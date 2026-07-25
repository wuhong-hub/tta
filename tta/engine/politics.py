"""政治阶段动作与 SeedEvent 结算(P2-T5) + 殖民竞拍与地区牌(P2-T7).

每回合限 1 政治行动: POLITICS 相位 legal = 政治动作 + SkipPolitics(见
legal.py), 任一政治动作结算后置 phase=ACTION(Julius Caesar 一次性双政治
T10)。侵略/战争/条约/退出动作类型已建(actions.py), 结算见 T8/T9/T10。

SeedEvent 结算(规则书 p4/p7):
1. 军事手牌中的 EVENT 卡面朝下压入 future_events 顶;
2. 揭示 current_events 顶牌(空 -> 无事发生):
   - TERRITORY -> 触发殖民竞拍(本文件下半部分);
   - 其余 -> events.resolve_event 查 EVENT_HANDLERS 结算, 结算后入
     past_events;
3. 若揭示的是 current_events 最后一张: 重洗 future_events(按时代分组,
   早时代在上, 组内 rng_shuffle)成为新 current_events。

殖民竞拍(规则书 p7 殖民节):
- 揭示 TERRITORY -> pending kind="colonize_bid", responder 从揭示者起
  顺时针轮转; context = {territory, current_bid, leader(-1=无人出价),
  bidders(剩余竞拍者座位, 逗号连接字符串)}。
- ColonizeBid(amount): 须 > current_bid 且 <= 可承诺殖民军力上限
  (colonization_cap = 全部军事单位军力含阵型 + 殖民修正 + 手中军事奖励牌
  殖民数值总和); 出价须至少 1 且出价者须有至少 1 个军事单位(规则: 必须
  挑出至少 1 个军事单位, 不能只靠奖励牌与殖民修正)。
- ColonizePass(): 退出竞拍。仅剩 leader 时 leader 胜出; 无人出价且全员
  退出 -> 流拍, 地区牌入 past_events。无人出价时仅剩 1 人仍须做决定
  (可出价直接胜出, 或退出流拍)。leader 不会再次行动(其余人全 pass 即
  胜出), 故不存在"leader 退出"的悬空高出价。
- 胜者 -> pending kind="colonize_sacrifice"(responder=胜者, context =
  {territory, bid, bonus}):
  - ColonizePlayBonus(card_id): 打出手中军事奖励牌, 殖民数值累加进
    context["bonus"], 卡入军事弃牌堆; 未打出的留在手牌;
  - ColonizeSacrifice(units): 提交牺牲单位元组(组合枚举爆炸, legal 仅给
    "全选"锚点, apply 前独立校验): 所选单位军力(按当前阵型组军, 见
    military.units_strength) + 殖民修正 + bonus >= bid, 至少 1 个单位;
    每个单位 1 工人回黄点银行(规则: 黄色标记放回黄色人口区)。
- 获得殖民地: colonies 追加; 永久黄/蓝标记先入银行(官方: 可为即时效果
  提供标记; 负值下限 0), 再结算即时效果(science/culture/food/materials
  按价值/population 免费人口/military_card 抽军事牌忽略手牌上限);
  永久效果(除黄/蓝标记)接入 civ.py 合成。
"""

from dataclasses import replace

from tta.engine import economy, events, military
from tta.engine.actions import (
    ColonizeBid,
    ColonizePass,
    ColonizePlayBonus,
    ColonizeSacrifice,
    IllegalActionError,
    SeedEvent,
)
from tta.engine.civ import civ_values
from tta.engine.enums import UNIT_CATEGORIES, Age, CardCategory, Phase
from tta.engine.model import CardDB
from tta.engine.rng import rng_shuffle
from tta.engine.state import (
    GameState,
    PendingEffect,
    PlayerState,
    acting_index,
    replace_player,
)

_AGE_ORDER = (Age.A, Age.I, Age.II, Age.III, Age.IV)
"""事件重洗分组的时代序(早时代在上)."""

KIND_COLONIZE_BID = "colonize_bid"
"""殖民竞拍 pending: responder 轮流出价(ColonizeBid)或退出(ColonizePass)."""

KIND_COLONIZE_SACRIFICE = "colonize_sacrifice"
"""胜者牺牲结算 pending: 打出奖励牌(ColonizePlayBonus)并提交牺牲单位
(ColonizeSacrifice)后获得殖民地。"""

