"""官方回合状态机: PassTurn 后的完整回合推进.

advance(state, db) 流程:

1. 回合末阶段(当前玩家, end_of_turn), 官方顺序(规则书 p6 回合结束阶段):
   弃置多余的军事牌 -> 起义检定 -> 生产阶段 -> 抓取军事牌 -> 恢复所有
   行动点。分两个阶段逐步实现逐步等待(P3-T3):
   - 阶段 1(end_of_turn): 军事手牌上限 = civ 军事行动点 +
     military_hand_extra, 超出部分压入 discard_military pending
     (responder = 刚结束回合的玩家, context 带 {"count": excess,
     "resume": RESUME_END_OF_TURN_PRODUCTION} 续跑标记)并立即返回;
     未超限则直接进入阶段 2。
   - 阶段 2(end_of_turn_production): 起义检定(is_uprising -> 跳过整个
     生产阶段) -> 生产(科技/文化按增速计分 -> 腐败[资源支付, 不足用食物
     补, 仍不足损失到此为止] -> 食物生产 -> 食物消耗[每缺 1 -4 文化,
     文化下限 0] -> 资源生产) -> 抓军事牌(min(剩余红点, 3) 张; 牌堆空则
     切洗军事弃牌堆重置牌堆, 弃牌堆也空则抓不到; 时代 IV 不抓) -> 恢复
     行动点(= civ 总值, 同时清零 tactics_this_turn; rebellion 事件的
     civil_action_debt 于本次恢复时生效并清零, 见 events) -> 重置
     turn_discounts(注入领袖回合修饰, 如 homer 军事建造折扣, 见
     effects.turn_start_discounts)。
   压入 discard_military pending 时 advance 即停(phase 置 TURN_START,
   current_player 保持为响应者), 由响应者逐张 DiscardMilitary 弃至合规;
   apply._discard_military 于 count 归零 pop 时识别 resume 标记, 调用
   end_of_turn_production 从阶段 2 续跑(阶段 1 不重入, 不重复检查超限:
   阶段 2 抓牌可能使手牌再度超限, 官方口径此时回合已结束, 下次弃牌检查
   在该玩家下个回合末), 然后 proceed 推进。
2. 推进(proceed): 下一位未退出座位(体面退出者跳过, P2-T10); 回绕座位
   序列时: last_round -> 终局计分(events.endgame_scoring: 结算两事件堆
   中所有时代 III 事件 + 终局奖励效果, terminal, final_scores = 终局文化,
   P2-T12); 否则 round += 1, 且 age 已为 IV 时 last_round = True(非起始
   玩家回合开启 IV -> 下一轮为最后一轮)。
3. 回合开始(nxt 玩家): round == 1 -> 全部跳过; 否则弃最左
   N(2/3/4 人 -> 3/2/1)个位置的牌入 removed -> 左移紧凑 -> 补牌
   -> 结算战争(规则书 p3 回合流程: 补充卡牌列 -> 结算战争 -> 公开
   专属阵型; 当前玩家 declared_wars 逐张结算, 见
   politics.resolve_declared_wars)-> 强制公开专属阵型(规则书 p3:
   tactics 非 None 且未公开 -> tactics_public=True, 实体卡入公共阵型区
   public_tactics, 同名覆盖/复制引用口径见 _reveal_tactics):
   - 时代 A 于第一次补牌时结束: 先用 A 堆补空位, 余牌入 removed, 启用
     I 堆继续补(官方规则: 时代 A 结束 nothing else happens -> 无过期,
     也无每人 -2 黄点);
   - 时代 I/II 于当前牌堆最后一张放上牌列时结束: 过期处理(更早时代手牌
     入弃牌堆; 更早时代军事手牌入 removed[军事弃牌堆按时代分立, 旧时代
     军事牌放回盒中]; 过期条约双方同删、单份入 removed[规则书 p3]; 过期
     领袖入 removed 并清 None, leader_ages 保留; 过期未完成奇迹已付阶段
     蓝点退回 blue_bank 后入 removed) -> 每人 yellow_bank -2
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

from tta.engine import civ, economy, effects, events, military, politics
from tta.engine.constants import FOOD_SHORTAGE_CULTURE_PENALTY
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

AGE_END_YELLOW_LOSS = 2
"""时代结束时每位玩家损失的黄点."""

MAX_MILITARY_DRAW = 3
"""回合末抓军事牌上限(官方规则: 至多 3 张)."""

RESUME_END_OF_TURN_PRODUCTION = "end_of_turn_production"
"""discard_military pending context 的续跑标记值(键 "resume").

