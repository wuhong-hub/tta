"""事件卡结算注册表与 Age A 事件处理器(P2-T5).

EVENT_HANDLERS: handler 名 -> (state, db) -> state。揭示流程见
politics.seed_event; 未注册的 Age A 事件 fail-loud(ValueError), 时代
I/II/III 事件在 T6/T11/T12 注册前为无效果过场(TODO, 不阻塞对局)。

需要玩家决策的事件压入 pending 链: 从 current_player 起顺时针每座位一个
PendingEffect(responder=座位), 逐个结算 pop; 均为非强制选择(可
DeclineResponse 放弃)。决策动作为 ChooseEventOption(见
apply_event_choice)或事件免费建造的 Build(见 EVENT_FREE_BUILD)。
"""

from collections.abc import Callable
from dataclasses import replace

from tta.engine import economy, effects
from tta.engine.enums import Age
from tta.engine.model import CardDB
from tta.engine.rng import rng_shuffle
from tta.engine.state import (
    GameState,
    PendingEffect,
    PlayerState,
    acting_index,
    replace_player,
)

KIND_EVENT_MARKETS = "event_markets"
"""development_of_markets 选择 pending: responder 选 food/resource +2."""

KIND_EVENT_RELIGION = "event_religion"
"""development_of_religion 免费建造 pending: responder 可免费建 religion."""

KIND_EVENT_WARFARE = "event_warfare"
"""development_of_warfare 免费建造 pending: responder 可免费建 warriors."""

KIND_EVENT_CIVILIZATION = "event_civilization"
"""development_of_civilization 选择 pending: responder 三选一(见
CIVILIZATION_OPTION_PENDING)或 DeclineResponse."""

EVENT_FREE_BUILD: dict[str, str] = {
    KIND_EVENT_RELIGION: "religion",
    KIND_EVENT_WARFARE: "warriors",
}
"""事件免费建造 pending kind -> 可免费放置 1 工人的卡 id(0 行动点 0 费用)."""

DECLINABLE_EVENT_KINDS: frozenset[str] = frozenset({
    KIND_EVENT_MARKETS,
    KIND_EVENT_RELIGION,
    KIND_EVENT_WARFARE,
    KIND_EVENT_CIVILIZATION,
})
"""事件选择类 pending kind(均为非强制选择, 可 DeclineResponse)."""

DECLINABLE_PENDING_KINDS: frozenset[str] = (
    effects.DECLINABLE_PENDING_KINDS | DECLINABLE_EVENT_KINDS
)
"""可放弃 pending kind 全量白名单(行动卡子行动类 ∪ 事件选择类)."""

CIVILIZATION_OPTION_PENDING: dict[str, tuple[str, int]] = {
    "farm_mine": (effects.KIND_BUILD_FARM_MINE, 1),
    "urban": (effects.KIND_BUILD_URBAN, 1),
    "tech": (effects.KIND_DEVELOP_TECH, 1),
}
"""development_of_civilization 选项 -> (子 pending kind, 折扣).

SIMPLIFICATION(brief 口径): "-1 食物建农场/矿场"与"-1 资源建城市建筑"
统一实现为建造折扣 1(引擎支付以资源计); "-1 科技研发科技"实现为
develop_tech pending 的科技费折扣 1。
"""

EVENT_HANDLERS: dict[str, Callable[[GameState, CardDB], GameState]] = {}
"""事件结算处理器注册表: handler 名 -> (state, db) -> 新 state."""

MARKETS_GAIN = 2
"""development_of_markets 每名玩家所得(食物或资源)."""

POLITICS_DRAW = 3
"""development_of_politics 每名玩家抓军事牌数."""


def resolve_event(state: GameState, db: CardDB, card_id: str) -> GameState:
    """揭示事件的统一入口: 查 EVENT_HANDLERS 结算.

    fail-loud: Age A 事件未注册 handler -> ValueError(T5 拥有 Age A 全量,
    缺失即实现缺陷); 时代 I/II/III 事件在 T6/T11/T12 注册前为无效果过场
    (不阻塞对局), 注册后删除该兜底统一 fail-loud。
    """
    card = db.get(card_id)
    handler = EVENT_HANDLERS.get(card.handler)
    if handler is None:
        if card.age is Age.A:
            msg = f"事件 {card_id!r} 未注册 EVENT_HANDLERS handler"
            raise ValueError(msg)
        # TODO(T6/T11/T12): 后续时代事件 handler 注册前的过场兜底
        return state
    return handler(state, db)


def apply_event_choice(
    db: CardDB, state: GameState, option: str,
) -> GameState:
    """ChooseEventOption 结算: pop pending[0] 并按 kind 分派(合法性由 legal 保证)."""
    if not state.pending:  # pragma: no cover - legal 已排除
        msg = "无待决策的事件 pending"
        raise ValueError(msg)
    pending = state.pending[0]
    idx = acting_index(state)
    state = replace(state, pending=state.pending[1:])
    if pending.kind == KIND_EVENT_MARKETS:
        p = economy.gain_tokens(db, state.players[idx], option, MARKETS_GAIN)
        return replace_player(state, idx, p)
    if pending.kind == KIND_EVENT_CIVILIZATION:
        spec = CIVILIZATION_OPTION_PENDING.get(option)
        if spec is None:  # pragma: no cover - legal 已排除
            msg = f"事件 {pending.kind!r} 无选项 {option!r}"
            raise ValueError(msg)
        kind, discount = spec
        sub = PendingEffect(kind, discount, responder=idx)
        return replace(state, pending=(sub,) + state.pending)
    msg = f"pending {pending.kind!r} 不接受 ChooseEventOption"  # pragma: no cover
    raise ValueError(msg)  # pragma: no cover