_COLONY_TOKEN_KEYS = ("yellow_token", "blue_token")
"""殖民地永久效果中的一次性银行标记键(获得时调整, 不入 civ 合成)."""


def politics_actions(db: CardDB, state: GameState) -> list[SeedEvent]:
    """POLITICS 相位可用政治动作(不含 SkipPolitics, 由 legal 追加).

    当前仅 SeedEvent(军事手牌中的 EVENT 卡); 侵略/战争/条约动作 T8/T9/T10
    加入。RULES-CHECK(规则书 p4 未禁止): 时代 IV 无军事牌可抽, 但手牌中
    已有的事件牌仍可筹划。
    """
    p = state.players[state.current_player]
    return [
        SeedEvent(card_id)
        for card_id in dict.fromkeys(p.hand_military)
        if db.get(card_id).category is CardCategory.EVENT
    ]


def seed_event(db: CardDB, state: GameState, action: SeedEvent) -> GameState:
    """SeedEvent 结算: 筹划 -> 揭示 -> past_events -> (当前堆尽)重洗.

    结算后 phase=ACTION(每回合限 1 政治行动); 事件 handler 压入的 pending
    链在 ACTION 相位由 legal 的 pending 分支逐座位结算。
    """
    idx = state.current_player
    p = state.players[idx]
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    state = replace_player(state, idx, replace(p, hand_military=tuple(hand)))
    # 1. 筹划卡面朝下压入 future_events 顶
    state = replace(
        state, future_events=(action.card_id,) + state.future_events)
    # 2. 揭示 current_events 顶牌; 空 -> 无事发生
    if not state.current_events:
        return replace(state, phase=Phase.ACTION)
    revealed = state.current_events[0]
    state = replace(state, current_events=state.current_events[1:])
    card = db.get(revealed)
    if card.category is CardCategory.TERRITORY:
        # TERRITORY -> 殖民竞拍; 地区牌暂不入 past_events(流拍时才入,
        # 成交则入胜者 colonies)
        state = _start_colonization(state, revealed)
    else:
        state = events.resolve_event(state, db, revealed)
        # 3. 结算后该卡入 past_events
        state = replace(state, past_events=state.past_events + (revealed,))
    # 4. 揭示的是 current_events 最后一张 -> 重洗 future 成为新 current
    if not state.current_events and state.future_events:
        state = _reshuffle_future_events(db, state)
    return replace(state, phase=Phase.ACTION)


def _reshuffle_future_events(db: CardDB, state: GameState) -> GameState:
    """重洗 future_events 成为新 current_events: 按时代分组, 早时代在上,
    组内 rng_shuffle(消费 GameState.rng_state)."""
    groups: dict[Age, list[str]] = {}
    for card_id in state.future_events:
        groups.setdefault(db.get(card_id).age, []).append(card_id)
    rng = state.rng_state
    cards: list[str] = []
    for age in sorted(groups, key=_AGE_ORDER.index):
        rng, shuffled = rng_shuffle(rng, groups[age])
        cards.extend(shuffled)
    return replace(
        state, current_events=tuple(cards), future_events=(), rng_state=rng)


# --- 殖民竞拍(规则书 p7 殖民节) -------------------------------------------------


def colonization_cap(db: CardDB, p: PlayerState) -> int:
    """可承诺殖民军力上限 = 全部军事单位军力(含阵型加成) + 殖民修正
    + 手中军事奖励牌殖民数值总和.

    基础军力用 army_strength 口径(单位 + 阵型, 不含领袖/奇迹的军力静态
    加成 — 官方: 军力等级修正不作用于殖民军力); 殖民修正 = civ 合成的
    colonization 键(领袖/奇迹/特殊科技/殖民地); 奖励牌按手中 BONUS 卡的
    colonize_bonus 求和(出价时自动计入上限, 履约时须实际打出)。
    """
    hand_bonus = sum(db.get(card_id).colonize_bonus for card_id in p.hand_military)
    return (
        military.army_strength(db, p)
        + civ_values(db, p).colonization
        + hand_bonus
    )


def has_military_unit(p: PlayerState) -> bool:
    """玩家是否拥有至少 1 个军事单位(有工人的单位卡)."""
    return any(
        workers > 0
        for category in UNIT_CATEGORIES
        for workers in p.buildings.get(category.value, {}).values()
    )