弃牌 pending 结算完毕(count 归零 pop)时, apply._discard_military 识别
该标记并调用 end_of_turn_production 从阶段 2 续跑回合末(见模块
docstring 第 1 条)。
"""

_AGE_ORDER = (Age.A, Age.I, Age.II, Age.III, Age.IV)


def advance(state: GameState, db: CardDB) -> GameState:
    """回合末阶段 -> (压入弃牌 pending 则等待响应) -> 推进 + 下一位回合开始.

    相位流转: 当前玩家 ACTION(PassTurn)-> 若超军事手牌上限则 TURN_START
    (等待刚结束回合的玩家逐张 DiscardMilitary 弃至合规, 之后由
    apply._discard_military 续跑回合末阶段 2 并调 proceed 继续)-> 下一位
    TURN_START(引擎自动处理回合开始阶段)-> 第一回合直接 ACTION(官方
    规则: 跳过回合开始阶段与政治阶段), 否则 POLITICS。
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
    体面退出者(P2-T10)座位跳过; 越过座位序列末端(回绕)才递增 round。
    """
    nxt = state.current_player
    for _ in range(len(state.players)):
        nxt = (nxt + 1) % len(state.players)
        if not state.players[nxt].resigned:
            break
    if nxt <= state.current_player:
        # 回绕到座位序列前段 -> 新一轮(无退出者时等价于 nxt == 0)
        if state.last_round:
            # 最后一轮已完整打完 -> 终局计分: 结算两事件堆中所有时代 III
            # 事件与终局奖励效果(bill_gates), final_scores = 终局文化
            # (见 events.endgame_scoring)
            return events.endgame_scoring(db, state)
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
    """回合末阶段 1: 检查军事手牌超限, 压 discard pending 并立即返回.

    官方顺序(规则书 p6): 弃置多余的军事牌 -> 起义检定 -> 生产 -> 抓取
    军事牌。超限时压入 discard_military pending(responder = 刚结束回合
    的玩家, 需弃数量固化于 context, 带 resume 续跑标记)即停——此时
    起义检定/生产/抓牌/恢复均未发生; 由 apply._discard_military 结算
    完毕后续跑阶段 2。未超限则直接落入阶段 2。
    """
    idx = state.current_player
    p = state.players[idx]
    if p.resigned:
        # 体面退出者(P2-T10): 文明已移除, 无回合末阶段(仅 PassTurn 推进)
        return state
    values = civ.civ_values(db, p, state.players, idx)
    hand_limit = values.military_actions + values.military_hand_extra
    excess = len(p.hand_military) - hand_limit
    if excess > 0:
        return replace(state, pending=state.pending + (PendingEffect(
            effects.KIND_DISCARD_MILITARY, 0,
            responder=idx,
            context={"count": excess,
                     "resume": RESUME_END_OF_TURN_PRODUCTION}),))
    return end_of_turn_production(state, db)


def end_of_turn_production(state: GameState, db: CardDB) -> GameState:
    """回合末阶段 2: 起义检定 -> 生产 -> 抓军事牌 -> 恢复行动点/清折扣.

    由 end_of_turn(无超限)或 apply._discard_military(弃牌 pending 结算
    完毕, resume 标记)调用; 不得重入阶段 1(不再检查超限: 抓牌后手牌
    可能超上限, 官方口径下次弃牌检查在该玩家下个回合末)。
    """
    idx = state.current_player
    p = state.players[idx]
    values = civ.civ_values(db, p, state.players, idx)
    # b. 起义检定: 起义则跳过整个生产阶段
    if not civ.is_uprising(db, p, state.players, idx):
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
    p = economy.produce(db, p, "resource")
    # 国际贸易协议 A 侧(P2-T10): 每回合 +1 资源生产(卡牌数值表 p3)
    if ("international_trade_agreement", "A") in p.pacts:
        p = economy.gain_tokens(db, p, "resource", 1)
    return p


# --- 回合开始阶段 -----------------------------------------------------------


def _reveal_tactics(state: GameState) -> GameState:
    """回合开始强制公开专属阵型(规则书 p3: 有阵型牌必须在此时将其公开).

    公开即实体卡入公共阵型区(public_tactics), 之后其他玩家方可复制
    (CopyTactics 合法来源 = 公共区); 打出/复制的当回合不公开。
    同名牌处理: 公共区已有同名牌时, 规则书允许覆盖或从游戏中移除——
    同 id 下两者状态等价, 引擎固定"公共区保留一张, 重复实体卡入 removed"
    (真实牌库阵型有 2 份, 如 phalanx)。复制引用(tactics_copied)无实体卡,
    公开时不动公共区(不追加、不产生幻影 removed)。
    """
    idx = state.current_player
    p = state.players[idx]
    if p.tactics is None or p.tactics_public:
        return state
    if not p.tactics_copied:
        if p.tactics in state.public_tactics:
            # 同名牌覆盖: 重复实体卡从游戏中移除, 公共区保留一张
            state = replace(state, removed=state.removed + (p.tactics,))
        else:
            state = replace(
                state, public_tactics=state.public_tactics + (p.tactics,))
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

    过期处理: 更早时代手牌入弃牌堆; 更早时代军事手牌入 removed(规则书 p3:
    弃置手中所有过期卡牌; 军事弃牌堆按时代分立, 旧时代军事牌于本次更替
    放回盒中, 故与旧军事弃牌堆同归宿); 过期条约从游戏中移除(规则书 p3,
    双方同删、单份入 removed, 与 politics._remove_pact 同口径); 过期领袖
    入 removed 并清 None(leader_ages 保留); 过期未完成奇迹已付阶段蓝点
    退回 blue_bank 后入 removed。返回 (removed, discard, players) 供调用方
    组装新状态。
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
        # 过期军事手牌入 removed(规则书 p3: 手中所有过期卡牌, 含军事手牌)
        kept_military: list[str] = []
        for card_id in p.hand_military:
            if _is_obsolete(db, card_id, ended):
                removed += (card_id,)
            else:
                kept_military.append(card_id)
        p = replace(p, hand_military=tuple(kept_military))
        # 过期条约从游戏中移除: 双方各删己方记录(双方同删), A 侧恰一份,
        # 仅 A 侧计 1 份入 removed(与 politics._remove_pact 同口径)
        if p.pacts:
            kept_pacts: list[tuple[str, str]] = []
            for card_id, side in p.pacts:
                if _is_obsolete(db, card_id, ended):
                    if side == "A":
                        removed += (card_id,)
                else:
                    kept_pacts.append((card_id, side))
            p = replace(p, pacts=tuple(kept_pacts))
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
