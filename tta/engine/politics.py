"""政治阶段动作与 SeedEvent 结算(P2-T5) + 殖民竞拍与地区牌(P2-T7)
+ 侵略与防御响应(P2-T8).

每回合限 1 政治行动: POLITICS 相位 legal = 政治动作 + SkipPolitics(见
legal.py), 任一政治动作结算后置 phase=ACTION(Julius Caesar 一次性双政治
T10)。战争(T9, 本文件末尾)与条约/退出(T10)动作类型见 actions.py。

SeedEvent 结算(规则书 p4/p7):
1. 军事手牌中的 EVENT 卡面朝下压入 future_events 顶;
2. 揭示 current_events 顶牌(空 -> 无事发生):
   - TERRITORY -> 触发殖民竞拍(本文件下半部分);
   - 其余 -> events.resolve_event 查 EVENT_HANDLERS 结算, 结算后入
     past_events;
3. 若揭示的是 current_events 最后一张: 重洗 future_events(按时代分组,
   早时代在上, 组内 rng_shuffle)成为新 current_events。

侵略与防御响应(规则书 p4 发动侵略, P2-T8):
- PlayAggression 合法性(legal 枚举): 手牌中的 AGGRESSION 卡(handler 已
  注册)、目标非己、目标军力 < 攻击方军力("不能攻击军力等级大于或等于你
  的玩家")、无停战类条约(双方 pacts 同录 ATTACK_BLOCKING_PACTS)、军事
  行动费足够(目标领袖为甘地时费用 ×2; 攻击方领袖为甘地时不可打出侵略牌
  ——甘地卡文本"你不能打出侵略或战争牌")。
- 结算: 付军事行动费, 侵略卡从手牌揭示, 压 aggression_defense pending
  (responder=目标, context={card, attacker, attack_strength(快照),
  defense_bonus, defense_cards})。
- 防御方动作: PlayDefenseBonus(军事奖励牌防御数值)/ DiscardForStrength
  (弃 1 军事牌 +1 军力), 均可多张, 但打出+弃置总数 <= 防御方总军事行动
  点数(规则书 p4 限制); PassResponse 结束响应并判定。
- 判定: 防御方军力(civ 军力 + defense_bonus) >= attack_strength -> 侵略
  失败, 侵略牌入军事弃牌堆, 无效果; 否则侵略成功, 侵略牌入军事弃牌堆并
  结算 AGGRESSION_HANDLERS[card.handler]。结算后 phase -> ACTION(控制权
  经响应机制自然回到攻击方, current_player 全程不变)。
- 受害者的"选择"(plunder 食物/资源组合、raid 建筑、annex 殖民地、
  infiltrate 领袖/未完成奇迹)压 pending(responder=受害者), 由
  ChooseEventOption 结算(强制失去, 不可 DeclineResponse; raid 无合格
  建筑时 PassResponse 跳过该次摧毁)。

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

条约、体面退出与 Caesar 双政治(规则书 p4, P2-T10):
- ProposePact(card_id, target, side)(3-4 人; 2 人局不生成): 展示条约牌
  (离手), 压 pact_offer pending(responder=target, context={card,
  proposer, side}); side 为提出者自己扮演的侧("A"/"B"), 对称条约仅举 "A"
  (两侧效果相同, 减动作空间)。
- PactAccept/PactReject: 拒绝 -> 牌回提出者手, 其本回合不能再执行政治行动
  (phase -> ACTION, Caesar 不覆盖, 规则书 p4 明示); 接受 -> 双方既有条约
  立即失效(入 removed, "无论是与对方还是与其他玩家缔结的"), 双方 pacts
  各追加 (卡 id, 本方侧), 静态/被动效果经 civ.pact_bonuses 合成。
- 条约效果(卡牌数值表 p3): 静态类入 civ.PACT_STATIC_BONUSES(停战类同时
  入 ATTACK_BLOCKING_PACTS); 开放边境"攻击者 +2 军力"于攻击快照时加成
  (OPEN_BORDERS_ATTACK_BONUS); 军事同盟/军事保护承诺"若一方攻击另一方,
  条约终止"于 PlayAggression/DeclareWar 时先移除再快照
  (ATTACK_ENDING_PACTS); 主权丧失"无人能对 B 宣战"于 _war_actions 豁免;
  国际贸易协议 A 侧 +1 资源生产于 turn 回合末生产钩子; trade_routes
  (每回合食物/资源置换)与 scientific_cooperation(每回合研发折扣)为
  每回合选择类互动, P3-DEFERRED(可缔约但无效果, 卡 text 保留完整描述)。
- CancelPact(card_id)(3-4 人): 你为当事人的一项条约从双方 pacts 移除,
  卡入 removed, 效果终止。
- Resign(时代 IV 不可用): 手牌入弃牌堆, 游戏区域卡牌入 removed(进行中
  奇迹已付阶段蓝点退回供给区); 与其有关的条约双方移除; 对其宣战者的
  战争牌入 removed 且宣战者 +7 文化; 黄/蓝标记与工人随文明退出冻结保留
  (守恒口径, 不再参与游戏)。只剩 1 人 -> 游戏立即结束, 该玩家直接判胜
  (不比文化, final_scores 其严格最高); 仍有 >=2 人继续, 轮换跳过其座位
  (turn.proceed), 事件比较与目标枚举排除已退出者(state.active_indices)。
- Julius Caesar: 领袖在场且 caesar_used=False 时, 政治动作结算后
  (seed_event/侵略判定/宣战/条约接受/取缔)phase 回 POLITICS 而非 ACTION
  并置 caesar_used=True(一次性); 第二次政治动作后 -> ACTION。
"""

from collections.abc import Callable
from dataclasses import replace

