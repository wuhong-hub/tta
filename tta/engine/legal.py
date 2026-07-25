"""合法动作枚举(官方规则 P1).

legal_actions(db, state) 枚举当前玩家的全部合法动作:
- 终局 -> []; pending 非空 -> 仅 [PassTurn](Task 7 改为结算 pending);
- 第一回合(state.round == 1) -> 仅 TakeCard;
- 其余情况: TakeCard / DevelopTech / DevelopGovernment / Build / Upgrade /
  Destroy / Disband / PlayLeader / BuildWonderStage / PlayActionCard,
  PassTurn 恒在末尾。
"""

from tta.engine import effects
from tta.engine.actions import (
    Action,
    Build,
    BuildWonderStage,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    PassTurn,
    PlayActionCard,
    PlayLeader,
    TakeCard,
    Upgrade,
)
from tta.engine.civ import civ_values, hand_limit_civil
from tta.engine.economy import resource_total
from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    WORKER_CATEGORIES,
    Age,
    CardCategory,
)
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import GameState, PlayerState

ROW_COSTS: tuple[int, ...] = (1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3)
"""卡牌列各位置拿牌白点费(0-4 号位 1 点, 5-9 号位 2 点, 10-12 号位 3 点)."""

_AGE_ORDER = (Age.A, Age.I, Age.II, Age.III)

_DEVELOP_CATEGORIES = WORKER_CATEGORIES | frozenset({CardCategory.SPECIAL})
"""DevelopTech 可研发的类别(农场/矿场/城市建筑/兵种/特殊科技)."""

_NO_DUPLICATE_CATEGORIES = _DEVELOP_CATEGORIES | frozenset({CardCategory.GOVERNMENT})
"""拿牌时手牌+developed 同名查重的类别."""

_DESTROY_CATEGORIES = (
    URBAN_CATEGORIES | frozenset({CardCategory.FARM, CardCategory.MINE})
)


def _take_card_legal(
    db: CardDB, p: PlayerState, row_index: int, card_id: str,
) -> bool:
    card = db.get(card_id)
    cost = ROW_COSTS[row_index]
    if card.category is CardCategory.WONDER:
        cost += len(p.wonders)
    if p.civil_actions < cost:
        return False
    if card.category is CardCategory.WONDER:
        # 奇迹牌不受内政手牌上限限制; 有未完成奇迹不可再拿
        return p.wonder_progress is None
    if len(p.hand_civil) >= hand_limit_civil(db, p):
        return False
    if card.category in _NO_DUPLICATE_CATEGORIES:
        if card_id in p.hand_civil or card_id in p.developed:
            return False
    if card.category is CardCategory.LEADER:
        if card.age.value in p.leader_ages:
            return False
    return True


