"""事件卡结算注册表与 Age A/I 事件处理器(P2-T5/T6).

EVENT_HANDLERS: handler 名 -> (state, db) -> state。揭示流程见
politics.seed_event; 未注册的 Age A/I 事件 fail-loud(ValueError), 时代
II/III 事件在 T11/T12 注册前为无效果过场(TODO, 不阻塞对局)。

需要玩家决策的事件压入 pending 链: 从 current_player 起顺时针每座位一个
PendingEffect(responder=座位), 逐个结算 pop; 增益类选择(可
DeclineResponse 放弃)见 DECLINABLE_EVENT_KINDS, 强制失去类(raiders/
border_conflict)不可放弃(压入前保证恒有可执行选项, 防卡死)。
决策动作为 ChooseEventOption(见 apply_event_choice)或事件免费建造的
Build(见 EVENT_FREE_BUILD)。

强弱比较口径(规则书 p7):
- "最强/最弱文明"按 civ 军力(civ_values.strength); barbarians 的"文化
  领先者"按文化分存量(p.culture), immigration 按笑脸(civ 幸福);
- 平局按当前玩家顺时针近者优先(同一事件同时引用最强与最弱且全场平局时,
  同一文明可同为两者, 如 crusades 该文明 +4 再 -4);
- 2 人局"两个最X"理解为"一个最X";
- immigration 为"所有笑脸最多的文明"(PDF 原文 Civilization(s)), 平局的
  全部生效(规则书 p7: 提到"所有…最多/最少"时平局保持平局)。

时代 I 事件的 PDF 图标口径(卡牌数值表 v1.09 第 4 页, 以 PDF 文本为准):
- 竖琴 = 文化, 灯泡 = 科技, 棋子 = 人口(黄点), 黄球 = 黄点银行标记;
- barbarians / pestilence / reign_of_terror 均为失去人口(棋子图标):
  优先空闲工人池, 不足时按 (类别, card_id) 字典序从有工人的卡上移除
  (SIMPLIFICATION, 官方为玩家自选), 失去的黄点回到黄点银行。
"""

from collections.abc import Callable
from dataclasses import replace

from tta.engine import economy, effects, military
from tta.engine.civ import civ_values
from tta.engine.enums import (
    URBAN_CATEGORIES,
    Age,
    CardCategory,
)
from tta.engine.model import CardDB
from tta.engine.state import (
    GameState,
    PendingEffect,
    PlayerState,
    acting_index,
    active_indices,
    replace_player,
)

KIND_EVENT_MARKETS = "event_markets"
"""development_of_markets 选择 pending: responder 选 food/resource +2."""

KIND_EVENT_RELIGION = "event_religion"
"""development_of_religion 免费建造 pending: responder 可免费建 religion."""

KIND_EVENT_WARFARE = "event_warfare"
"""development_of_warfare 免费建造 pending: responder 可免费建 warriors."""

KIND_EVENT_CIVILIZATION = "event_civilization"
"""development_of_civilization 选择 pending: responder 三选一(官方口径:
人口/建造/研发; 建造在引擎中拆为 farm_mine 与 urban 两个 option, 见
CIVILIZATION_OPTION_PENDING 与 CIVILIZATION_OPTION_POPULATION)或
DeclineResponse."""

KIND_EVENT_DESTROY_BUILDING = "event_destroy_building"
"""border_conflict 失去建筑 pending: responder(最弱文明)选 1 张有工人的
城市建筑/农场/矿场卡, 移除 1 工人回空闲池(强制, 不可放弃)。"""

KIND_EVENT_FORAY = "event_foray"
"""foray 生产选择 pending: responder 选食物/资源组合(按价值共 3, 见
FORAY_OPTIONS), 可 DeclineResponse 放弃。"""

KIND_EVENT_RAIDERS = "event_raiders"
"""raiders 失去选择 pending: responder 选食物/资源组合(按价值共 2, 见
RAIDERS_OPTIONS), 不足部分损失到此为止(强制, 不可放弃)。"""

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
    KIND_EVENT_FORAY,
})
"""事件选择类 pending kind(增益类非强制选择, 可 DeclineResponse).

强制失去类(KIND_EVENT_DESTROY_BUILDING / KIND_EVENT_RAIDERS)不在名单:
压入前已保证恒有可执行选项(destroy 仅当有建筑可失; raiders 的
settle_loss 不足时损失到此为止, 不抛错), 不会卡死。"""

FORAY_OPTIONS: tuple[str, ...] = (
    "food:3", "food:2,resource:1", "food:1,resource:2", "resource:3",
)
"""foray 合法 option: 食物/资源组合, 按价值合计 3。"""

