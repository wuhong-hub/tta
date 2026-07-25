"""动作应用(官方规则 P1).

apply(state, action, db) 返回新 GameState, 不改动入参(嵌套 dict 整体复制)。
合法性统一经 legal_actions 成员判定; 非法动作抛 IllegalActionError。
PassTurn 交由 turn.advance 执行官方回合推进(见 tta/engine/turn.py)。
"""

from dataclasses import replace

from tta.engine import effects, turn
from tta.engine.actions import (
    Action,
    Build,
    BuildWonderStage,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    IllegalActionError,
    PassTurn,
    PlayActionCard,
    PlayLeader,
    TakeCard,
    Upgrade,
)
from tta.engine.economy import pay
from tta.engine.enums import UNIT_CATEGORIES, CardCategory
from tta.engine.legal import ROW_COSTS, legal_actions, turn_discount_for
from tta.engine.model import CardDB
from tta.engine.state import GameState, PlayerState, replace_player


def apply(state: GameState, action: Action, db: CardDB) -> GameState:
    """应用动作并返回新状态; 非法动作抛 IllegalActionError."""
    if isinstance(action, PassTurn):
        if state.terminal:
            msg = "游戏已结束, 无合法动作"
            raise IllegalActionError(msg)
        if state.pending:
            # SIMPLIFICATION: 官方行动卡效果为强制; 引擎允许 PassTurn 放弃
            # pending(仅丢弃), 随后正常落入回合推进逻辑。
            state = replace(state, pending=())
        return turn.advance(state, db)
    if state.terminal:
        msg = "游戏已结束, 无合法动作"
        raise IllegalActionError(msg)
    if action not in legal_actions(db, state):
        msg = f"非法动作: {action!r}"
        raise IllegalActionError(msg)
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
    msg = f"未知动作类型: {action!r}"  # pragma: no cover
    raise IllegalActionError(msg)  # pragma: no cover


def _update(state: GameState, p: PlayerState) -> GameState:
    return replace_player(state, state.current_player, p)


def _spend_point(p: PlayerState, military: bool) -> PlayerState:
    if military:
        return replace(p, military_actions=p.military_actions - 1)
    return replace(p, civil_actions=p.civil_actions - 1)


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
    p = state.players[state.current_player]
    card_id = state.card_row[action.row_index]
    if card_id is None:  # pragma: no cover - legal 已排除
        msg = f"卡牌列 {action.row_index} 号位为空"
        raise IllegalActionError(msg)
    card = db.get(card_id)
    cost = ROW_COSTS[action.row_index]
    if card.category is CardCategory.WONDER:
        cost += len(p.wonders)
    row = list(state.card_row)
    row[action.row_index] = None
    state = replace(state, card_row=tuple(row))
    p = replace(p, civil_actions=p.civil_actions - cost)
    if card.category is CardCategory.WONDER:
        p = replace(p, wonder_progress=(card_id, 0))
    else:
        p = replace(p, hand_civil=p.hand_civil + (card_id,))
    return _update(state, p)


def _develop_tech(db: CardDB, state: GameState, action: DevelopTech) -> GameState:
    p = state.players[state.current_player]
    card = db.get(action.card_id)
    p = _remove_from_hand(p, action.card_id)
    p = _spend_point(p, military=card.category in UNIT_CATEGORIES)
    p = replace(p, science=p.science - card.cost_science,
                developed=p.developed + (action.card_id,))
    return _update(state, p)


def _develop_government(
    db: CardDB, state: GameState, action: DevelopGovernment,
) -> GameState:
    p = state.players[state.current_player]
    card = db.get(action.card_id)
    p = _remove_from_hand(p, action.card_id)
    if action.revolution:
        # 革命: 低费 + 全部剩余白点
        fee = card.cost_science_revolution
        p = replace(p, civil_actions=0)
    else:
        fee = card.cost_science
        p = _spend_point(p, military=False)
    p = replace(p, science=p.science - fee, government=action.card_id)
    old_government = state.players[state.current_player].government
    state = replace(state, discard=state.discard + (old_government,))
    return _update(state, p)


