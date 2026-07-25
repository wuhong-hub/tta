"""动作应用(官方规则 P1 + P2 相位化/政治阶段).

apply(state, action, db) 返回新 GameState, 不改动入参(嵌套 dict 整体复制)。
合法性统一经 legal_actions 成员判定; 非法动作抛 IllegalActionError。
PassTurn(仅 ACTION 相位合法)交由 turn.advance 执行官方回合推进
(见 tta/engine/turn.py); SkipPolitics 将相位 POLITICS -> ACTION;
SeedEvent 走 politics.seed_event(筹划 + 揭示 + 事件结算); 事件选择 pending
由 ChooseEventOption(events.apply_event_choice)或 DeclineResponse(丢弃
pending[0], 仅可放弃白名单 kind)结算。
行动者 = pending[0].responder(None 时为 current_player, 见
state.acting_index): 响应期由 responder 结算 pending, pop 后控制权
自然恢复为 current_player。
"""

from dataclasses import replace

from tta.engine import effects, events, politics, turn
from tta.engine.actions import (
    Action,
    Build,
    BuildWonderStage,
    CancelPact,
    ChooseEventOption,
    ColonizeBid,
    ColonizePass,
    ColonizePlayBonus,
    ColonizeSacrifice,
    CopyTactics,
    DeclareWar,
    DeclineResponse,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    DiscardForStrength,
    DiscardMilitary,
    IllegalActionError,
    IncreasePopulation,
    PactAccept,
    PactReject,
    PassResponse,
    PassTurn,
    PlayActionCard,
    PlayAggression,
    PlayDefenseBonus,
    PlayLeader,
    PlayTactics,
    ProposePact,
    Resign,
    SeedEvent,
    SkipPolitics,
    TakeCard,
    Upgrade,
)
from tta.engine.economy import pay
from tta.engine.enums import UNIT_CATEGORIES, Age, CardCategory, Phase
from tta.engine.legal import ROW_COSTS, legal_actions, turn_discount_for
from tta.engine.model import CardDB
from tta.engine.state import GameState, PlayerState, acting_index, replace_player