RAIDERS_OPTIONS: tuple[str, ...] = (
    "food:2", "food:1,resource:1", "resource:2",
)
"""raiders 合法 option: 食物/资源组合, 按价值合计 2。"""

DESTROY_BUILDING_CATEGORIES: frozenset[CardCategory] = (
    URBAN_CATEGORIES | frozenset({CardCategory.FARM, CardCategory.MINE})
)
"""border_conflict 可失去的建筑类别(城市建筑/农场/矿场, 不含兵种)。"""

REBELLION_CIVIL_LOSS = 2
"""rebellion 每名玩家下一回合失去的白点数。"""

DECLINABLE_PENDING_KINDS: frozenset[str] = (
    effects.DECLINABLE_PENDING_KINDS | DECLINABLE_EVENT_KINDS
)
"""可放弃 pending kind 全量白名单(行动卡子行动类 ∪ 事件选择类)."""

CIVILIZATION_OPTION_POPULATION = "population"
"""development_of_civilization 人口选项(官方选项 ①): +1 人口并付 1 食物."""

CIVILIZATION_POPULATION_FOOD_COST = 1
"""人口选项的食物费(事件固定价 1 食物, 非轨道人口费, moses 折扣不适用)."""

CIVILIZATION_OPTION_PENDING: dict[str, tuple[str, int]] = {
    "farm_mine": (effects.KIND_BUILD_FARM_MINE, 1),
    "urban": (effects.KIND_BUILD_URBAN, 1),
    "tech": (effects.KIND_DEVELOP_TECH, 1),
}
"""development_of_civilization 折扣选项 -> (子 pending kind, 折扣).

SIMPLIFICATION(brief 口径): "-1 食物建农场/矿场"与"-1 资源建城市建筑"
统一实现为建造折扣 1(引擎支付以资源计); "-1 科技研发科技"实现为
develop_tech pending 的科技费折扣 1。人口选项(①)无子 pending, 选择即
结算, 不在本表(见 CIVILIZATION_OPTION_POPULATION)。
"""

EVENT_HANDLERS: dict[str, Callable[[GameState, CardDB], GameState]] = {}
"""事件结算处理器注册表: handler 名 -> (state, db) -> 新 state."""

MARKETS_GAIN = 2
"""development_of_markets 每名玩家所得(食物或资源)."""

POLITICS_DRAW = 3
"""development_of_politics 每名玩家抓军事牌数."""


def resolve_event(state: GameState, db: CardDB, card_id: str) -> GameState:
    """揭示事件的统一入口: 查 EVENT_HANDLERS 结算.

    fail-loud: Age A/I 事件未注册 handler -> ValueError(T5/T6 拥有 Age A/I
    全量, 缺失即实现缺陷); 时代 II/III 事件在 T11/T12 注册前为无效果过场
    (不阻塞对局), 注册后删除该兜底统一 fail-loud。
    """
    card = db.get(card_id)
    handler = EVENT_HANDLERS.get(card.handler)
    if handler is None:
        if card.age in (Age.A, Age.I):
            msg = f"事件 {card_id!r} 未注册 EVENT_HANDLERS handler"
            raise ValueError(msg)
        # TODO(T11/T12): 后续时代事件 handler 注册前的过场兜底
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
        if option == CIVILIZATION_OPTION_POPULATION:
            # 官方选项 ①: +1 人口并付 1 食物(事件固定价, moses 折扣不适用)
            p = state.players[idx]
            p = replace(p, yellow_bank=p.yellow_bank - 1,
                        worker_pool=p.worker_pool + 1)
            p = economy.pay(db, p, "food", CIVILIZATION_POPULATION_FOOD_COST)
            return replace_player(state, idx, p)
        spec = CIVILIZATION_OPTION_PENDING.get(option)
        if spec is None:  # pragma: no cover - legal 已排除
            msg = f"事件 {pending.kind!r} 无选项 {option!r}"
            raise ValueError(msg)
        kind, discount = spec
        sub = PendingEffect(kind, discount, responder=idx)
        return replace(state, pending=(sub,) + state.pending)
    if pending.kind == KIND_EVENT_DESTROY_BUILDING:
        # border_conflict: 移除所选建筑卡上 1 工人, 回空闲池
        p = state.players[idx]
        card = db.get(option)
        buildings = dict(p.buildings)
        slots = dict(buildings[card.category.value])
        left = slots[option] - 1
        if left > 0:
            slots[option] = left
        else:
            del slots[option]
        buildings[card.category.value] = slots
        p = replace(p, buildings=buildings, worker_pool=p.worker_pool + 1)
        return replace_player(state, idx, p)
    if pending.kind == KIND_EVENT_FORAY:
        # foray: 按所选组合生产(按价值, 见 economy.gain_value)
        p = state.players[idx]
        for kind, amount in parse_mix(option):
            p = economy.gain_value(db, p, kind, amount)
        return replace_player(state, idx, p)
    if pending.kind == KIND_EVENT_RAIDERS:
        # raiders: 按所选组合失去(不足部分损失到此为止)
        p = state.players[idx]
        for kind, amount in parse_mix(option):
            p, _ = economy.settle_loss(db, p, kind, amount)
        return replace_player(state, idx, p)
    msg = f"pending {pending.kind!r} 不接受 ChooseEventOption"  # pragma: no cover
    raise ValueError(msg)  # pragma: no cover