def _build(db: CardDB, state: GameState, card_id: str) -> GameState:
    p = state.players[state.current_player]
    card = db.get(card_id)
    free, discount, state = _match_build_pending(state, card.category)
    if not free:
        p = _spend_point(p, military=card.category in UNIT_CATEGORIES)
    cost = max(
        0, card.build_cost - discount - turn_discount_for(p, card.category))
    p = pay(db, p, "resource", cost)
    p = replace(p, worker_pool=p.worker_pool - 1)
    p = _add_worker(p, card.category, card_id, +1)
    return _update(state, p)


def _upgrade(db: CardDB, state: GameState, action: Upgrade) -> GameState:
    p = state.players[state.current_player]
    from_card = db.get(action.from_card_id)
    to_card = db.get(action.to_card_id)
    free, discount, state = _match_build_pending(state, from_card.category)
    if not free:
        p = _spend_point(p, military=from_card.category in UNIT_CATEGORIES)
    diff = max(0, to_card.build_cost - from_card.build_cost)
    cost = max(
        0, diff - discount - turn_discount_for(p, from_card.category))
    p = pay(db, p, "resource", cost)
    p = _add_worker(p, from_card.category, action.from_card_id, -1)
    p = _add_worker(p, to_card.category, action.to_card_id, +1)
    return _update(state, p)


def _match_build_pending(
    state: GameState, category: CardCategory,
) -> tuple[bool, int, GameState]:
    """Build/Upgrade 与首个 pending 匹配时: pop pending, 返回 (0 行动点, 折扣).

    不匹配(或无 pending)时返回 (False, 0, 原 state), 走正常扣点全费流程。
    合法性由 legal 保证: pending 非空时只会生成匹配的动作。
    """
    if not state.pending:
        return False, 0, state
    pending = state.pending[0]
    categories = effects.PENDING_BUILD_CATEGORIES.get(pending.kind)
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
    p = state.players[state.current_player]
    card = db.get(card_id)
    p = _spend_point(p, military=military)
    p = _add_worker(p, card.category, card_id, -1)
    p = replace(p, worker_pool=p.worker_pool + 1)
    return _update(state, p)


def _play_leader(db: CardDB, state: GameState, action: PlayLeader) -> GameState:
    p = state.players[state.current_player]
    card = db.get(action.card_id)
    p = _remove_from_hand(p, action.card_id)
    if p.leader is not None:
        state = replace(state, discard=state.discard + (p.leader,))
    p = replace(p, leader=action.card_id,
                leader_ages=p.leader_ages + (card.age.value,))
    # 1 白点花出并拿回, 净耗 0 -> civil_actions 不变
    return _update(state, p)


def _build_wonder_stage(db: CardDB, state: GameState) -> GameState:
    p = state.players[state.current_player]
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
        p = replace(p, wonders=p.wonders + (card_id,), wonder_progress=None)
    else:
        p = replace(p, wonder_progress=(card_id, stages_done))
    return _update(state, p)


def _play_action_card(
    db: CardDB, state: GameState, action: PlayActionCard,
) -> GameState:
    p = state.players[state.current_player]
    card = db.get(action.card_id)
    handler = effects.ACTION_HANDLERS.get(card.handler)
    if handler is None:  # pragma: no cover - legal 已排除
        msg = f"行动卡 {action.card_id!r} 未注册处理器"
        raise IllegalActionError(msg)
    # 打出流程: 扣 1 白点 + 手牌移除 + 卡入弃牌堆, 再交 handler 结算效果
    p = _remove_from_hand(p, action.card_id)
    p = _spend_point(p, military=False)
    state = replace(state, discard=state.discard + (action.card_id,))
    state = _update(state, p)
    return handler(state, state.current_player, db)