def _decode_bidders(context: dict[str, str | int]) -> list[int]:
    raw = str(context.get("bidders", ""))
    return [int(s) for s in raw.split(",") if s != ""]


def _encode_bidders(bidders: list[int]) -> str:
    return ",".join(str(s) for s in bidders)


def _next_bidder(bidders: list[int], after: int, num_players: int) -> int:
    """bidders 中座位 after 顺时针方向的下一个剩余竞拍者."""
    for step in range(1, num_players + 1):
        candidate = (after + step) % num_players
        if candidate in bidders:
            return candidate
    msg = "bidders 为空, 无下一个竞拍者"  # pragma: no cover - 调用前已判空
    raise ValueError(msg)  # pragma: no cover


def _start_colonization(state: GameState, territory: str) -> GameState:
    """揭示 TERRITORY: 压入 colonize_bid pending, 从揭示者起顺时针轮转."""
    n = len(state.players)
    bidders = [(state.current_player + i) % n for i in range(n)]
    pending = PendingEffect(
        KIND_COLONIZE_BID, 0, responder=state.current_player,
        context={
            "territory": territory,
            "current_bid": 0,
            "leader": -1,
            "bidders": _encode_bidders(bidders),
        })
    return replace(state, pending=state.pending + (pending,))


def _win_bid(state: GameState, winner: int, territory: str, bid: int) -> GameState:
    """竞拍结束: colonize_bid -> colonize_sacrifice(responder=胜者)."""
    sacrifice = PendingEffect(
        KIND_COLONIZE_SACRIFICE, 0, responder=winner,
        context={"territory": territory, "bid": bid, "bonus": 0})
    return replace(state, pending=(sacrifice,) + state.pending[1:])


def colonize_bid(db: CardDB, state: GameState, action: ColonizeBid) -> GameState:
    """ColonizeBid 结算: 更新 leader/current_bid, responder 轮转或决出胜者.

    合法性(amount > current_bid, amount <= 上限, 出价者有单位)由 legal 保证。
    """
    idx = acting_index(state)
    pending = state.pending[0]
    context = dict(pending.context)
    context["current_bid"] = action.amount
    context["leader"] = idx
    bidders = _decode_bidders(context)
    if len(bidders) == 1:
        # 唯一参与者出价 -> 直接胜出
        return _win_bid(state, idx, str(context["territory"]), action.amount)
    context["bidders"] = _encode_bidders(bidders)
    nxt = _next_bidder(bidders, idx, len(state.players))
    new_pending = replace(pending, responder=nxt, context=context)
    return replace(state, pending=(new_pending,) + state.pending[1:])


def colonize_pass(db: CardDB, state: GameState, action: ColonizePass) -> GameState:
    """ColonizePass 结算: 退出竞拍; 流拍 / 决出胜者 / 轮转."""
    idx = acting_index(state)
    pending = state.pending[0]
    context = dict(pending.context)
    territory = str(context["territory"])
    bidders = _decode_bidders(context)
    bidders.remove(idx)
    if not bidders:
        # 全员退出 -> 流拍, 地区牌入 past_events
        state = replace(state, pending=state.pending[1:])
        return replace(state, past_events=state.past_events + (territory,))
    leader = int(context["leader"])
    if leader != -1 and bidders == [leader]:
        # 其余人全部退出 -> leader 胜出
        return _win_bid(state, leader, territory, int(context["current_bid"]))
    # 否则轮转(含"无人出价仅剩 1 人仍须做决定"的情形)
    context["bidders"] = _encode_bidders(bidders)
    nxt = _next_bidder(bidders, idx, len(state.players))
    new_pending = replace(pending, responder=nxt, context=context)
    return replace(state, pending=(new_pending,) + state.pending[1:])


def colonize_play_bonus(
    db: CardDB, state: GameState, action: ColonizePlayBonus,
) -> GameState:
    """ColonizePlayBonus 结算: 手牌移除, 入军事弃牌堆, 殖民数值累加."""
    idx = acting_index(state)
    p = state.players[idx]
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    state = replace_player(state, idx, replace(p, hand_military=tuple(hand)))
    state = replace(
        state, military_discard=state.military_discard + (action.card_id,))
    pending = state.pending[0]
    context = dict(pending.context)
    context["bonus"] = (
        int(context.get("bonus", 0)) + db.get(action.card_id).colonize_bonus)
    return replace(
        state, pending=(replace(pending, context=context),) + state.pending[1:])