def parse_mix(option: str) -> tuple[tuple[str, int], ...]:
    """解析 "food:2,resource:1" 形式的组合 option 为 ((kind, 数量), ...)."""
    parts: list[tuple[str, int]] = []
    for chunk in option.split(","):
        kind, _, count = chunk.partition(":")
        parts.append((kind, int(count)))
    return tuple(parts)


# --- pending 链辅助 ----------------------------------------------------------


def _seat_order(state: GameState) -> list[int]:
    """从 current_player 起顺时针的座位序(不含已体面退出者)."""
    n = len(state.players)
    return [
        (state.current_player + i) % n for i in range(n)
        if not state.players[(state.current_player + i) % n].resigned
    ]


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


# --- Age A 事件 handler(卡牌数值表 p4 文本) --------------------------------------


def _gain_tokens_all(
    db: CardDB, state: GameState, kind: str, count: int,
) -> GameState:
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, economy.gain_tokens(db, p, kind, count))
    return state


def _development_of_agriculture(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 食物."""
    return _gain_tokens_all(db, state, "food", 2)


def _development_of_civilization(state: GameState, db: CardDB) -> GameState:
    """每名玩家三选一(官方口径): +1 人口付 1 食物 | -1 建造 | -1 研发."""
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
        state = military.draw_military(state, seat, POLITICS_DRAW)
    return state


def _development_of_religion(state: GameState, db: CardDB) -> GameState:
    """有可用工人的玩家可免费建 1 宗教(pending 链, 可放弃)."""
    return _push_free_build_chain(state, KIND_EVENT_RELIGION, "religion")


def _development_of_science(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 科技."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, replace(p, science=p.science + 2))
    return state


def _development_of_settlement(state: GameState, db: CardDB) -> GameState:
    """每个文明免费 +1 人口(yellow_bank > 0 才生效; 不付食物费)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        if p.yellow_bank > 0:
            state = replace_player(state, i, replace(
                p, yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1))
    return state


def _development_of_trade_route(state: GameState, db: CardDB) -> GameState:
    """每个文明 +1 科技、+1 食物、+1 资源."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
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


# --- 强弱比较辅助(规则书 p7) ------------------------------------------------------


def _clockwise_distance(state: GameState, seat: int) -> int:
    """座位距 current_player 的顺时针距离(0 = 当前玩家)."""
    return (seat - state.current_player) % len(state.players)


def _extreme_seats(
    state: GameState, values: list[int], *, strongest: bool, count: int = 1,
) -> list[int]:
    """按 values 取最值前 count 个座位; 平局按当前玩家顺时针近者优先.

    返回按"最值程度"排序的座位列表(同一事件同时引用最强与最弱且全场平局
    时, 两侧可判给同一座位 — 规则书 p7 平局口径的字面结果)。
    已体面退出者(resigned)不参与比较(规则书 p4: 其文明移出游戏)。
    """
    seats = active_indices(state)

    def key(seat: int) -> tuple[int, int]:
        primary = -values[seat] if strongest else values[seat]
        return (primary, _clockwise_distance(state, seat))

    return sorted(seats, key=key)[:count]


def _most_count(state: GameState) -> int:
    """"两个最X"的数量: 2 人局理解为"一个最X"(规则书 p7), 否则 2.

    按在局(未退出)人数计(规则书 p4: 只剩 2 位玩家时按 2 人规则结算事件)。
    """
    return 1 if len(active_indices(state)) == 2 else 2


def _strengths(db: CardDB, state: GameState) -> list[int]:
    """各玩家 civ 军力(最强/最弱文明的比较口径; 含条约静态加成)."""
    return [
        civ_values(db, p, state.players, i).strength
        for i, p in enumerate(state.players)
    ]


def _weakest_seats(db: CardDB, state: GameState) -> list[int]:
    """"两个最弱文明"座位(2 人局 1 个), 按军力升序 + 顺时针平局口径."""
    return _extreme_seats(
        state, _strengths(db, state), strongest=False,
        count=_most_count(state))


def _strongest_seats(db: CardDB, state: GameState) -> list[int]:
    """"两个最强文明"座位(2 人局 1 个), 按军力降序 + 顺时针平局口径."""
    return _extreme_seats(
        state, _strengths(db, state), strongest=True,
        count=_most_count(state))


def _clockwise_sorted(state: GameState, seats: list[int]) -> list[int]:
    """座位集按从 current_player 起顺时针排序(多人决策的依次结算序)."""
    return sorted(seats, key=lambda seat: _clockwise_distance(state, seat))


def lose_population(p: PlayerState, count: int) -> PlayerState:
    """失去人口: 优先空闲工人池, 不足按 (类别, card_id) 字典序从卡上移除.

    失去的黄点回到黄点银行(官方规则, 如 emigration 注记 return to yellow
    bank)。SIMPLIFICATION: 池空时官方为玩家自选, 引擎按字典序确定选取。
    """
    from_pool = min(count, p.worker_pool)
    remaining = count - from_pool
    buildings = {cat: dict(slots) for cat, slots in p.buildings.items()}
    taken = 0
    for cat in sorted(buildings):
        for card_id in sorted(buildings[cat]):
            if remaining == 0:
                break
            take = min(remaining, buildings[cat][card_id])
            if take == 0:
                continue
            left = buildings[cat][card_id] - take
            if left > 0:
                buildings[cat][card_id] = left
            else:
                del buildings[cat][card_id]
            remaining -= take
            taken += take
    return replace(
        p,
        worker_pool=p.worker_pool - from_pool,
        yellow_bank=p.yellow_bank + from_pool + taken,
        buildings=buildings,
    )


def destroyable_building_ids(p: PlayerState) -> list[str]:
    """border_conflict 可失去的建筑卡 id(有工人的城市建筑/农场/矿场)."""
    ids: list[str] = []
    for cat_value, slots in sorted(p.buildings.items()):
        if CardCategory(cat_value) not in DESTROY_BUILDING_CATEGORIES:
            continue
        ids.extend(card_id for card_id, n in sorted(slots.items()) if n > 0)
    return ids


# --- 时代 I 事件 handler(卡牌数值表 p4 Events 表 Age I 行) ---------------------------


def _barbarians(state: GameState, db: CardDB) -> GameState:
    """文化领先者(文化分最多)若为两个最弱文明之一, 失去 1 人口."""
    cultures = [p.culture for p in state.players]
    leader = _extreme_seats(state, cultures, strongest=True)[0]
    if leader in _weakest_seats(db, state):
        state = replace_player(
            state, leader, lose_population(state.players[leader], 1))
    return state


def _border_conflict(state: GameState, db: CardDB) -> GameState:
    """最弱失去 1 城市建筑/农场/矿场(该玩家选择, 强制 pending); 最强产 3 资源."""
    weakest = _weakest_seats(db, state)[0]
    strongest = _strongest_seats(db, state)[0]
    p = state.players[strongest]
    state = replace_player(
        state, strongest, economy.gain_value(db, p, "resource", 3))
    if destroyable_building_ids(state.players[weakest]):
        state = _push_chain(state, KIND_EVENT_DESTROY_BUILDING, [weakest])
    return state


def _crusades(state: GameState, db: CardDB) -> GameState:
    """最强 +4 文化; 最弱 -4 文化(下限 0, 同 turn 食物短缺的文化扣减口径)."""
    strongest = _strongest_seats(db, state)[0]
    weakest = _weakest_seats(db, state)[0]
    p = state.players[strongest]
    state = replace_player(state, strongest, replace(p, culture=p.culture + 4))
    p = state.players[weakest]
    return replace_player(
        state, weakest, replace(p, culture=max(0, p.culture - 4)))


def _cultural_influence(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化, 等于其文化增速."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        rate = civ_values(db, p, state.players, i).culture_rate
        if rate:
            state = replace_player(state, i, replace(p, culture=p.culture + rate))
    return state


def _foray(state: GameState, db: CardDB) -> GameState:
    """两个最强文明各产共 3 食物/资源(各自选组合, 顺时针依次, 可放弃)."""
    seats = _clockwise_sorted(state, _strongest_seats(db, state))
    return _push_chain(state, KIND_EVENT_FORAY, seats)


def _good_harvest(state: GameState, db: CardDB) -> GameState:
    """每名玩家农场立即生产(事件即时结算, 天然无消耗与腐败)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, economy.produce(db, p, "food"))
    return state