def apply(state: GameState, action: Action, db: CardDB) -> GameState:
    """应用动作并返回新状态; 非法动作抛 IllegalActionError."""
    if state.terminal:
        msg = "游戏已结束, 无合法动作"
        raise IllegalActionError(msg)
    if isinstance(action, ColonizeSacrifice):
        # 牺牲元组组合枚举爆炸: legal 仅提供"全选"锚点, 此处独立于成员
        # 判定校验(非法抛 IllegalActionError, 见 politics.colonize_sacrifice),
        # 供 LLM 玩家构造精确子集元组
        return politics.colonize_sacrifice(db, state, action)
    if action not in legal_actions(db, state):
        msg = f"非法动作: {action!r}"
        raise IllegalActionError(msg)
    if isinstance(action, PassTurn):
        if state.pending:
            # SIMPLIFICATION: 官方行动卡效果为强制; 引擎允许 PassTurn 放弃
            # pending(仅丢弃), 随后正常落入回合推进逻辑。
            state = replace(state, pending=())
        return turn.advance(state, db)
    if isinstance(action, SkipPolitics):
        return replace(state, phase=Phase.ACTION)
    if isinstance(action, DeclineResponse):
        # 放弃首个 pending(白名单由 legal 保证); 仅丢弃 pending[0]
        return replace(state, pending=state.pending[1:])
    if isinstance(action, SeedEvent):
        return politics.seed_event(db, state, action)
    if isinstance(action, PlayAggression):
        return politics.play_aggression(db, state, action)
    if isinstance(action, DeclareWar):
        return politics.declare_war(db, state, action)
    if isinstance(action, ProposePact):
        return politics.propose_pact(db, state, action)
    if isinstance(action, PactAccept):
        return politics.pact_accept(db, state)
    if isinstance(action, PactReject):
        return politics.pact_reject(db, state)
    if isinstance(action, CancelPact):
        return politics.cancel_pact(db, state, action)
    if isinstance(action, Resign):
        return politics.resign(db, state)
    if isinstance(action, PlayDefenseBonus):
        return politics.play_defense_bonus(db, state, action)
    if isinstance(action, DiscardForStrength):
        return politics.discard_for_strength(db, state, action)
    if isinstance(action, PassResponse):
        return politics.pass_response(db, state)
    if isinstance(action, ChooseEventOption):
        if (state.pending
                and state.pending[0].kind in politics.AGGRESSION_CHOICE_KINDS):
            # 受害者选择类侵略 pending(强制失去)由 politics 结算
            return politics.apply_aggression_choice(db, state, action.option)
        if (state.pending
                and state.pending[0].kind == politics.KIND_WAR_SEIZE):
            # 科技之战胜者夺取特殊科技 pending 由 politics 结算
            return politics.apply_war_seize(db, state, action.option)
        return events.apply_event_choice(db, state, action.option)
    if isinstance(action, ColonizeBid):
        return politics.colonize_bid(db, state, action)
    if isinstance(action, ColonizePass):
        return politics.colonize_pass(db, state, action)
    if isinstance(action, ColonizePlayBonus):
        return politics.colonize_play_bonus(db, state, action)
    if isinstance(action, TakeCard):
        return _take_card(db, state, action)
    if isinstance(action, DevelopTech):
        return _develop_tech(db, state, action)
    if isinstance(action, DevelopGovernment):
        return _develop_government(db, state, action)
    if isinstance(action, Build):
        return _build(db, state, action.card_id)
    if isinstance(action, Upgrade):
        return _upgrade(db, state, action)
    if isinstance(action, Destroy):
        return _remove_worker(db, state, action.card_id, military=False)
    if isinstance(action, Disband):
        return _remove_worker(db, state, action.card_id, military=True)
    if isinstance(action, PlayLeader):
        return _play_leader(db, state, action)
    if isinstance(action, BuildWonderStage):
        return _build_wonder_stage(db, state)
    if isinstance(action, PlayActionCard):
        return _play_action_card(db, state, action)
    if isinstance(action, DiscardMilitary):
        return _discard_military(db, state, action)
    if isinstance(action, PlayTactics):
        return _play_tactics(db, state, action)
    if isinstance(action, CopyTactics):
        return _copy_tactics(db, state, action)
    if isinstance(action, IncreasePopulation):
        return _increase_population(db, state)
    msg = f"未知动作类型: {action!r}"  # pragma: no cover
    raise IllegalActionError(msg)  # pragma: no cover


def _update(state: GameState, idx: int, p: PlayerState) -> GameState:
    return replace_player(state, idx, p)


def _spend_point(p: PlayerState, military: bool) -> PlayerState:
    if military:
        return replace(p, military_actions=p.military_actions - 1)
    return replace(p, civil_actions=p.civil_actions - 1)


def _spend_civil(db: CardDB, p: PlayerState, cost: int) -> PlayerState:
    """扣 cost 白点; 白点不足时经 effects.flexible_actions 用 1 红点垫付.

    hammurabi 官方规则: 每回合一次, 可将 1 个军事行动当作内政行动使用
    (每次垫付最多 1 点, 已用标记写入 turn_discounts, 回合末清空)。
    仅 TakeCard / DevelopTech / Build / Upgrade 四处挂钩(与 legal 一致),
    其余白点花费(PlayLeader / Destroy / BuildWonderStage 等)不垫付。
    垫付上限由 legal 保证; 防御性校验: 无垫付资格(非 hammurabi / 本回合
    已用 / 红点不足)或差额超过 1 点时抛 IllegalActionError。
    """
    deficit = cost - p.civil_actions
    if deficit <= 0:
        return replace(p, civil_actions=p.civil_actions - cost)
    if effects.flexible_actions(db, p) < deficit:
        msg = f"白点不足且无红点垫付资格(hammurabi): 需垫付 {deficit}"
        raise IllegalActionError(msg)
    discounts = dict(p.turn_discounts)
    discounts[effects.HAMMURABI_FLEX_KEY] = 1
    return replace(
        p, civil_actions=0, military_actions=p.military_actions - deficit,
        turn_discounts=discounts)