from tta.engine import economy, effects, events, military
from tta.engine.actions import (
    Action,
    CancelPact,
    ColonizeBid,
    ColonizePass,
    ColonizePlayBonus,
    ColonizeSacrifice,
    DeclareWar,
    DiscardForStrength,
    IllegalActionError,
    PlayAggression,
    PlayDefenseBonus,
    ProposePact,
    Resign,
    SeedEvent,
)
from tta.engine.civ import civ_values
from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    Age,
    CardCategory,
    Phase,
)
from tta.engine.model import CardDB, CardDefinition
from tta.engine.rng import rng_shuffle
from tta.engine.state import (
    GameState,
    PendingEffect,
    PlayerState,
    acting_index,
    active_indices,
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


def politics_actions(db: CardDB, state: GameState) -> list[Action]:
    """POLITICS 相位可用政治动作(不含 SkipPolitics, 由 legal 追加).

    SeedEvent(军事手牌中的 EVENT 卡) + PlayAggression(军事手牌中的
    AGGRESSION 卡 × 合法目标) + DeclareWar(军事手牌中的 WAR 卡 × 合法
    目标) + ProposePact/CancelPact(3-4 人, 条约) + Resign(时代 IV 外)。
    RULES-CHECK(规则书 p4 未禁止): 时代 IV 无军事牌可抽, 但手牌中已有的
    事件牌仍可筹划、侵略牌仍可打出; 条约动作同理(仅 Resign 明示 IV 禁用)。
    """
    idx = state.current_player
    p = state.players[idx]
    actions: list[Action] = [
        SeedEvent(card_id)
        for card_id in dict.fromkeys(p.hand_military)
        if db.get(card_id).category is CardCategory.EVENT
    ]
    actions.extend(_aggression_actions(db, state, idx, p))
    actions.extend(_war_actions(db, state, idx, p))
    actions.extend(_pact_actions(db, state, idx, p))
    if state.age is not Age.IV:
        # 规则书 p4: 你不能在时代 IV 退出游戏
        actions.append(Resign())
    return actions


def _aggression_actions(
    db: CardDB, state: GameState, idx: int, p: PlayerState,
) -> list[PlayAggression]:
    """PlayAggression 枚举(合法性口径见模块 docstring 侵略节)."""
    if p.leader == effects.LEADER_GANDHI:
        # 甘地卡文本: 你不能打出侵略或战争牌
        return []
    attacker_strength = civ_values(db, p, state.players, idx).strength
    actions: list[PlayAggression] = []
    for card_id in dict.fromkeys(p.hand_military):
        card = db.get(card_id)
        if card.category is not CardCategory.AGGRESSION:
            continue
        # 未注册处理器的侵略牌不可打出(与行动卡同口径)
        if card.handler not in AGGRESSION_HANDLERS:
            continue
        for target, tp in enumerate(state.players):
            if target == idx or tp.resigned:
                continue
            if _pact_blocks_attack(p, tp):
                continue
            # 规则书 p4: 不能攻击军力等级大于或等于你的玩家
            if civ_values(db, tp, state.players, target).strength >= attacker_strength:
                continue
            if p.military_actions < aggression_cost(tp, card):
                continue
            actions.append(PlayAggression(card_id, target))
    return actions


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
        return _after_political_action(state, idx)
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
    return _after_political_action(state, idx)


def _after_political_action(state: GameState, idx: int) -> GameState:
    """政治动作结算后的相位: Julius Caesar 一次性双政治.

    领袖为 julius_caesar 且 caesar_used=False -> phase 回 POLITICS 并置
    caesar_used=True(本局一次); 否则 -> ACTION(每回合限 1 政治行动)。
    条约拒绝(规则书 p4 明示本回合不能再政治行动)与体面退出不经此钩子。
    """
    p = state.players[idx]
    if p.leader == effects.LEADER_JULIUS_CAESAR and not p.caesar_used:
        state = replace_player(state, idx, replace(p, caesar_used=True))
        return replace(state, phase=Phase.POLITICS)
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


# --- 侵略与防御响应(规则书 p4 发动侵略) ------------------------------------------

KIND_AGGRESSION_DEFENSE = "aggression_defense"
"""侵略防御响应 pending: responder=目标, context={card, attacker,
attack_strength(快照), defense_bonus, defense_cards}."""

KIND_AGGRESSION_PLUNDER = "aggression_plunder"
"""plunder 受害者选择 pending: 失去共 amount 食物/资源(组合自选, 强制)."""

KIND_AGGRESSION_RAID = "aggression_raid"
"""raid 受害者选择 pending: 摧毁 1 个 <= max_age 级城市建筑(强制; 无合格
建筑时 PassResponse 跳过)。链式多张时 context["loot"] 累计已毁造价。"""

KIND_AGGRESSION_ANNEX = "aggression_annex"
"""annex 受害者选择 pending: 选 1 个殖民地转交攻击方(强制)."""

KIND_AGGRESSION_INFILTRATE = "aggression_infiltrate"
"""infiltrate 受害者选择 pending: 弃 1 个领袖或 1 个未完成奇迹(强制)."""

AGGRESSION_CHOICE_KINDS: frozenset[str] = frozenset({
    KIND_AGGRESSION_PLUNDER,
    KIND_AGGRESSION_RAID,
    KIND_AGGRESSION_ANNEX,
    KIND_AGGRESSION_INFILTRATE,
})
"""受害者选择类侵略 pending kind(ChooseEventOption 路由, 见
apply_aggression_choice); 均为强制失去, 不可 DeclineResponse。"""

ATTACK_BLOCKING_PACTS: frozenset[str] = frozenset({
    "peace_treaty", "acceptance_of_supremacy", "loss_of_sovereignty",
})
"""停战类条约(条约文本含"不可攻击"): 生效中不可互相攻击/宣战.
缔约双方 pacts 各录 (卡 id, 本方侧), 判定取卡 id 交集。"""

ATTACK_ENDING_PACTS: frozenset[str] = frozenset({
    "military_alliance", "promise_of_military_protection",
})
"""攻击终止类条约(卡牌数值表 p3: "若一方攻击另一方, 条约终止"):
一方攻击另一方时立即从游戏中移除(规则书 p4 侵略节), 先移除再快照。"""

OPEN_BORDERS_PACT = "open_borders_agreement"
OPEN_BORDERS_ATTACK_BONUS = 2
"""开放边境协议: 若一方攻击另一方, 攻击者 +2 军力(卡牌数值表 p3)."""

LOSS_OF_SOVEREIGNTY_PACT = "loss_of_sovereignty"
"""主权丧失: 除双方互不攻击外, 无人能对 B 侧宣战(卡牌数值表 p3)."""

GANDHI_COST_MULTIPLIER = 2
"""甘地被动: 针对其文明的侵略/战争花费双倍军事行动(卡文本)."""

_TECH_LEVEL = {Age.A: 1, Age.I: 2, Age.II: 3, Age.III: 4}
"""卡牌等级(级 = 时代序, 时代 A 计 1 级; 与 effects._TECH_LEVEL 同口径)."""

INFILTRATE_OPTION_LEADER = "leader"
"""infiltrate 受害者选择: 弃当前领袖(其余 option 值为未完成奇迹卡 id)."""

RAID_REQUIREMENTS: dict[str, tuple[Age, ...]] = {
    "raid_i": (Age.I,),
    "raid_ii": (Age.II, Age.I),
    "raid_iii": (Age.III, Age.II),
}
"""raid 摧毁序列: 依次各摧毁 1 个 <= 该级(含 A)的城市建筑.
卡牌数值表 p3: raid 受害图标为城市建筑图标(不含农场/矿场)。"""

_AGE_LEVEL_ORDER = (Age.A, Age.I, Age.II, Age.III)
"""raid 等级比较的时代序(IV 为终局标记, 卡牌不出现)."""

AggressionHandler = Callable[[GameState, CardDB, int, int], GameState]
"""侵略效果处理器签名: (state, db, attacker, victim) -> 新 state."""

AGGRESSION_HANDLERS: dict[str, AggressionHandler] = {}
"""侵略效果注册表: handler 名(= 卡 id) -> 处理器(注册见文件末尾)."""


def aggression_cost(target: PlayerState, card: CardDefinition) -> int:
    """侵略/战争军事行动费: 目标领袖为甘地时双倍(卡文本)."""
    cost = card.military_cost
    if target.leader == effects.LEADER_GANDHI:
        cost *= GANDHI_COST_MULTIPLIER
    return cost


def _pact_blocks_attack(attacker: PlayerState, target: PlayerState) -> bool:
    """停战类条约生效中(双方 pacts 同录同一条约卡 id)则不可攻击."""
    return bool(
        ATTACK_BLOCKING_PACTS
        & {card_id for card_id, _ in attacker.pacts}
        & {card_id for card_id, _ in target.pacts})


def _shared_pact(a: PlayerState, b: PlayerState, card_id: str) -> bool:
    """双方 pacts 同录指定条约卡 id(缔约关系)."""
    return (
        any(cid == card_id for cid, _ in a.pacts)
        and any(cid == card_id for cid, _ in b.pacts))


def _end_pacts_on_attack(state: GameState, attacker: int, target: int) -> GameState:
    """攻击终止类条约: 攻击方与目标缔约的此类条约立即从游戏中移除.

    规则书 p4 侵略节: "如果你和你的对手之间有一张只要你攻击就会停止生效
    的条约牌, 立即将其从游戏中移除。"先移除再计算攻击快照(攻击不携带
    即将终止条约的加成)。
    """
    for card_id in ATTACK_ENDING_PACTS:
        if _shared_pact(state.players[attacker], state.players[target], card_id):
            state = _remove_pact(state, card_id)
    return state


def _attack_strength_snapshot(
    db: CardDB, state: GameState, attacker: int, target: int,
) -> int:
    """攻击方军力快照 = civ 军力 + 开放边境攻击加成(与目标缔约时 +2)."""
    strength = civ_values(db, state.players[attacker], state.players, attacker).strength
    if _shared_pact(
            state.players[attacker], state.players[target], OPEN_BORDERS_PACT):
        strength += OPEN_BORDERS_ATTACK_BONUS
    return strength


def play_aggression(
    db: CardDB, state: GameState, action: PlayAggression,
) -> GameState:
    """PlayAggression 结算: 付军事行动费, 揭示侵略卡, 压防御响应 pending.

    合法性(目标军力严格更低/费用/条约/甘地)由 legal 保证; 攻击军力快照
    入 context(响应期仅防御方变动, 判定以快照为准); 攻击终止类条约先移除
    再快照。phase 保持 POLITICS(pending 响应优先), 判定后由
    _resolve_defense 经 _after_political_action 置相位。
    """
    idx = state.current_player
    p = state.players[idx]
    card = db.get(action.card_id)
    cost = aggression_cost(state.players[action.target], card)
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    p = replace(
        p, hand_military=tuple(hand),
        military_actions=p.military_actions - cost)
    state = replace_player(state, idx, p)
    # 攻击终止类条约(军事同盟/军事保护承诺)立即移除(先移除再快照)
    state = _end_pacts_on_attack(state, idx, action.target)
    pending = PendingEffect(
        KIND_AGGRESSION_DEFENSE, 0, responder=action.target,
        context={
            "card": action.card_id,
            "attacker": idx,
            "attack_strength": _attack_strength_snapshot(
                db, state, idx, action.target),
            "defense_bonus": 0,
            "defense_cards": 0,
        })
    return replace(state, pending=state.pending + (pending,))


def _bump_defense(
    state: GameState, idx: int, card_id: str, bonus: int,
) -> GameState:
    """防御方用牌公共: 手牌移除入军事弃牌堆, defense_bonus/defense_cards 累加."""
    p = state.players[idx]
    hand = list(p.hand_military)
    hand.remove(card_id)
    state = replace_player(state, idx, replace(p, hand_military=tuple(hand)))
    state = replace(
        state, military_discard=state.military_discard + (card_id,))
    pending = state.pending[0]
    context = dict(pending.context)
    context["defense_bonus"] = int(context.get("defense_bonus", 0)) + bonus
    context["defense_cards"] = int(context.get("defense_cards", 0)) + 1
    return replace(
        state, pending=(replace(pending, context=context),) + state.pending[1:])


def play_defense_bonus(
    db: CardDB, state: GameState, action: PlayDefenseBonus,
) -> GameState:
    """PlayDefenseBonus 结算: 奖励牌防御数值临时加入防御方军力."""
    return _bump_defense(
        state, acting_index(state), action.card_id,
        db.get(action.card_id).defense_bonus)


def discard_for_strength(
    db: CardDB, state: GameState, action: DiscardForStrength,
) -> GameState:
    """DiscardForStrength 结算: 面朝下弃 1 军事牌, 临时 +1 军力."""
    return _bump_defense(state, acting_index(state), action.card_id, 1)


def pass_response(db: CardDB, state: GameState) -> GameState:
    """PassResponse 结算: 防御判定(aggression_defense)或 raid 跳过摧毁.

    合法性由 legal 保证(仅这两类 pending 生成 PassResponse)。
    """
    if not state.pending:  # pragma: no cover - legal 已排除
        msg = "当前无可响应的 pending"
        raise IllegalActionError(msg)
    pending = state.pending[0]
    if pending.kind == KIND_AGGRESSION_DEFENSE:
        return _resolve_defense(db, state, pending)
    if pending.kind == KIND_AGGRESSION_RAID:
        state = replace(state, pending=state.pending[1:])
        return _raid_advance(
            db, state, int(pending.context["attacker"]),
            int(pending.context["loot"]))
    msg = f"pending {pending.kind!r} 不接受 PassResponse"  # pragma: no cover
    raise IllegalActionError(msg)  # pragma: no cover


def _resolve_defense(
    db: CardDB, state: GameState, pending: PendingEffect,
) -> GameState:
    """侵略判定: 防御方军力(civ + 奖励) >= 攻击快照 -> 失败; 否则结算效果.

    两种结果侵略牌均入军事弃牌堆(规则书 p4: 弃置相应的侵略牌); 结算后
    经 _after_political_action 定相位(每回合限 1 政治行动; Caesar 一次性
    双政治可回 POLITICS)。
    """
    context = pending.context
    card_id = str(context["card"])
    attacker = int(context["attacker"])
    victim = acting_index(state)
    defense = (
        civ_values(db, state.players[victim], state.players, victim).strength
        + int(context["defense_bonus"])
    )
    state = replace(
        state, pending=state.pending[1:],
        military_discard=state.military_discard + (card_id,))
    if defense < int(context["attack_strength"]):
        handler = AGGRESSION_HANDLERS[db.get(card_id).handler]
        state = handler(state, db, attacker, victim)
    # 判定完成 -> 政治行动结算(Caesar 一次性双政治可回 POLITICS)
    return _after_political_action(state, attacker)


def apply_aggression_choice(
    db: CardDB, state: GameState, option: str,
) -> GameState:
    """受害者选择类侵略 pending 的 ChooseEventOption 结算(强制失去)."""
    if not state.pending:  # pragma: no cover - legal 已排除
        msg = "无待结算的侵略 pending"
        raise ValueError(msg)
    pending = state.pending[0]
    if pending.kind == KIND_AGGRESSION_PLUNDER:
        return _plunder_settle(db, state, pending, option)
    if pending.kind == KIND_AGGRESSION_RAID:
        return _raid_destroy(db, state, pending, option)
    if pending.kind == KIND_AGGRESSION_ANNEX:
        return _annex_settle(db, state, pending, option)
    if pending.kind == KIND_AGGRESSION_INFILTRATE:
        return _infiltrate_settle(db, state, pending, option)
    msg = f"pending {pending.kind!r} 不接受 ChooseEventOption"  # pragma: no cover
    raise ValueError(msg)  # pragma: no cover


# --- 侵略效果处理器(handler 名 = 卡 id) -----------------------------------------


def _enslave_i(state: GameState, db: CardDB, attacker: int, victim: int) -> GameState:
    """enslave_i: 受害者 -1 人口; 攻击方 +2 食物 +2 资源(独立效果)."""
    state = replace_player(
        state, victim, events.lose_population(state.players[victim], 1))
    p = state.players[attacker]
    p = economy.gain_tokens(db, p, "food", 2)
    p = economy.gain_tokens(db, p, "resource", 2)
    return replace_player(state, attacker, p)


def _plunder(amount: int) -> AggressionHandler:
    """plunder 工厂: 压受害者选择 pending(失去共 amount 食物/资源)."""

    def handler(
        state: GameState, db: CardDB, attacker: int, victim: int,
    ) -> GameState:
        pending = PendingEffect(
            KIND_AGGRESSION_PLUNDER, 0, responder=victim,
            context={"attacker": attacker, "amount": amount})
        return replace(state, pending=state.pending + (pending,))

    return handler


def plunder_options(amount: int) -> tuple[str, ...]:
    """plunder 合法 option: 食物/资源组合, 按价值合计 amount(恒可执行,
    不足由 settle_loss 封顶)。"""
    options: list[str] = []
    for food in range(amount, -1, -1):
        resource = amount - food
        parts: list[str] = []
        if food:
            parts.append(f"food:{food}")
        if resource:
            parts.append(f"resource:{resource}")
        options.append(",".join(parts))
    return tuple(options)


def _plunder_settle(
    db: CardDB, state: GameState, pending: PendingEffect, option: str,
) -> GameState:
    """plunder 选择结算: 受害者按组合失去(不足封顶), 攻击方获得实失量."""
    victim = acting_index(state)
    attacker = int(pending.context["attacker"])
    state = replace(state, pending=state.pending[1:])
    for kind, amount in events.parse_mix(option):
        p, paid = economy.settle_loss(db, state.players[victim], kind, amount)
        state = replace_player(state, victim, p)
        if paid:
            a = economy.gain_value(db, state.players[attacker], kind, paid)
            state = replace_player(state, attacker, a)
    return state


def raid_eligible_building_ids(
    db: CardDB, p: PlayerState, max_age: Age,
) -> list[str]:
    """raid 可摧毁的城市建筑卡 id(有工人且等级 <= max_age, 含 A)."""
    limit = _AGE_LEVEL_ORDER.index(max_age)
    ids: list[str] = []
    for category in sorted(URBAN_CATEGORIES, key=lambda c: c.value):
        for card_id, workers in sorted(p.buildings.get(category.value, {}).items()):
            if workers < 1:
                continue
            if _AGE_LEVEL_ORDER.index(db.get(card_id).age) <= limit:
                ids.append(card_id)
    return ids


def _raid(requirements: tuple[Age, ...]) -> AggressionHandler:
    """raid 工厂: 按摧毁序列压链式 pending(loot 累计已毁建筑造价)."""

    def handler(
        state: GameState, db: CardDB, attacker: int, victim: int,
    ) -> GameState:
        chain = tuple(
            PendingEffect(
                KIND_AGGRESSION_RAID, 0, responder=victim,
                context={
                    "attacker": attacker, "max_age": max_age.value, "loot": 0,
                })
            for max_age in requirements
        )
        return replace(state, pending=state.pending + chain)

    return handler


def _raid_destroy(
    db: CardDB, state: GameState, pending: PendingEffect, option: str,
) -> GameState:
    """raid 摧毁结算: 所选建筑 -1 工人回空闲池, loot 累加其造价(卡面费,
    规则书 p4: 涉及卡牌费用时不作任何修正), 链尽后攻击方 +ceil(loot/2) 资源。
    """
    victim = acting_index(state)
    attacker = int(pending.context["attacker"])
    card = db.get(option)
    p = state.players[victim]
    buildings = dict(p.buildings)
    slots = dict(buildings[card.category.value])
    left = slots[option] - 1
    if left > 0:
        slots[option] = left
    else:
        del slots[option]
    buildings[card.category.value] = slots
    state = replace_player(
        state, victim,
        replace(p, buildings=buildings, worker_pool=p.worker_pool + 1))
    loot = int(pending.context["loot"]) + card.build_cost
    state = replace(state, pending=state.pending[1:])
    return _raid_advance(db, state, attacker, loot)


def _raid_advance(
    db: CardDB, state: GameState, attacker: int, loot: int,
) -> GameState:
    """raid 链推进: 下一段 pending 继承 loot; 链尽攻击方 +ceil(loot/2) 资源."""
    if state.pending and state.pending[0].kind == KIND_AGGRESSION_RAID:
        nxt = state.pending[0]
        context = dict(nxt.context)
        context["loot"] = loot
        return replace(
            state, pending=(replace(nxt, context=context),) + state.pending[1:])
    if loot > 0:
        p = economy.gain_value(db, state.players[attacker], "resource",
                               (loot + 1) // 2)
        state = replace_player(state, attacker, p)
    return state


def _annex_ii(state: GameState, db: CardDB, attacker: int, victim: int) -> GameState:
    """annex_ii: 受害者有殖民地时压选择 pending(无则无效果)."""
    if not state.players[victim].colonies:
        return state
    pending = PendingEffect(
        KIND_AGGRESSION_ANNEX, 0, responder=victim,
        context={"attacker": attacker})
    return replace(state, pending=state.pending + (pending,))


def _annex_settle(
    db: CardDB, state: GameState, pending: PendingEffect, option: str,
) -> GameState:
    """annex 选择结算: 殖民地转移(含永久效果); 黄/蓝标记受害者归还、
    攻击方自配件盒取得(与 politics._grant_colony 获得时口径互逆, 下限 0)。
    """
    victim = acting_index(state)
    attacker = int(pending.context["attacker"])
    state = replace(state, pending=state.pending[1:])
    permanent = db.get(option).territory_permanent
    yellow = permanent.get("yellow_token", 0)
    blue = permanent.get("blue_token", 0)
    p = state.players[victim]
    colonies = list(p.colonies)
    colonies.remove(option)
    p = replace(
        p, colonies=tuple(colonies),
        yellow_bank=max(0, p.yellow_bank - yellow),
        blue_bank=max(0, p.blue_bank - blue))
    state = replace_player(state, victim, p)
    a = state.players[attacker]
    a = replace(
        a, colonies=a.colonies + (option,),
        yellow_bank=max(0, a.yellow_bank + yellow),
        blue_bank=max(0, a.blue_bank + blue))
    return replace_player(state, attacker, a)


def _infiltrate_ii(state: GameState, db: CardDB, attacker: int, victim: int) -> GameState:
    """infiltrate_ii: 受害者有领袖或未完成奇迹时压选择 pending(无则无效果)."""
    p = state.players[victim]
    if p.leader is None and p.wonder_progress is None:
        return state
    pending = PendingEffect(
        KIND_AGGRESSION_INFILTRATE, 0, responder=victim,
        context={"attacker": attacker})
    return replace(state, pending=state.pending + (pending,))


def infiltrate_options(p: PlayerState) -> list[str]:
    """infiltrate 合法 option: "leader"(有领袖时)/未完成奇迹卡 id."""
    options: list[str] = []
    if p.leader is not None:
        options.append(INFILTRATE_OPTION_LEADER)
    if p.wonder_progress is not None:
        options.append(p.wonder_progress[0])
    return options


def _infiltrate_settle(
    db: CardDB, state: GameState, pending: PendingEffect, option: str,
) -> GameState:
    """infiltrate 选择结算: 弃领袖(入弃牌堆)或未完成奇迹(已付阶段蓝点
    退回供给区后入 removed, 同时代结束过期口径); 攻击方 +3 文化/级。"""
    victim = acting_index(state)
    attacker = int(pending.context["attacker"])
    state = replace(state, pending=state.pending[1:])
    p = state.players[victim]
    if option == INFILTRATE_OPTION_LEADER:
        card_id = str(p.leader)
        level = _TECH_LEVEL[db.get(card_id).age]
        state = replace(state, discard=state.discard + (card_id,))
        p = replace(p, leader=None)
    else:
        card_id, stages_done = p.wonder_progress  # type: ignore[misc]
        level = _TECH_LEVEL[db.get(card_id).age]
        p = replace(p, wonder_progress=None,
                    blue_bank=p.blue_bank + stages_done)
        state = replace(state, removed=state.removed + (card_id,))
    state = replace_player(state, victim, p)
    a = state.players[attacker]
    return replace_player(
        state, attacker, replace(a, culture=a.culture + 3 * level))


def _spy_ii(state: GameState, db: CardDB, attacker: int, victim: int) -> GameState:
    """spy_ii: 受害者 -5 科技(下限 0); 攻击方 +等量文化(PDF: Scores same
    amount, 按实失量)。"""
    p = state.players[victim]
    lost = min(5, p.science)
    state = replace_player(state, victim, replace(p, science=p.science - lost))
    a = state.players[attacker]
    return replace_player(state, attacker, replace(a, culture=a.culture + lost))


def _armed_intervention_iii(
    state: GameState, db: CardDB, attacker: int, victim: int,
) -> GameState:
    """armed_intervention_iii: 受害者 -7 文化(下限 0); 攻击方 +7 文化
    (卡面为两个独立效果, 攻击方收益不随受害者实失量封顶)。"""
    p = state.players[victim]
    state = replace_player(
        state, victim, replace(p, culture=max(0, p.culture - 7)))
    a = state.players[attacker]
    return replace_player(state, attacker, replace(a, culture=a.culture + 7))


AGGRESSION_HANDLERS.update({
    "enslave_i": _enslave_i,
    "plunder_i": _plunder(3),
    "plunder_ii": _plunder(5),
    "plunder_iii": _plunder(7),
    "raid_i": _raid(RAID_REQUIREMENTS["raid_i"]),
    "raid_ii": _raid(RAID_REQUIREMENTS["raid_ii"]),
    "raid_iii": _raid(RAID_REQUIREMENTS["raid_iii"]),
    "annex_ii": _annex_ii,
    "infiltrate_ii": _infiltrate_ii,
    "spy_ii": _spy_ii,
    "armed_intervention_iii": _armed_intervention_iii,
})


# --- 战争宣告与结算(规则书 p3-p4 战争, P2-T9) -------------------------------------

KIND_WAR_SEIZE = "war_seize_tech"
"""科技之战胜者夺取特殊科技 pending: responder=胜者, context={loser,
options(可夺取的特殊科技卡 id, 逗号连接快照)}; 可放弃(DeclineResponse)。"""

WAR_TERRITORY_BASE = 1
"""领土之战黄点基数(PDF: -黄点 equal to 1 + 1/5 adv. of winner)."""

WAR_TERRITORY_DIVISOR = 5
"""领土之战军力差除数(向下取整)."""

WAR_CULTURE_BASE = 5
"""文化之战文化基数(PDF: -文化 equal to 5 + adv. of winner)."""

WarHandler = Callable[[GameState, CardDB, int, int, int], GameState]
"""战争效果处理器签名: (state, db, winner, loser, 军力差) -> 新 state."""

WAR_HANDLERS: dict[str, WarHandler] = {}
"""战争效果注册表: handler 名(= 卡 id) -> 处理器(注册见文件末尾)."""


def _war_actions(
    db: CardDB, state: GameState, idx: int, p: PlayerState,
) -> list[DeclareWar]:
    """DeclareWar 枚举(规则书 p4 宣告战争).

    合法性: 手牌中的 WAR 卡(handler 已注册)、目标非己、无停战类条约
    (双方 pacts 同录 ATTACK_BLOCKING_PACTS)、军事行动费足够(目标领袖为
    甘地时费用 ×2; 宣告方领袖为甘地时不可打出战争牌——甘地卡文本"你不
    能打出侵略或战争牌")、最后的游戏轮不可宣告(规则书 p4 限制)。
    与侵略不同: 规则书未禁止向军力等级大于或等于你的玩家宣战。
    """
    if state.last_round:
        # 规则书 p4: 你不能在最后的游戏轮宣告战争
        return []
    if p.leader == effects.LEADER_GANDHI:
        return []
    actions: list[DeclareWar] = []
    for card_id in dict.fromkeys(p.hand_military):
        card = db.get(card_id)
        if card.category is not CardCategory.WAR:
            continue
        # 未注册处理器的战争牌不可打出(与侵略牌同口径)
        if card.handler not in WAR_HANDLERS:
            continue
        for target, tp in enumerate(state.players):
            if target == idx or tp.resigned:
                continue
            if _pact_blocks_attack(p, tp):
                continue
            if _sovereignty_blocks_war(tp):
                # 主权丧失: 无人能对 B 侧宣战(卡牌数值表 p3)
                continue
            if p.military_actions < aggression_cost(tp, card):
                continue
            actions.append(DeclareWar(card_id, target))
    return actions


def _sovereignty_blocks_war(target: PlayerState) -> bool:
    """目标持有主权丧失 B 侧 -> 无人能对其宣战(含缔约方外的第三方)."""
    return (LOSS_OF_SOVEREIGNTY_PACT, "B") in target.pacts


def declare_war(db: CardDB, state: GameState, action: DeclareWar) -> GameState:
    """DeclareWar 结算: 付军事行动费, 战争牌手牌 -> declared_wars(在途).

    合法性由 legal 保证(见 _war_actions)。战争在宣告者的下个回合开始
    阶段结算(规则书 p4, 见 resolve_declared_wars), 宣告当回合不结算;
    phase -> ACTION(每回合限 1 政治行动)。
    """
    idx = state.current_player
    p = state.players[idx]
    card = db.get(action.card_id)
    cost = aggression_cost(state.players[action.target], card)
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    p = replace(
        p, hand_military=tuple(hand),
        military_actions=p.military_actions - cost,
        declared_wars=p.declared_wars + ((action.card_id, action.target),))
    state = replace_player(state, idx, p)
    # 攻击终止类条约(军事同盟/军事保护承诺)立即移除
    state = _end_pacts_on_attack(state, idx, action.target)
    return _after_political_action(state, idx)


def resolve_declared_wars(db: CardDB, state: GameState) -> GameState:
    """回合开始阶段结算当前玩家 declared_wars 中的全部战争(逐张).

    规则书 p3 回合流程: 补充卡牌列 -> 结算战争 -> 公开专属阵型(本函数由
    turn.proceed 在补牌后、公开阵型前调用)。比较双方 civ.strength(纯军力
    等级; 规则书 p3 注意: 结算战争时, 双方都不可以打出军事奖励牌来增加
    自己的军力等级)。平局无效果; 有胜负按战争牌效果结算(军力差 = 胜者
    军力优势)。无论如何, 战争牌最终都入军事弃牌堆。
    临时军力加成(事件给的临时军力)在比较时应计入——本阶段无此类事件,
    暂仅 civ.strength(规则书 p3: 可先附加奖励再进行战争的结算)。
    """
    idx = state.current_player
    while state.players[idx].declared_wars:
        card_id, target = state.players[idx].declared_wars[0]
        attacker_strength = _attack_strength_snapshot(db, state, idx, target)
        target_strength = civ_values(
            db, state.players[target], state.players, target).strength
        # 战争牌无论结果均入军事弃牌堆, declared_wars 移除该卡
        p = state.players[idx]
        state = replace_player(
            state, idx, replace(p, declared_wars=p.declared_wars[1:]))
        state = replace(
            state, military_discard=state.military_discard + (card_id,))
        if attacker_strength == target_strength:
            # 规则书 p3: 双方军力相等, 战争的结算不会产生任何效果
            continue
        if attacker_strength > target_strength:
            winner, loser = idx, target
        else:
            winner, loser = target, idx
        diff = abs(attacker_strength - target_strength)
        handler = WAR_HANDLERS[db.get(card_id).handler]
        state = handler(state, db, winner, loser, diff)
    return state


def war_seize_options(
    db: CardDB, winner: PlayerState, loser: PlayerState,
) -> list[str]:
    """科技之战可夺取的特殊科技卡 id(败方 developed 中的 SPECIAL).

    规则书 p3: 胜利者不能夺取与自己游戏区域或手牌中同名的特殊科技牌。
    """
    blocked = set(winner.developed) | set(winner.hand_civil)
    return [
        card_id for card_id in loser.developed
        if db.get(card_id).category is CardCategory.SPECIAL
        and card_id not in blocked
    ]


def apply_war_seize(
    db: CardDB, state: GameState, option: str,
) -> GameState:
    """war_seize_tech pending 的 ChooseEventOption 结算(可选, 已选择夺取).

    夺取的特殊科技免费加入胜者游戏区域(不触发研发即时收益); 若与胜者
    游戏区域中同类型的特殊科技并存, 保留等级较高者并弃置另一张
    (规则书 p3; 等级比较与 apply._replace_lower_special 同口径: 先比
    时代序, 同级按 cost_science; 此处按战争规则文本弃置入民政弃牌堆)。
    """
    pending = state.pending[0]
    winner = acting_index(state)
    loser = int(pending.context["loser"])
    state = replace(state, pending=state.pending[1:])
    lp = state.players[loser]
    loser_developed = list(lp.developed)
    loser_developed.remove(option)
    state = replace_player(
        state, loser, replace(lp, developed=tuple(loser_developed)))
    wp = state.players[winner]
    state = replace_player(
        state, winner, replace(wp, developed=wp.developed + (option,)))
    return _war_seize_replace_same_type(db, state, winner, option)


def _war_seize_replace_same_type(
    db: CardDB, state: GameState, winner: int, new_card_id: str,
) -> GameState:
    """夺取后同类型特殊科技两张并存 -> 保留等级较高者, 弃置另一张."""
    new_type = db.get(new_card_id).special_type
    p = state.players[winner]
    same = [
        card_id for card_id in p.developed
        if db.get(card_id).category is CardCategory.SPECIAL
        and db.get(card_id).special_type is new_type
    ]
    if len(same) < 2:
        return state

    def _level(card_id: str) -> tuple[int, int]:
        card = db.get(card_id)
        return (_AGE_LEVEL_ORDER.index(card.age), card.cost_science)

    lower = min(same, key=_level)
    developed = list(p.developed)
    developed.remove(lower)
    state = replace_player(
        state, winner, replace(p, developed=tuple(developed)))
    return replace(state, discard=state.discard + (lower,))


# --- 战争效果处理器(handler 名 = 卡 id) -----------------------------------------


def _war_over_technology(
    state: GameState, db: CardDB, winner: int, loser: int, diff: int,
) -> GameState:
    """war_over_technology_ii: 败者 -科技 = 军力差(下限 0), 胜者 +实失量;
    胜者并可夺取对方 1 张特殊科技牌(压 war_seize_tech pending, 可放弃;
    无可夺取目标时不压)。"""
    lp = state.players[loser]
    lost = min(diff, lp.science)
    state = replace_player(state, loser, replace(lp, science=lp.science - lost))
    wp = state.players[winner]
    state = replace_player(
        state, winner, replace(wp, science=wp.science + lost))
    options = war_seize_options(db, state.players[winner], state.players[loser])
    if options:
        pending = PendingEffect(
            KIND_WAR_SEIZE, 0, responder=winner,
            context={"loser": loser, "options": ",".join(options)})
        state = replace(state, pending=state.pending + (pending,))
    return state


def _war_over_territory(
    state: GameState, db: CardDB, winner: int, loser: int, diff: int,
) -> GameState:
    """war_over_territory_ii: 败者 -黄点 = 1 + 军力差÷5(向下取整); 胜者
    获得等量(黄点银行转移, 不足则全给——规则书 p10: 从黄色人口区拿取,
    不足时尽可能拿取)。"""
    amount = WAR_TERRITORY_BASE + diff // WAR_TERRITORY_DIVISOR
    lp = state.players[loser]
    moved = min(amount, lp.yellow_bank)
    state = replace_player(
        state, loser, replace(lp, yellow_bank=lp.yellow_bank - moved))
    wp = state.players[winner]
    return replace_player(
        state, winner, replace(wp, yellow_bank=wp.yellow_bank + moved))


def _war_over_culture(
    state: GameState, db: CardDB, winner: int, loser: int, diff: int,
) -> GameState:
    """war_over_culture_iii: 败者 -文化 = 5 + 军力差(下限 0); 胜者 +实失量
    (规则书 p11: 夺取文化点数时, 对方不足则只能夺取其已有的全部点数)。"""
    lp = state.players[loser]
    lost = min(WAR_CULTURE_BASE + diff, lp.culture)
    state = replace_player(state, loser, replace(lp, culture=lp.culture - lost))
    wp = state.players[winner]
    return replace_player(
        state, winner, replace(wp, culture=wp.culture + lost))


WAR_HANDLERS.update({
    "war_over_technology_ii": _war_over_technology,
    "war_over_territory_ii": _war_over_territory,
    "war_over_culture_iii": _war_over_culture,
})


# --- 条约提议/接受/拒绝/取缔(规则书 p4, P2-T10) -------------------------------------

KIND_PACT_OFFER = "pact_offer"
"""条约提议 pending: responder=目标, context={card, proposer, side(提出者
自己扮演的侧 "A"/"B")}; 响应动作为 PactAccept/PactReject(恒可响应,
不可放弃, 不入 DECLINABLE 白名单)。"""

SYMMETRIC_PACTS: frozenset[str] = frozenset({
    "open_borders_agreement", "scientific_cooperation",
    "international_tourism", "military_alliance", "peace_treaty",
})
"""对称条约(卡牌数值表 p3 Sym=Yes): 两侧效果相同, 提议仅举侧 "A"."""

PACT_SIDE_A = "A"
PACT_SIDE_B = "B"

MIN_PLAYERS_FOR_PACTS = 3
"""条约动作(提议/取缔)的最少在局人数(规则书 p4: 2 人游戏时不允许)."""


def _pact_actions(
    db: CardDB, state: GameState, idx: int, p: PlayerState,
) -> list[Action]:
    """ProposePact/CancelPact 枚举(规则书 p4 提出条约/取缔条约).

    仅 3-4 人在局(未退出人数 >= 3)时生成; 提议目标为任一在局对手,
    非对称条约举 A/B 两个侧(提出者自己扮演的侧), 对称条约仅举 "A";
    取缔按自己 pacts 中生效的条约逐张枚举。
    """
    if len(active_indices(state)) < MIN_PLAYERS_FOR_PACTS:
        return []
    actions: list[Action] = []
    for card_id in dict.fromkeys(p.hand_military):
        if db.get(card_id).category is not CardCategory.PACT:
            continue
        sides = (PACT_SIDE_A,) if card_id in SYMMETRIC_PACTS else (
            PACT_SIDE_A, PACT_SIDE_B)
        for target, tp in enumerate(state.players):
            if target == idx or tp.resigned:
                continue
            for side in sides:
                actions.append(ProposePact(card_id, target, side))
    actions.extend(CancelPact(card_id) for card_id, _ in p.pacts)
    return actions


def propose_pact(db: CardDB, state: GameState, action: ProposePact) -> GameState:
    """ProposePact 结算: 展示条约牌(离手), 压 pact_offer pending 由对方响应.

    合法性(3-4 人/手牌 PACT 卡/目标在局非己)由 legal 保证; phase 保持
    POLITICS(pending 响应优先), 接受/拒绝后定相位。
    """
    idx = state.current_player
    p = state.players[idx]
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    state = replace_player(state, idx, replace(p, hand_military=tuple(hand)))
    pending = PendingEffect(
        KIND_PACT_OFFER, 0, responder=action.target,
        context={"card": action.card_id, "proposer": idx, "side": action.side})
    return replace(state, pending=state.pending + (pending,))


def pact_accept(db: CardDB, state: GameState) -> GameState:
    """PactAccept 结算: 双方既有条约失效, 新条约缔结并立即生效.

    规则书 p4: 任一当事人游戏区域中已有条约牌(无论与对方还是与其他玩家
    缔结)立即失效, 从游戏中移除; 新条约双方 pacts 各录 (卡 id, 本方侧),
    静态/被动效果经 civ.pact_bonuses 合成(无需即时结算)。注意: 条约不
    取消已宣告的战争(declared_wars 不受影响)。
    """
    pending = state.pending[0]
    proposer = int(pending.context["proposer"])
    responder = acting_index(state)
    card_id = str(pending.context["card"])
    side = str(pending.context["side"])
    other_side = PACT_SIDE_B if side == PACT_SIDE_A else PACT_SIDE_A
    state = replace(state, pending=state.pending[1:])
    # 双方既有条约立即失效(入 removed)
    for seat in (proposer, responder):
        for old_card_id, _ in state.players[seat].pacts:
            state = _remove_pact(state, old_card_id)
    p = state.players[proposer]
    state = replace_player(
        state, proposer, replace(p, pacts=p.pacts + ((card_id, side),)))
    q = state.players[responder]
    state = replace_player(
        state, responder, replace(q, pacts=q.pacts + ((card_id, other_side),)))
    return _after_political_action(state, proposer)


def pact_reject(db: CardDB, state: GameState) -> GameState:
    """PactReject 结算: 条约牌拿回提出者手牌, 其本回合不能再执行政治行动.

    规则书 p4 明示"本回合你不能再执行政治行动", 故 phase -> ACTION,
    Julius Caesar 双政治不覆盖此限制。
    """
    pending = state.pending[0]
    proposer = int(pending.context["proposer"])
    card_id = str(pending.context["card"])
    state = replace(state, pending=state.pending[1:])
    p = state.players[proposer]
    state = replace_player(
        state, proposer, replace(p, hand_military=p.hand_military + (card_id,)))
    return replace(state, phase=Phase.ACTION)


def cancel_pact(db: CardDB, state: GameState, action: CancelPact) -> GameState:
    """CancelPact 结算: 你为当事人的一项条约从游戏中移除(双方 pacts 同删).

    规则书 p4 取缔条约: 将该条约牌从游戏中移除, 它不再影响你和另一位
    当事人; 静态效果经 civ 合成自动终止。phase -> ACTION(Caesar 可双政治)。
    """
    state = _remove_pact(state, action.card_id)
    return _after_political_action(state, state.current_player)


def _remove_pact(state: GameState, card_id: str) -> GameState:
    """将指定条约从所有持有者 pacts 移除, 条约牌入 removed(从游戏中移除)."""
    for seat, p in enumerate(state.players):
        if any(cid == card_id for cid, _ in p.pacts):
            pacts = tuple(e for e in p.pacts if e[0] != card_id)
            state = replace_player(state, seat, replace(p, pacts=pacts))
    return replace(state, removed=state.removed + (card_id,))


# --- 体面退出(规则书 p4, P2-T10) ----------------------------------------------------

RESIGN_WAR_CULTURE = 7
"""对退出者宣战的玩家将战争牌从游戏中移除并获得的文化(规则书 p4)."""


def resign(db: CardDB, state: GameState) -> GameState:
    """Resign 结算: 当前玩家文明退出游戏(规则书 p4 体面退出).

    - 手牌入相应弃牌堆; 游戏区域卡牌(developed/领袖/已完成与进行中奇迹/
      殖民地/实体阵型/自己在途战争牌)入 removed; 进行中奇迹已付阶段蓝点
      退回供给区(与时代结束过期口径一致); 黄/蓝标记与工人随文明退出
      冻结保留(守恒口径, 不再参与游戏; 政体卡字段保留不计入 removed);
    - 与其有关的条约从双方 pacts 移除并入 removed;
    - 其他玩家向其宣告的战争: 战争牌入 removed, 宣战者 +7 文化;
    - 只剩 1 人 -> 游戏立即结束, 该玩家直接判胜(不比文化, final_scores
      其严格最高); 仍有 >=2 人 -> phase -> ACTION, 轮换跳过其座位
      (turn.proceed), 退出者回合仅剩 PassTurn(legal 保证)。
    """
    idx = state.current_player
    p = state.players[idx]
    # 手牌弃置(官方文本: "弃置你的手牌")
    state = replace(
        state,
        discard=state.discard + p.hand_civil,
        military_discard=state.military_discard + p.hand_military)
    # 游戏区域卡牌入 removed
    removed = list(state.removed)
    removed.extend(p.developed)
    removed.extend(p.wonders)
    if p.leader is not None:
        removed.append(p.leader)
    if p.wonder_progress is not None:
        removed.append(p.wonder_progress[0])
    removed.extend(p.colonies)
    if p.tactics is not None and not p.tactics_copied:
        removed.append(p.tactics)
    removed.extend(card_id for card_id, _ in p.declared_wars)
    # 与退出者有关的条约牌入 removed(下方从双方 pacts 移除)
    resigner_pact_ids = {card_id for card_id, _ in p.pacts}
    removed.extend(sorted(resigner_pact_ids))
    state = replace(state, removed=tuple(removed))
    # 进行中奇迹已付阶段蓝点退回供给区
    blue_refund = p.wonder_progress[1] if p.wonder_progress is not None else 0
    state = replace_player(state, idx, replace(
        p,
        resigned=True,
        hand_civil=(), hand_military=(), developed=(), leader=None,
        wonders=(), wonder_progress=None, colonies=(),
        tactics=None, declared_wars=(), pacts=(),
        blue_bank=p.blue_bank + blue_refund))
    # 其他玩家: 相关条约移除; 对退出者的战争牌移除且宣战者 +7 文化
    war_cards_on_resigner = [
        card_id
        for q in state.players for card_id, target in q.declared_wars
        if target == idx
    ]
    if war_cards_on_resigner:
        state = replace(
            state, removed=state.removed + tuple(war_cards_on_resigner))
    for seat, q in enumerate(state.players):
        if q.resigned:
            continue
        updates: dict = {}
        if resigner_pact_ids:
            updates["pacts"] = tuple(
                e for e in q.pacts if e[0] not in resigner_pact_ids)
        war_bonus = sum(
            RESIGN_WAR_CULTURE for _, target in q.declared_wars if target == idx)
        if war_bonus:
            updates["declared_wars"] = tuple(
                w for w in q.declared_wars if w[1] != idx)
            updates["culture"] = q.culture + war_bonus
        if updates:
            state = replace_player(state, seat, replace(q, **updates))
    # 只剩 1 人 -> 游戏立即结束, 该玩家直接判胜(不比文化)
    active = active_indices(state)
    if len(active) == 1:
        winner = active[0]
        scores = [q.culture for q in state.players]
        scores[winner] = max(scores) + 1
        return replace(state, terminal=True, final_scores=tuple(scores))
    return replace(state, phase=Phase.ACTION)
