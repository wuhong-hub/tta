"""官方回合状态机: PassTurn 后的完整回合推进.

advance(state, db) 流程:

1. 回合末阶段(当前玩家, end_of_turn): 弃多余军事牌(军事手牌上限 = civ
   军事行动点 + military_hand_extra, 超出部分压入 discard_military pending,
   由刚结束回合的玩家响应, 逐张 DiscardMilitary 弃至合规) -> 起义检定
   (is_uprising -> 跳过整个生产阶段) -> 生产(科技/文化按增速计分 ->
   腐败[资源支付, 不足用食物补, 仍不足损失到此为止] -> 食物生产 ->
   食物消耗[每缺 1 -4 文化, 文化下限 0] -> 资源生产) -> 抓军事牌
   (min(剩余红点, 3) 张; 牌堆空则切洗军事弃牌堆重置牌堆, 弃牌堆也空则
   抓不到; 时代 IV 不抓) -> 恢复行动点(= civ 总值, 同时清零
   tactics_this_turn; rebellion 事件的 civil_action_debt 于本次恢复时
   生效并清零, 见 events) -> 重置 turn_discounts
   (注入领袖回合修饰, 如 homer 军事建造折扣, 见 effects.turn_start_discounts)。
   官方顺序: 回合结束阶段(含弃牌决策)全部完成后, 才轮到下一位的回合
   开始。压入 discard_military pending 时 advance 即停(phase 置
   TURN_START, current_player 保持为响应者), 由响应者弃至合规后
   apply._discard_military 调 proceed 继续推进。
   次优口径说明: 官方回合结束阶段顺序为 弃置多余军事牌 -> 起义检定 ->
   生产 -> 抓取军事牌; pending 虽在"弃置多余军事牌"步骤压入, 但其结算
   等待发生在整个回合末流程之后(响应者会看到抓牌结果, 弃牌候选含新抓
   的牌)。引擎未做到逐步等待, 但保证了弃牌决策先于推进/下一位回合开始
   (消除时代切换错位与回合开始信息泄漏)。
2. 推进(proceed): nxt = (current+1) % 人数; nxt == 0 时: last_round ->
   终局(terminal, final_scores = 各玩家文化, 事件计分 P2); 否则
   round += 1, 且 age 已为 IV 时 last_round = True(非起始玩家回合开启
   IV -> 下一轮为最后一轮)。
3. 回合开始(nxt 玩家): round == 1 -> 全部跳过; 否则弃最左
   N(2/3/4 人 -> 3/2/1)个位置的牌入 removed -> 左移紧凑 -> 补牌
   -> 结算战争(规则书 p3 回合流程: 补充卡牌列 -> 结算战争 -> 公开
   专属阵型; 当前玩家 declared_wars 逐张结算, 见
   politics.resolve_declared_wars)-> 强制公开专属阵型(规则书 p3:
   tactics 非 None 且未公开 -> tactics_public=True):
   - 时代 A 于第一次补牌时结束: 先用 A 堆补空位, 余牌入 removed, 启用
     I 堆继续补(官方规则: 时代 A 结束 nothing else happens -> 无过期,
     也无每人 -2 黄点);
   - 时代 I/II 于当前牌堆最后一张放上牌列时结束: 过期处理(更早时代手牌
     入弃牌堆; 过期领袖入 removed 并清 None, leader_ages 保留; 过期未完成
     奇迹已付阶段蓝点退回 blue_bank 后入 removed) -> 每人 yellow_bank -2
     (下限 0) -> 启用下一时代牌堆继续补;
   - 时代 III 牌堆尽 -> 时代 IV: 先执行与 I/II 结束同一序列(过期处理 +
     每人 yellow_bank -2, 下限 0), 再停止补牌; 时代 IV 无牌堆但回合开始仍
     弃最左 N 张并左移, 右侧空位保持空;
     起始玩家回合开启 IV -> 本轮为最后一轮, 否则下一轮为最后一轮。
   - 时代更替(A->I/I->II/II->III/III->IV)同步更替军事牌堆: 旧军事牌堆
     余牌与军事弃牌堆放回盒中(入 removed; 官方规则: 军事弃牌堆按时代
     分立, 重洗只用当前时代的军事弃牌堆), 从 future_military_decks
     弹出新时代军事堆(开局已洗匀); 时代 IV military_deck 清空。
"""

from dataclasses import replace

from tta.engine import civ, economy, effects, military, politics
from tta.engine.enums import Age, Phase
from tta.engine.model import CardDB
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
    replace_player,
)
from tta.engine.tracks import consumption_value, corruption_value

DISCARD_BY_PLAYERS = {2: 3, 3: 2, 4: 1}
"""回合开始弃掉的卡牌列最左位置数(按玩家人数)."""