def _remove_from_hand(p: PlayerState, card_id: str) -> PlayerState:
    hand = list(p.hand_civil)
    hand.remove(card_id)
    return replace(p, hand_civil=tuple(hand))


def _add_worker(p: PlayerState, category: CardCategory, card_id: str,
                delta: int) -> PlayerState:
    buildings = dict(p.buildings)
    slots = dict(buildings.get(category.value, {}))
    left = slots.get(card_id, 0) + delta
    if left > 0:
        slots[card_id] = left
    else:
        slots.pop(card_id, None)
    buildings[category.value] = slots
    return replace(p, buildings=buildings)


def _take_card(db: CardDB, state: GameState, action: TakeCard) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    card_id = state.card_row[action.row_index]
    if card_id is None:  # pragma: no cover - legal 已排除
        msg = f"卡牌列 {action.row_index} 号位为空"
        raise IllegalActionError(msg)
    card = db.get(card_id)
    cost = ROW_COSTS[action.row_index]
    if card.category is CardCategory.WONDER:
        # 每已完成奇迹 +1 白点(michelangelo 免除, 与 legal 同口径)
        cost += effects.wonder_take_surcharge(db, p)
    if card.category is CardCategory.LEADER:
        # hammurabi: 拿领袖牌 -1 白点(与 legal._take_card_legal 同口径)
        cost = max(0, cost - effects.leader_take_discount(db, p))
    row = list(state.card_row)
    row[action.row_index] = None
    state = replace(state, card_row=tuple(row))
    p = _spend_civil(db, p, cost)
    if card.category is CardCategory.WONDER:
        p = replace(p, wonder_progress=(card_id, 0))
    else:
        p = replace(p, hand_civil=p.hand_civil + (card_id,))
    # aristotle 等领袖的拿牌即时收益(拿科技牌 +1 科技)
    gains = effects.on_take_card_gains(db, p, card)
    if gains:
        p = replace(p,
                    science=p.science + gains.get("science", 0),
                    culture=p.culture + gains.get("culture", 0))
    return _update(state, idx, p)


_SPECIAL_AGE_ORDER = (Age.A, Age.I, Age.II, Age.III)
"""特殊科技等级比较的时代序(同级再按 cost_science)."""


def _replace_lower_special(
    db: CardDB, state: GameState, p: PlayerState, new_card_id: str,
) -> tuple[GameState, PlayerState]:
    """同类型特殊科技替换: 两张并存时立即将等级较低者从游戏中移除.

    官方规则: LAW/WARFARE/EXPLORATION/CONSTRUCTION 四类特殊科技,
    同时拥有两张同类型时, 等级较低者(先比时代序, 同级按 cost_science)
    从游戏中移除(入 removed, 保持卡牌守恒); 其静态加成随之失效。
    """
    new_type = db.get(new_card_id).special_type
    same = [
        card_id for card_id in p.developed
        if db.get(card_id).category is CardCategory.SPECIAL
        and db.get(card_id).special_type is new_type
    ]
    if len(same) < 2:
        return state, p

    def _level(card_id: str) -> tuple[int, int]:
        card = db.get(card_id)
        return (_SPECIAL_AGE_ORDER.index(card.age), card.cost_science)

    lower = min(same, key=_level)
    developed = list(p.developed)
    developed.remove(lower)
    p = replace(p, developed=tuple(developed))
    state = replace(state, removed=state.removed + (lower,))
    return state, p