def colonize_sacrifice(
    db: CardDB, state: GameState, action: ColonizeSacrifice,
) -> GameState:
    """ColonizeSacrifice 结算: 独立校验(组合枚举爆炸, 非 legal 成员判定).

    校验: 存在 colonize_sacrifice pending; 至少 1 个单位; 均为有工人的
    军事单位卡(重复数不超过工人数); 所选单位军力(按当前阵型组军) + 殖民
    修正 + 已出奖励 >= 出价。成功后每单位 1 工人回黄点银行, 获得殖民地。
    """
    if not state.pending or state.pending[0].kind != KIND_COLONIZE_SACRIFICE:
        msg = f"当前无殖民牺牲 pending, 无法执行 {action!r}"
        raise IllegalActionError(msg)
    pending = state.pending[0]
    idx = acting_index(state)
    p = state.players[idx]
    units = action.units
    if not units:
        msg = "必须挑出至少 1 个军事单位(规则书 p7)"
        raise IllegalActionError(msg)
    counts: dict[str, int] = {}
    for card_id in units:
        if card_id not in db.cards:
            msg = f"未知卡牌 id: {card_id!r}"
            raise IllegalActionError(msg)
        if db.get(card_id).category not in UNIT_CATEGORIES:
            msg = f"{card_id!r} 不是军事单位卡, 不可牺牲"
            raise IllegalActionError(msg)
        counts[card_id] = counts.get(card_id, 0) + 1
    for card_id, count in counts.items():
        category = db.get(card_id).category.value
        if p.buildings.get(category, {}).get(card_id, 0) < count:
            msg = f"{card_id!r} 上工人不足 {count}, 不可牺牲"
            raise IllegalActionError(msg)
    bid = int(pending.context["bid"])
    bonus = int(pending.context.get("bonus", 0))
    strength = (
        military.units_strength(db, p, units)
        + civ_values(db, p).colonization
        + bonus
    )
    if strength < bid:
        msg = f"殖民军力 {strength} 不足承诺的出价 {bid}"
        raise IllegalActionError(msg)
    # 牺牲: 每单位 1 工人回黄点银行
    buildings = {cat: dict(slots) for cat, slots in p.buildings.items()}
    for card_id, count in counts.items():
        category = db.get(card_id).category.value
        left = buildings[category][card_id] - count
        if left > 0:
            buildings[category][card_id] = left
        else:
            del buildings[category][card_id]
    p = replace(p, buildings=buildings, yellow_bank=p.yellow_bank + len(units))
    state = replace(state, pending=state.pending[1:])
    state = replace_player(state, idx, p)
    return _grant_colony(db, state, idx, str(pending.context["territory"]))


def _grant_colony(
    db: CardDB, state: GameState, idx: int, territory: str,
) -> GameState:
    """获得殖民地: colonies 追加 + 永久黄/蓝标记入银行 + 即时效果结算.

    官方顺序(规则书 p7 注记): 永久效果的黄/蓝标记先于即时效果结算
    (可为即时效果提供标记); 负值标记下限 0(配件盒/银行不产负)。
    即时效果键: science/culture 直接加分; food/materials 按价值获得;
    population 免费 +1 人口/个(黄点银行空则不生效); military_card 抽军事
    牌(忽略手牌上限, 时代 IV 无牌可抽, 见 military.draw_military)。
    """
    card = db.get(territory)
    p = state.players[idx]
    p = replace(p, colonies=p.colonies + (territory,))
    permanent = card.territory_permanent
    p = replace(
        p,
        yellow_bank=max(0, p.yellow_bank + permanent.get("yellow_token", 0)),
        blue_bank=max(0, p.blue_bank + permanent.get("blue_token", 0)))
    immediate = card.territory_immediate
    p = replace(
        p,
        science=p.science + immediate.get("science", 0),
        culture=p.culture + immediate.get("culture", 0))
    if immediate.get("food"):
        p = economy.gain_value(db, p, "food", immediate["food"])
    if immediate.get("materials"):
        p = economy.gain_value(db, p, "resource", immediate["materials"])
    for _ in range(immediate.get("population", 0)):
        if p.yellow_bank > 0:
            p = replace(
                p, yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1)
    state = replace_player(state, idx, p)
    if immediate.get("military_card"):
        state = military.draw_military(state, idx, immediate["military_card"])
    return state