FOOD_SHORTAGE_CULTURE_PENALTY = 4
"""食物消耗每缺 1 点损失的文化."""

AGE_END_YELLOW_LOSS = 2
"""时代结束时每位玩家损失的黄点."""

MAX_MILITARY_DRAW = 3
"""回合末抓军事牌上限(官方规则: 至多 3 张)."""

_AGE_ORDER = (Age.A, Age.I, Age.II, Age.III, Age.IV)


def advance(state: GameState, db: CardDB) -> GameState:
    """回合末阶段 -> (压入弃牌 pending 则等待响应) -> 推进 + 下一位回合开始.

    相位流转: 当前玩家 ACTION(PassTurn)-> 若超军事手牌上限则 TURN_START
    (等待刚结束回合的玩家逐张 DiscardMilitary 弃至合规, 之后由
    apply._discard_military 调 proceed 继续)-> 下一位 TURN_START(引擎
    自动处理回合开始阶段)-> 第一回合直接 ACTION(官方规则: 跳过回合
    开始阶段与政治阶段), 否则 POLITICS。
    """
    pending_before = len(state.pending)
    state = end_of_turn(state, db)
    if len(state.pending) > pending_before:
        # 官方顺序: 回合结束阶段(含弃牌决策)全部完成后, 才轮到下一位的
        # 回合开始。压入 discard_military pending 即停: current_player 保持
        # 为刚结束回合的玩家(即 responder), phase 置 TURN_START(推进中,
        # 阻断 legal 的 PassTurn 兜底, 强制弃牌)。
        return replace(state, phase=Phase.TURN_START)
    return proceed(state, db)


def proceed(state: GameState, db: CardDB) -> GameState:
    """推进到下一位玩家并执行其回合开始阶段(end_of_turn 已结算完毕).

    仅供 advance(无弃牌 pending)与 apply._discard_military(弃牌 pending
    结算完)调用; 不重复执行回合末阶段的任何内容。
    """
    nxt = (state.current_player + 1) % len(state.players)
    if nxt == 0:
        if state.last_round:
            # 最后一轮已完整打完 -> 终局(P1 无事件, 仅文化计分)
            return replace(
                state,
                terminal=True,
                final_scores=tuple(p.culture for p in state.players),
            )
        state = replace(state, round=state.round + 1)
        if state.age is Age.IV:
            # IV 于非起始玩家回合开启: 递增后的这一轮为最后一轮
            state = replace(state, last_round=True)
    state = replace(state, current_player=nxt, phase=Phase.TURN_START)
    state = _start_of_turn(state, db)
    # 规则书 p3 回合流程: 补充卡牌列 -> 结算战争 -> 公开专属阵型
    state = politics.resolve_declared_wars(db, state)
    state = _reveal_tactics(state)
    # 第一回合跳过政治阶段(回合开始阶段 _start_of_turn 对 round==1 本就跳过)
    phase = Phase.ACTION if state.round == 1 else Phase.POLITICS
    return replace(state, phase=phase)


# --- 回合末阶段 -----------------------------------------------------------


def end_of_turn(state: GameState, db: CardDB) -> GameState:
    idx = state.current_player
    p = state.players[idx]
    values = civ.civ_values(db, p)
    # a. 弃多余军事牌: 手牌 > civ 军事行动点 + military_hand_extra ->
    # discard_military pending(responder = 刚结束回合的玩家; 官方回合结束
    # 阶段顺序: 弃置多余的军事牌 -> 起义检定 -> 生产 -> 抓取军事牌。
    # pending 在"弃置多余军事牌"步骤压入, 但结算等待发生在整个回合末流程
    # 之后、回合推进之前, 由 apply._discard_military 归零后调 proceed;
    # 需弃数量已固化于 context)
    hand_limit = values.military_actions + values.military_hand_extra
    excess = len(p.hand_military) - hand_limit
    if excess > 0:
        state = replace(state, pending=state.pending + (PendingEffect(
            effects.KIND_DISCARD_MILITARY, 0,
            responder=idx, context={"count": excess}),))
    # b. 起义检定: 起义则跳过整个生产阶段
    if not civ.is_uprising(db, p):
        p = _production(db, p, values)
    # d. 抓军事牌: min(剩余红点, 3); 时代 IV 不抓
    state, p = _draw_military(state, p)
    # e. 恢复行动点 = civ 总值; 重置 turn_discounts(注入领袖回合修饰);
    # 清零 tactics_this_turn(阵型打出/复制每回合限 1, 随行动点恢复重置);
    # civil_action_debt(rebellion 事件)于本次恢复时生效并清零(下回合 -2 白点)
    p = replace(
        p,
        civil_actions=max(0, values.civil_actions - p.civil_action_debt),
        military_actions=values.military_actions,
        turn_discounts=effects.turn_start_discounts(db, p),
        tactics_this_turn=False,
        civil_action_debt=0,
    )
    return replace_player(state, idx, p)