def _develop_tech(db: CardDB, state: GameState, action: DevelopTech) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    card = db.get(action.card_id)
    free, science_gain, science_discount = False, 0, 0
    if state.pending and state.pending[0].kind == effects.KIND_DEVELOP_TECH:
        # develop_tech pending 子行动: 0 行动点; breakthrough 全价研发后
        # +science_gain 科技, 事件选项(development_of_civilization)带
        # 科技费折扣(discount)
        free = True
        science_gain = state.pending[0].science_gain
        science_discount = state.pending[0].discount
        state = replace(state, pending=state.pending[1:])
    p = _remove_from_hand(p, action.card_id)
    if not free:
        if card.category in UNIT_CATEGORIES:
            p = _spend_point(p, military=True)
        else:
            p = _spend_civil(db, p, 1)
    science_cost = (
        max(0, card.cost_science - science_discount)
        if free else card.cost_science
    )
    p = replace(p, science=p.science - science_cost + science_gain,
                developed=p.developed + (action.card_id,))
    if card.category is CardCategory.SPECIAL:
        # 官方规则: 同类型特殊科技两张并存 -> 等级较低者立即从游戏中移除
        state, p = _replace_lower_special(db, state, p, action.card_id)
    # 研发即时收益(leonardo +1 资源 / newton 拿回白点 / justice_system +3 蓝点)
    p = effects.on_develop_tech_gains(db, p, action.card_id)
    return _update(state, idx, p)


def _develop_government(
    db: CardDB, state: GameState, action: DevelopGovernment,
) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    card = db.get(action.card_id)
    p = _remove_from_hand(p, action.card_id)
    if action.revolution:
        # 革命: 低费 + 全部剩余白点(robespierre: 全部剩余红点)
        fee = card.cost_science_revolution
        if effects.revolution_uses_military(db, p):
            p = replace(p, military_actions=0)
        else:
            p = replace(p, civil_actions=0)
    else:
        fee = card.cost_science
        p = _spend_point(p, military=False)
    p = replace(p, science=p.science - fee, government=action.card_id)
    old_government = state.players[idx].government
    state = replace(state, discard=state.discard + (old_government,))
    return _update(state, idx, p)


def _build(db: CardDB, state: GameState, card_id: str) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    card = db.get(card_id)
    if state.pending and (
        events.EVENT_FREE_BUILD.get(state.pending[0].kind) == card_id
    ):
        # 事件免费建造(development_of_religion/warfare): 0 行动点 0 费用
        state = replace(state, pending=state.pending[1:])
        p = replace(p, worker_pool=p.worker_pool - 1)
        p = _add_worker(p, card.category, card_id, +1)
        return _update(state, idx, p)
    free, discount, state = _match_build_pending(state, card.category)
    if not free:
        if card.category in UNIT_CATEGORIES:
            p = _spend_point(p, military=True)
        else:
            p = _spend_civil(db, p, 1)
    cost = max(
        0, card.build_cost - discount - turn_discount_for(p, card.category))
    p = pay(db, p, "resource", cost)
    p = replace(p, worker_pool=p.worker_pool - 1)
    p = _add_worker(p, card.category, card_id, +1)
    return _update(state, idx, p)


def _upgrade(db: CardDB, state: GameState, action: Upgrade) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    from_card = db.get(action.from_card_id)
    to_card = db.get(action.to_card_id)
    free, discount, state = _match_build_pending(
        state, from_card.category, upgrade=True)
    if not free:
        if from_card.category in UNIT_CATEGORIES:
            p = _spend_point(p, military=True)
        else:
            p = _spend_civil(db, p, 1)
    diff = max(0, to_card.build_cost - from_card.build_cost)
    cost = max(
        0, diff - discount - turn_discount_for(p, from_card.category))
    p = pay(db, p, "resource", cost)
    p = _add_worker(p, from_card.category, action.from_card_id, -1)
    p = _add_worker(p, to_card.category, action.to_card_id, +1)
    return _update(state, idx, p)