def _develop_actions(db: CardDB, p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    for card_id in dict.fromkeys(p.hand_civil):
        card = db.get(card_id)
        if card.category not in _DEVELOP_CATEGORIES:
            continue
        if p.science < card.cost_science:
            continue
        if card.category in UNIT_CATEGORIES:
            if p.military_actions >= 1:
                actions.append(DevelopTech(card_id))
        elif p.civil_actions >= 1:
            actions.append(DevelopTech(card_id))
    return actions


def _government_actions(db: CardDB, p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    for card_id in dict.fromkeys(p.hand_civil):
        card = db.get(card_id)
        if card.category is not CardCategory.GOVERNMENT:
            continue
        if p.civil_actions < 1:
            continue
        if p.science >= card.cost_science:
            actions.append(DevelopGovernment(card_id, False))
        if p.science >= card.cost_science_revolution:
            actions.append(DevelopGovernment(card_id, True))
    return actions


def _build_actions(db: CardDB, p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    civ = civ_values(db, p)
    resources = resource_total(db, p)
    developed = list(p.developed)
    for card_id in dict.fromkeys(developed):
        card = db.get(card_id)
        if card.category not in WORKER_CATEGORIES:
            continue
        if card.category in UNIT_CATEGORIES:
            if p.military_actions < 1:
                continue
        elif p.civil_actions < 1:
            continue
        if p.worker_pool < 1:
            continue
        slots = p.buildings.get(card.category.value, {})
        placed = slots.get(card_id, 0)
        if placed >= developed.count(card_id):
            continue
        if resources < card.build_cost:
            continue
        if card.category in URBAN_CATEGORIES and placed == 0:
            # 城市建筑上限按类别计建筑数(每张有工人的卡 = 一座建筑)
            built = sum(1 for n in slots.values() if n > 0)
            if built >= civ.urban_limit:
                continue
        actions.append(Build(card_id))
    return actions


def _higher_level(from_card: CardDefinition, to_card: CardDefinition) -> bool:
    """to 比 from 等级高: 先比时代(枚举序), 同时代比造价; 同级禁升."""
    from_key = (_AGE_ORDER.index(from_card.age), from_card.build_cost)
    to_key = (_AGE_ORDER.index(to_card.age), to_card.build_cost)
    return to_key > from_key


def _upgrade_actions(db: CardDB, p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    resources = resource_total(db, p)
    developed = list(p.developed)
    for from_id in dict.fromkeys(developed):
        from_card = db.get(from_id)
        if from_card.category not in WORKER_CATEGORIES:
            continue
        slots = p.buildings.get(from_card.category.value, {})
        if slots.get(from_id, 0) < 1:
            continue
        if from_card.category in UNIT_CATEGORIES:
            if p.military_actions < 1:
                continue
        elif p.civil_actions < 1:
            continue
        for to_id in dict.fromkeys(developed):
            if to_id == from_id:
                continue
            to_card = db.get(to_id)
            if to_card.category is not from_card.category:
                continue
            if not _higher_level(from_card, to_card):
                continue
            if slots.get(to_id, 0) >= developed.count(to_id):
                continue
            diff = max(0, to_card.build_cost - from_card.build_cost)
            if resources < diff:
                continue
            actions.append(Upgrade(from_id, to_id))
    return actions


def _destroy_disband_actions(p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    for category_value, slots in sorted(p.buildings.items()):
        category = CardCategory(category_value)
        for card_id, workers in sorted(slots.items()):
            if workers < 1:
                continue
            if category in _DESTROY_CATEGORIES and p.civil_actions >= 1:
                actions.append(Destroy(card_id))
            if category in UNIT_CATEGORIES and p.military_actions >= 1:
                actions.append(Disband(card_id))
    return actions


def _leader_actions(db: CardDB, p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    if p.civil_actions < 1:
        return actions
    for card_id in dict.fromkeys(p.hand_civil):
        card = db.get(card_id)
        if card.category is not CardCategory.LEADER:
            continue
        if card.age.value in p.leader_ages:
            continue
        actions.append(PlayLeader(card_id))
    return actions


def _wonder_actions(db: CardDB, p: PlayerState) -> list[Action]:
    if p.wonder_progress is None or p.civil_actions < 1:
        return []
    card_id, stages_done = p.wonder_progress
    stages = db.get(card_id).wonder_stages
    if stages_done >= len(stages):
        return []
    # SIMPLIFICATION: 官方规则允许动用卡上蓝点, P1 要求供给区蓝点 > 0
    if p.blue_bank < 1:
        return []
    if resource_total(db, p) < stages[stages_done]:
        return []
    return [BuildWonderStage()]


def _action_card_actions(db: CardDB, p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    if p.civil_actions < 1:
        return actions
    for card_id in dict.fromkeys(p.hand_civil):
        card = db.get(card_id)
        if card.category is not CardCategory.ACTION:
            continue
        # 未注册处理器的行动卡不可打出(Task 7 填充注册表)
        if card.handler not in effects.ACTION_HANDLERS:
            continue
        actions.append(PlayActionCard(card_id))
    return actions


def legal_actions(db: CardDB, state: GameState) -> list[Action]:
    """枚举当前玩家全部合法动作(规则见模块 docstring)."""
    if state.terminal:
        return []
    if state.pending:
        # Task 7 改为仅生成可结算 pending 的动作
        return [PassTurn()]
    p = state.players[state.current_player]
    takes: list[Action] = [
        TakeCard(i) for i, card_id in enumerate(state.card_row)
        if card_id is not None and _take_card_legal(db, p, i, card_id)
    ]
    if state.round == 1:
        return takes
    actions: list[Action] = takes
    actions.extend(_develop_actions(db, p))
    actions.extend(_government_actions(db, p))
    actions.extend(_build_actions(db, p))
    actions.extend(_upgrade_actions(db, p))
    actions.extend(_destroy_disband_actions(p))
    actions.extend(_leader_actions(db, p))
    actions.extend(_wonder_actions(db, p))
    actions.extend(_action_card_actions(db, p))
    actions.append(PassTurn())
    return actions