def _draw_military(
    state: GameState, p: PlayerState,
) -> tuple[GameState, PlayerState]:
    """回合末抓军事牌: min(剩余红点, 3) 张从军事牌堆顶抓入手.

    抓牌共用实现见 military.draw_military(与事件效果同一官方口径);
    p 尚未写回 state, 先落盘再抓并读回, 保证手牌基线含生产阶段改动。
    """
    idx = state.current_player
    count = min(p.military_actions, MAX_MILITARY_DRAW)
    state = military.draw_military(replace_player(state, idx, p), idx, count)
    return state, state.players[idx]


def _production(db: CardDB, p: PlayerState, values: civ.CivValues) -> PlayerState:
    """生产阶段: 计分 -> 腐败 -> 食物生产 -> 食物消耗 -> 资源生产."""
    p = replace(
        p,
        science=p.science + values.science_rate,
        culture=p.culture + values.culture_rate,
    )
    # 腐败: 资源支付, 不足部分用食物继续支付, 仍不足损失到此为止
    amount = corruption_value(p.blue_bank)
    if amount > 0:
        p, paid = economy.settle_loss(db, p, "resource", amount)
        p, _ = economy.settle_loss(db, p, "food", amount - paid)
    # 食物生产 -> 食物消耗(每缺 1 -4 文化, 文化下限 0)
    p = economy.produce(db, p, "food")
    need = consumption_value(p.yellow_bank)
    if need > 0:
        p, paid = economy.settle_loss(db, p, "food", need)
        missing = need - paid
        if missing > 0:
            p = replace(p, culture=max(
                0, p.culture - FOOD_SHORTAGE_CULTURE_PENALTY * missing))
    # 资源生产
    return economy.produce(db, p, "resource")


# --- 回合开始阶段 -----------------------------------------------------------


def _reveal_tactics(state: GameState) -> GameState:
    """回合开始强制公开专属阵型(规则书 p3: 有阵型牌必须在此时将其公开).

    公开后其他玩家方可复制(CopyTactics); 打出/复制的当回合不公开。
    """
    idx = state.current_player
    p = state.players[idx]
    if p.tactics is None or p.tactics_public:
        return state
    return replace_player(state, idx, replace(p, tactics_public=True))


def _start_of_turn(state: GameState, db: CardDB) -> GameState:
    if state.round == 1:
        return state  # 第一轮不弃牌不补牌
    state = _discard_and_slide(state)
    if state.age is Age.IV:
        # 时代 IV 无牌堆: 仍弃最左 N 张并左移, 但不补牌(右侧空位保持空)
        return state
    return _refill(state, db)


def _discard_and_slide(state: GameState) -> GameState:
    """弃最左 N 个位置的牌入 removed, 其余左移紧凑."""
    n = DISCARD_BY_PLAYERS[len(state.players)]
    row = list(state.card_row)
    removed = state.removed + tuple(c for c in row[:n] if c is not None)
    kept = [c for c in row[n:] if c is not None]
    kept.extend([None] * (ROW_SLOTS - len(kept)))
    return replace(state, card_row=tuple(kept), removed=removed)


def _refill(state: GameState, db: CardDB) -> GameState:
    """从当前时代牌堆补满右侧空位, 处理时代结束/时代 IV."""
    row = list(state.card_row)
    if state.age is Age.A:
        # 时代 A 于第一次补牌时结束: 先用 A 堆补空位, 余牌入 removed
        deck = list(state.civil_deck)
        for i, card_id in enumerate(row):
            if card_id is None and deck:
                row[i] = deck.pop(0)
        state = _end_age(replace(state, civil_deck=tuple(deck)), db)
    for i in range(ROW_SLOTS):
        if state.age is Age.IV:
            break
        if row[i] is not None:
            continue
        while not state.civil_deck and state.age is not Age.IV:
            # 牌堆已尽但仍有空位: 时代结束, 切下一时代牌堆继续补
            state = _end_current_age(state, db)
        if state.age is Age.IV:
            break
        row[i] = state.civil_deck[0]
        state = replace(state, civil_deck=state.civil_deck[1:])
        if not state.civil_deck:
            # 当前牌堆最后一张已放上牌列 -> 时代结束
            state = _end_current_age(state, db)
    return replace(state, card_row=tuple(row))


def _end_current_age(state: GameState, db: CardDB) -> GameState:
    if state.age is Age.III:
        return _enter_age_four(state, db)
    return _end_age(state, db)