def _match_build_pending(
    state: GameState, category: CardCategory, *, upgrade: bool = False,
) -> tuple[bool, int, GameState]:
    """Build/Upgrade 与首个 pending 匹配时: pop pending, 返回 (0 行动点, 折扣).

    upgrade=True 时额外匹配仅升级类 pending(efficient_upgrade, 见
    effects.PENDING_UPGRADE_CATEGORIES); Build 不匹配该类。
    不匹配(或无 pending)时返回 (False, 0, 原 state), 走正常扣点全费流程。
    合法性由 legal 保证: pending 非空时只会生成匹配的动作。
    """
    if not state.pending:
        return False, 0, state
    pending = state.pending[0]
    categories = effects.PENDING_BUILD_CATEGORIES.get(pending.kind)
    if categories is None and upgrade:
        categories = effects.PENDING_UPGRADE_CATEGORIES.get(pending.kind)
    if categories is None or category not in categories:
        return False, 0, state
    return True, pending.discount, replace(state, pending=state.pending[1:])


def _remove_worker(
    db: CardDB, state: GameState, card_id: str, *, military: bool,
) -> GameState:
    """Destroy/Disband 公共: 1 工人回空闲池.

    SIMPLIFICATION: 摧毁农场/矿场时卡上蓝点(card_tokens)保留(官方规则
    未明确, 引擎约定保留)。
    """
    idx = acting_index(state)
    p = state.players[idx]
    card = db.get(card_id)
    p = _spend_point(p, military=military)
    p = _add_worker(p, card.category, card_id, -1)
    p = replace(p, worker_pool=p.worker_pool + 1)
    return _update(state, idx, p)


def _play_leader(db: CardDB, state: GameState, action: PlayLeader) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    card = db.get(action.card_id)
    p = _remove_from_hand(p, action.card_id)
    # 官方规则: 打出领袖付 1 白点; 仅替换已有领袖时拿回 1 白点(净耗 0),
    # 首次打出净耗 1
    p = replace(p, civil_actions=p.civil_actions - 1)
    if p.leader is not None:
        state = replace(state, discard=state.discard + (p.leader,))
        p = replace(p, civil_actions=p.civil_actions + 1)
    p = replace(p, leader=action.card_id,
                leader_ages=p.leader_ages + (card.age.value,))
    return _update(state, idx, p)


def _build_wonder_stage(db: CardDB, state: GameState) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    if p.wonder_progress is None:  # pragma: no cover - legal 已排除
        msg = "无在建奇迹"
        raise IllegalActionError(msg)
    card_id, stages_done = p.wonder_progress
    stages = db.get(card_id).wonder_stages
    free, discount = False, 0
    if state.pending and state.pending[0].kind == effects.KIND_WONDER_STAGE:
        free, discount = True, state.pending[0].discount
        state = replace(state, pending=state.pending[1:])
    if not free:
        p = _spend_point(p, military=False)
    p = pay(db, p, "resource", max(0, stages[stages_done] - discount))
    # SIMPLIFICATION: 官方规则允许动用卡上蓝点, P1 仅从供给区盖 1 蓝点
    p = replace(p, blue_bank=p.blue_bank - 1)
    stages_done += 1
    if stages_done == len(stages):
        # 官方规则: 奇迹完成时盖在阶段上的蓝点全部放回供给区
        p = replace(p, wonders=p.wonders + (card_id,), wonder_progress=None,
                    blue_bank=p.blue_bank + len(stages))
    else:
        p = replace(p, wonder_progress=(card_id, stages_done))
    return _update(state, idx, p)