def _immigration(state: GameState, db: CardDB) -> GameState:
    """笑脸最多的所有文明(平局全部)免费 +1 人口(黄点银行非空才生效)."""
    happiness = [
        civ_values(db, p, state.players, i).happiness
        for i, p in enumerate(state.players)
    ]
    best = max(happiness)
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        if happiness[i] == best and p.yellow_bank > 0:
            state = replace_player(state, i, replace(
                p, yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1))
    return state


def _new_deposits(state: GameState, db: CardDB) -> GameState:
    """每名玩家矿场立即生产(忽略腐败)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, economy.produce(db, p, "resource"))
    return state


def _pestilence(state: GameState, db: CardDB) -> GameState:
    """每个文明 -1 人口."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, lose_population(p, 1))
    return state


def _raiders(state: GameState, db: CardDB) -> GameState:
    """两个最弱文明各失去共 2 食物/资源(各自选组合, 强制; 全无则不压)."""
    seats = [
        seat for seat in _clockwise_sorted(state, _weakest_seats(db, state))
        if (economy.food_total(db, state.players[seat])
            + economy.resource_total(db, state.players[seat])) > 0
    ]
    return _push_chain(state, KIND_EVENT_RAIDERS, seats)


def _rats(state: GameState, db: CardDB) -> GameState:
    """每个文明失去所有储存的食物(农场卡上蓝点全清回供给区)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        farm_tokens = sum(
            n for card_id, n in p.card_tokens.items()
            if n > 0 and db.get(card_id).category is CardCategory.FARM
        )
        if not farm_tokens:
            continue
        tokens = {
            card_id: n for card_id, n in p.card_tokens.items()
            if db.get(card_id).category is not CardCategory.FARM
        }
        state = replace_player(state, i, replace(
            p, card_tokens=tokens, blue_bank=p.blue_bank + farm_tokens))
    return state


def _rebellion(state: GameState, db: CardDB) -> GameState:
    """每名玩家下一回合 -2 白点.

    行动点在每回合末恢复(为下一回合预算): 当前玩家的下一次恢复尚未发生,
    挂 civil_action_debt 于恢复时生效(见 turn.end_of_turn); 他玩家的下
    回合行动点已于其上一回合末恢复完毕, 立即 -2(下限 0)。
    """
    idx = state.current_player
    players: list[PlayerState] = []
    for i, p in enumerate(state.players):
        if p.resigned:
            players.append(p)
            continue
        if i == idx:
            p = replace(
                p, civil_action_debt=p.civil_action_debt + REBELLION_CIVIL_LOSS)
        else:
            p = replace(p, civil_actions=max(
                0, p.civil_actions - REBELLION_CIVIL_LOSS))
        players.append(p)
    return replace(state, players=tuple(players))


def _reign_of_terror(state: GameState, db: CardDB) -> GameState:
    """最弱文明 -1 人口."""
    weakest = _weakest_seats(db, state)[0]
    return replace_player(
        state, weakest, lose_population(state.players[weakest], 1))


def _scientific_breakthrough(state: GameState, db: CardDB) -> GameState:
    """每个文明 +科技, 等于其科技增速."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        rate = civ_values(db, p, state.players, i).science_rate
        if rate:
            state = replace_player(state, i, replace(p, science=p.science + rate))
    return state