def _age_end_cleanup(
    state: GameState, db: CardDB, ended: Age,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[PlayerState, ...]]:
    """时代结束共有序列: 过期处理 + 每人 -2 黄点(时代 A 结束不执行).

    过期处理: 更早时代手牌入弃牌堆; 过期领袖入 removed 并清 None
    (leader_ages 保留); 过期未完成奇迹已付阶段蓝点退回 blue_bank 后
    入 removed。返回 (removed, discard, players) 供调用方组装新状态。
    """
    removed = state.removed
    discard = state.discard
    players: list[PlayerState] = []
    for p in state.players:
        # 过期手牌(时代早于刚结束时代)入弃牌堆
        kept: list[str] = []
        for card_id in p.hand_civil:
            if _is_obsolete(db, card_id, ended):
                discard += (card_id,)
            else:
                kept.append(card_id)
        p = replace(p, hand_civil=tuple(kept))
        # 过期领袖入 removed 并清 None(leader_ages 保留)
        if p.leader is not None and _is_obsolete(db, p.leader, ended):
            removed += (p.leader,)
            p = replace(p, leader=None)
        # 过期未完成奇迹: 已付阶段蓝点退回 blue_bank, 奇迹入 removed
        if p.wonder_progress is not None:
            wonder_id, stages_done = p.wonder_progress
            if _is_obsolete(db, wonder_id, ended):
                removed += (wonder_id,)
                p = replace(p, blue_bank=p.blue_bank + stages_done,
                            wonder_progress=None)
        # 每人 -2 黄点(下限 0); 时代 A 结束不执行
        if ended is not Age.A:
            p = replace(
                p, yellow_bank=max(0, p.yellow_bank - AGE_END_YELLOW_LOSS))
        players.append(p)
    return removed, discard, tuple(players)


def _end_age(state: GameState, db: CardDB) -> GameState:
    """时代 A/I/II 结束: 余牌移除 -> 过期处理与 -2 黄点 -> 启用新牌堆.

    官方规则: 每人 -2 黄点仅在时代 I/II/III 结束时执行; 时代 A 结束
    "nothing else happens"(无过期, 也无黄点损失)。
    """
    ended = state.age
    new_age = ended.next()
    if new_age is None:  # pragma: no cover - III 由 _enter_age_four 处理
        msg = "时代 III 的结束应走 _enter_age_four"
        raise AssertionError(msg)
    # 当前牌堆余牌入 removed(时代 A 结束的核心; I/II 结束时牌堆已空)
    removed = state.removed + state.civil_deck
    state = replace(state, removed=removed)
    removed, discard, players = _age_end_cleanup(state, db, ended)
    future = dict(state.future_decks)
    new_deck = future.pop(new_age.value, ())
    # 军事牌堆更替: 旧军事牌堆余牌与军事弃牌堆放回盒中(入 removed; 官方
    # 规则: 军事弃牌堆按时代分立, 重洗只用当前时代的军事弃牌堆, 旧时代
    # 弃牌堆在时代切换后不再参与重洗), 启用新时代军事堆(开局已洗匀)
    removed += state.military_deck + state.military_discard
    future_military = dict(state.future_military_decks)
    new_military_deck = future_military.pop(new_age.value, ())
    return replace(
        state,
        age=new_age,
        civil_deck=new_deck,
        future_decks=future,
        military_deck=new_military_deck,
        future_military_decks=future_military,
        military_discard=(),
        removed=removed,
        discard=discard,
        players=players,
    )


def _is_obsolete(db: CardDB, card_id: str, ended: Age) -> bool:
    """过期 = 卡牌时代早于刚结束的时代(刚结束时代的卡本身不过期)."""
    return _AGE_ORDER.index(db.get(card_id).age) < _AGE_ORDER.index(ended)


def _enter_age_four(state: GameState, db: CardDB) -> GameState:
    """时代 III 结束: 过期处理与 -2 黄点(同 I/II 结束序列) -> 时代 IV.

    官方规则: 时代 I/II/III 结束执行同一序列(过期处理 + 每人 -2 黄点,
    下限 0)。时代 IV 无牌堆: 停止补牌; 起始玩家回合开启则本轮为最后轮。
    """
    removed, discard, players = _age_end_cleanup(state, db, Age.III)
    last_round = state.last_round or state.current_player == 0
    return replace(
        state,
        age=Age.IV,
        civil_deck=(),
        # 时代 IV 无军事牌堆: 旧军事牌堆余牌与军事弃牌堆(按时代分立)
        # 放回盒中(入 removed)
        military_deck=(),
        military_discard=(),
        removed=removed + state.military_deck + state.military_discard,
        discard=discard,
        players=players,
        last_round=last_round,
    )