def _discard_military(
    db: CardDB, state: GameState, action: DiscardMilitary,
) -> GameState:
    """弃 1 张军事手牌入军事弃牌堆; pending context count 递减, 归零时 pop.

    行动者 = pending[0].responder(回合末超上限的玩家, 见 turn.end_of_turn)。
    官方顺序: 回合结束阶段(含弃牌决策)全部完成后才轮到下一位的回合开始,
    故 count 归零 pop 后调用 turn.proceed 继续推进(不重复回合末内容)。
    """
    idx = acting_index(state)
    p = state.players[idx]
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    p = replace(p, hand_military=tuple(hand))
    state = replace(
        state, military_discard=state.military_discard + (action.card_id,))
    pending = state.pending[0]
    count = int(pending.context.get("count", 1)) - 1
    if count > 0:
        context = dict(pending.context)
        context["count"] = count
        state = replace(
            state, pending=(replace(pending, context=context),)
            + state.pending[1:])
        return _update(state, idx, p)
    state = replace(state, pending=state.pending[1:])
    state = _update(state, idx, p)
    # 弃牌结算完毕 -> 继续回合推进(下一位玩家的回合开始此刻才发生)
    return turn.proceed(state, db)


def _set_tactics(
    state: GameState, idx: int, card_id: str, cost: int, *, copied: bool,
) -> GameState:
    """打出/复制阵型公共结算: 扣红点, 旧阵型离场, 置新专属阵型.

    旧阵型为实体卡(tactics_copied=False, 由 PlayTactics 入场)时入军事弃牌堆;
    为复制引用时仅丢弃引用(无实体卡, 不产生幻影卡)。新阵型
    tactics_public=False(打出的当回合不公开), 回合开始阶段强制公开
    (规则书 p3, 见 turn._reveal_tactics); tactics_this_turn=True(打出与复制
    合计每回合限 1, 规则书 p6)。
    """
    p = state.players[idx]
    p = replace(p, military_actions=p.military_actions - cost)
    if p.tactics is not None and not p.tactics_copied:
        state = replace(
            state, military_discard=state.military_discard + (p.tactics,))
    p = replace(p, tactics=card_id, tactics_public=False,
                tactics_this_turn=True, tactics_copied=copied)
    return _update(state, idx, p)


def _play_tactics(db: CardDB, state: GameState, action: PlayTactics) -> GameState:
    """打出手牌中的阵型牌: 1 红点, 手牌移除该卡, 成为专属阵型(实体卡)."""
    idx = acting_index(state)
    p = state.players[idx]
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    state = _update(state, idx, replace(p, hand_military=tuple(hand)))
    return _set_tactics(state, idx, action.card_id, 1, copied=False)


def _copy_tactics(db: CardDB, state: GameState, action: CopyTactics) -> GameState:
    """复制对手已公开的阵型: 2 红点, 不消耗手牌, 成为自己的专属阵型(引用)."""
    idx = acting_index(state)
    return _set_tactics(state, idx, action.card_id, 2, copied=True)


def _increase_population(db: CardDB, state: GameState) -> GameState:
    """增人口: 1 白点 + 食物人口费(moses -1), 黄点银行 -1, 空闲工人 +1.

    结算与 frugality 行动卡共用 effects.increase_population(effects 不得
    import apply, 故共用函数置于 effects)。
    """
    idx = acting_index(state)
    p = state.players[idx]
    p = _spend_point(p, military=False)
    p = effects.increase_population(db, p)
    return _update(state, idx, p)


def _play_action_card(
    db: CardDB, state: GameState, action: PlayActionCard,
) -> GameState:
    idx = acting_index(state)
    p = state.players[idx]
    card = db.get(action.card_id)
    handler = effects.ACTION_HANDLERS.get(card.handler)
    if handler is None:  # pragma: no cover - legal 已排除
        msg = f"行动卡 {action.card_id!r} 未注册处理器"
        raise IllegalActionError(msg)
    # 打出流程: 扣 1 白点 + 手牌移除 + 卡入弃牌堆, 再交 handler 结算效果
    p = _remove_from_hand(p, action.card_id)
    p = _spend_point(p, military=False)
    state = replace(state, discard=state.discard + (action.card_id,))
    state = _update(state, idx, p)
    return handler(state, idx, db, action.option)