def _uncertain_borders(state: GameState, db: CardDB) -> GameState:
    """最弱文明从黄点银行给最强文明 1 黄点(银行空或同一文明则无效果)."""
    weakest = _weakest_seats(db, state)[0]
    strongest = _strongest_seats(db, state)[0]
    if weakest == strongest or state.players[weakest].yellow_bank == 0:
        return state
    p_from = replace(
        state.players[weakest],
        yellow_bank=state.players[weakest].yellow_bank - 1)
    state = replace_player(state, weakest, p_from)
    p_to = replace(
        state.players[strongest],
        yellow_bank=state.players[strongest].yellow_bank + 1)
    return replace_player(state, strongest, p_to)


EVENT_HANDLERS.update({
    "barbarians": _barbarians,
    "border_conflict": _border_conflict,
    "crusades": _crusades,
    "cultural_influence": _cultural_influence,
    "foray": _foray,
    "good_harvest": _good_harvest,
    "immigration": _immigration,
    "new_deposits": _new_deposits,
    "pestilence": _pestilence,
    "raiders": _raiders,
    "rats": _rats,
    "rebellion": _rebellion,
    "reign_of_terror": _reign_of_terror,
    "scientific_breakthrough": _scientific_breakthrough,
    "uncertain_borders": _uncertain_borders,
})