# --- pending 链与抓牌辅助 -------------------------------------------------------


def _seat_order(state: GameState) -> list[int]:
    """从 current_player 起顺时针的座位序."""
    n = len(state.players)
    return [(state.current_player + i) % n for i in range(n)]


def _push_chain(state: GameState, kind: str, seats: list[int]) -> GameState:
    """按座位序压一串同 kind pending(responder=座位), 逐个结算 pop."""
    chain = tuple(PendingEffect(kind, 0, responder=seat) for seat in seats)
    return replace(state, pending=state.pending + chain)


def _placed_count(p: PlayerState, card_id: str) -> int:
    return sum(slots.get(card_id, 0) for slots in p.buildings.values())


def _free_build_eligible(p: PlayerState, card_id: str) -> bool:
    """事件免费建造资格: 有可用工人且该卡有空槽."""
    return (
        p.worker_pool >= 1
        and _placed_count(p, card_id) < p.developed.count(card_id)
    )


def _push_free_build_chain(state: GameState, kind: str, card_id: str) -> GameState:
    seats = [
        seat for seat in _seat_order(state)
        if _free_build_eligible(state.players[seat], card_id)
    ]
    return _push_chain(state, kind, seats)


def _draw_military(state: GameState, idx: int, count: int) -> GameState:
    """从军事牌堆抓 count 张入 idx 手(牌堆空切洗军事弃牌堆; 时代 IV 不抓).

    与 turn._draw_military 同一官方口径(规则书 p7), 供事件效果调用。
    """
    if state.age is Age.IV or count <= 0:
        return state
    deck = list(state.military_deck)
    discard = list(state.military_discard)
    hand = list(state.players[idx].hand_military)
    rng = state.rng_state
    for _ in range(count):
        if not deck:
            if not discard:
                break
            rng, deck = rng_shuffle(rng, discard)
            discard = []
        hand.append(deck.pop(0))
    state = replace(state, military_deck=tuple(deck),
                    military_discard=tuple(discard), rng_state=rng)
    return replace_player(
        state, idx, replace(state.players[idx], hand_military=tuple(hand)))


# --- Age A 事件 handler(卡牌数值表 p4 文本) --------------------------------------


def _gain_tokens_all(
    db: CardDB, state: GameState, kind: str, count: int,
) -> GameState:
    for i, p in enumerate(state.players):
        state = replace_player(state, i, economy.gain_tokens(db, p, kind, count))
    return state


def _development_of_agriculture(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 食物."""
    return _gain_tokens_all(db, state, "food", 2)


def _development_of_civilization(state: GameState, db: CardDB) -> GameState:
    """每名玩家三选一(brief 口径): -1 建农场/矿场 | -1 建城市建筑 | -1 研发."""
    return _push_chain(state, KIND_EVENT_CIVILIZATION, _seat_order(state))


def _development_of_crafts(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 资源."""
    return _gain_tokens_all(db, state, "resource", 2)


def _development_of_markets(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 食物或 +2 资源(玩家各自选, pending 链)."""
    return _push_chain(state, KIND_EVENT_MARKETS, _seat_order(state))


def _development_of_politics(state: GameState, db: CardDB) -> GameState:
    """每名玩家 +3 张军事牌(从 current_player 起顺时针, 共享军事牌堆)."""
    for seat in _seat_order(state):
        state = _draw_military(state, seat, POLITICS_DRAW)
    return state


def _development_of_religion(state: GameState, db: CardDB) -> GameState:
    """有可用工人的玩家可免费建 1 宗教(pending 链, 可放弃)."""
    return _push_free_build_chain(state, KIND_EVENT_RELIGION, "religion")


def _development_of_science(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 科技."""
    for i, p in enumerate(state.players):
        state = replace_player(state, i, replace(p, science=p.science + 2))
    return state


def _development_of_settlement(state: GameState, db: CardDB) -> GameState:
    """每个文明免费 +1 人口(yellow_bank > 0 才生效; 不付食物费)."""
    for i, p in enumerate(state.players):
        if p.yellow_bank > 0:
            state = replace_player(state, i, replace(
                p, yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1))
    return state


def _development_of_trade_route(state: GameState, db: CardDB) -> GameState:
    """每个文明 +1 科技、+1 食物、+1 资源."""
    for i, p in enumerate(state.players):
        p = replace(p, science=p.science + 1)
        p = economy.gain_tokens(db, p, "food", 1)
        p = economy.gain_tokens(db, p, "resource", 1)
        state = replace_player(state, i, p)
    return state


def _development_of_warfare(state: GameState, db: CardDB) -> GameState:
    """有可用工人的玩家可免费建 1 战士(pending 链, 可放弃)."""
    return _push_free_build_chain(state, KIND_EVENT_WARFARE, "warriors")


EVENT_HANDLERS.update({
    "development_of_agriculture": _development_of_agriculture,
    "development_of_civilization": _development_of_civilization,
    "development_of_crafts": _development_of_crafts,
    "development_of_markets": _development_of_markets,
    "development_of_politics": _development_of_politics,
    "development_of_religion": _development_of_religion,
    "development_of_science": _development_of_science,
    "development_of_settlement": _development_of_settlement,
    "development_of_trade_route": _development_of_trade_route,
    "development_of_warfare": _development_of_warfare,
})
