"""合法动作枚举(官方规则 P1).

legal_actions(db, state) 枚举当前玩家的全部合法动作:
- 终局 -> []; pending 非空 -> 仅可结算首个 pending 的动作 + PassTurn;
- 第一回合(state.round == 1) -> 仅 TakeCard + 末尾 PassTurn;
- 其余情况: TakeCard / DevelopTech / DevelopGovernment / Build / Upgrade /
  Destroy / Disband / PlayLeader / BuildWonderStage / PlayActionCard /
  IncreasePopulation, PassTurn 恒在末尾。

pending 子行动(行动卡压入, 见 effects): 0 行动点, 费用享折扣(下限 0);
breakthrough 的 develop_tech 子行动为 0 行动点全价研发手牌科技。
回合修饰(turn_discounts): 目前仅兵种的 "unit_build" 建造折扣。
选择类行动卡(如 reserves_i)按 effects.ACTION_OPTIONS 每个选项枚举一个
PlayActionCard。

领袖钩子(Task 9): hammurabi 拿领袖牌 -1 白点; hammurabi 红点垫付白点
(SIMPLIFICATION, 仅 TakeCard/DevelopTech/Build/Upgrade 四处挂钩, 见
effects.flexible_actions); frugality 等行动卡的额外打出条件经
effects.PLAY_CONDITIONS 预判。
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
    IncreasePopulation,
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
from tta.engine.state import GameState, PendingEffect, PlayerState

ROW_COSTS: tuple[int, ...] = (1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3)
"""卡牌列各位置拿牌白点费(0-4 号位 1 点, 5-9 号位 2 点, 10-12 号位 3 点)."""

UNIT_BUILD_DISCOUNT_KEY = effects.UNIT_BUILD_DISCOUNT_KEY
"""turn_discounts 中兵种建造折扣的键(回合修饰类行动卡写入)."""


def turn_discount_for(p: PlayerState, category: CardCategory) -> int:
    """回合修饰类效果提供的建造折扣(当前仅兵种的 unit_build)."""
    if category in UNIT_CATEGORIES:
        return p.turn_discounts.get(UNIT_BUILD_DISCOUNT_KEY, 0)
    return 0

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
        # 每已完成奇迹 +1 白点(michelangelo 免除, 见 effects)
        cost += effects.wonder_take_surcharge(db, p)
    if card.category is CardCategory.LEADER:
        # hammurabi: 拿领袖牌 -1 白点
        cost = max(0, cost - effects.leader_take_discount(db, p))
    # hammurabi SIMPLIFICATION: 白点不足时可用红点 1:1 垫付
    if p.civil_actions + effects.flexible_actions(db, p) < cost:
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
        elif p.civil_actions + effects.flexible_actions(db, p) >= 1:
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


def _build_actions(
    db: CardDB,
    p: PlayerState,
    categories: frozenset[CardCategory] = WORKER_CATEGORIES,
    point_cost: int = 1,
    discount: int = 0,
) -> list[Action]:
    """Build 枚举. pending 子行动用 point_cost=0 + discount 调用."""
    actions: list[Action] = []
    civ = civ_values(db, p)
    resources = resource_total(db, p)
    developed = list(p.developed)
    for card_id in dict.fromkeys(developed):
        card = db.get(card_id)
        if card.category not in categories:
            continue
        if card.category in UNIT_CATEGORIES:
            if p.military_actions < point_cost:
                continue
        elif p.civil_actions + effects.flexible_actions(db, p) < point_cost:
            continue
        if p.worker_pool < 1:
            continue
        slots = p.buildings.get(card.category.value, {})
        placed = slots.get(card_id, 0)
        if placed >= developed.count(card_id):
            continue
        cost = max(
            0, card.build_cost - discount - turn_discount_for(p, card.category))
        if resources < cost:
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


def _upgrade_actions(
    db: CardDB,
    p: PlayerState,
    categories: frozenset[CardCategory] = WORKER_CATEGORIES,
    point_cost: int = 1,
    discount: int = 0,
) -> list[Action]:
    """Upgrade 枚举. pending 子行动用 point_cost=0 + discount 调用."""
    actions: list[Action] = []
    resources = resource_total(db, p)
    developed = list(p.developed)
    for from_id in dict.fromkeys(developed):
        from_card = db.get(from_id)
        if from_card.category not in categories:
            continue
        slots = p.buildings.get(from_card.category.value, {})
        if slots.get(from_id, 0) < 1:
            continue
        if from_card.category in UNIT_CATEGORIES:
            if p.military_actions < point_cost:
                continue
        elif p.civil_actions + effects.flexible_actions(db, p) < point_cost:
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
            cost = max(
                0, diff - discount - turn_discount_for(p, from_card.category))
            if resources < cost:
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


def _wonder_actions(
    db: CardDB, p: PlayerState, point_cost: int = 1, discount: int = 0,
) -> list[Action]:
    """BuildWonderStage 枚举. pending 子行动用 point_cost=0 + discount 调用."""
    if p.wonder_progress is None or p.civil_actions < point_cost:
        return []
    card_id, stages_done = p.wonder_progress
    stages = db.get(card_id).wonder_stages
    if stages_done >= len(stages):
        return []
    # SIMPLIFICATION: 官方规则允许动用卡上蓝点, P1 要求供给区蓝点 > 0
    if p.blue_bank < 1:
        return []
    if resource_total(db, p) < max(0, stages[stages_done] - discount):
        return []
    return [BuildWonderStage()]


def _develop_tech_pending_actions(db: CardDB, p: PlayerState) -> list[Action]:
    """breakthrough pending 子行动: 0 行动点全价研发手牌中一项科技."""
    actions: list[Action] = []
    for card_id in dict.fromkeys(p.hand_civil):
        card = db.get(card_id)
        if card.category not in _DEVELOP_CATEGORIES:
            continue
        if p.science < card.cost_science:
            continue
        actions.append(DevelopTech(card_id))
    return actions


def _pending_actions(
    db: CardDB, p: PlayerState, pending: PendingEffect,
) -> list[Action]:
    """生成可结算首个 pending 的动作(0 行动点, 费用享折扣)."""
    categories = effects.PENDING_BUILD_CATEGORIES.get(pending.kind)
    if categories is not None:
        actions = _build_actions(
            db, p, categories=categories, point_cost=0,
            discount=pending.discount)
        actions += _upgrade_actions(
            db, p, categories=categories, point_cost=0,
            discount=pending.discount)
        return actions
    if pending.kind == effects.KIND_WONDER_STAGE:
        return _wonder_actions(db, p, point_cost=0, discount=pending.discount)
    if pending.kind == effects.KIND_DEVELOP_TECH:
        return _develop_tech_pending_actions(db, p)
    return []


def _increase_population_actions(db: CardDB, p: PlayerState) -> list[Action]:
    """增人口: 1 白点 + 黄点银行非空 + 食物足以支付人口费(moses -1)."""
    if p.civil_actions < 1:
        return []
    if not effects.can_increase_population(db, p):
        return []
    return [IncreasePopulation()]


def _action_card_actions(db: CardDB, p: PlayerState) -> list[Action]:
    actions: list[Action] = []
    if p.civil_actions < 1:
        return actions
    for card_id in dict.fromkeys(p.hand_civil):
        card = db.get(card_id)
        if card.category is not CardCategory.ACTION:
            continue
        # 未注册处理器的行动卡不可打出
        if card.handler not in effects.ACTION_HANDLERS:
            continue
        # 折扣子行动类: 无合法子行动时不可打出(保证 pending 必可解)
        spec = effects.PENDING_SPECS.get(card.handler)
        if spec is not None and not _pending_actions(db, p, spec):
            continue
        # 额外打出条件(如 frugality 需能增人口)
        condition = effects.PLAY_CONDITIONS.get(card.handler)
        if condition is not None and not condition(db, p):
            continue
        # 选择类行动卡(如 reserves_i)每个合法 option 枚举一个动作
        options = effects.ACTION_OPTIONS.get(card.handler, ("",))
        actions.extend(PlayActionCard(card_id, option) for option in options)
    return actions


def legal_actions(db: CardDB, state: GameState) -> list[Action]:
    """枚举当前玩家全部合法动作(规则见模块 docstring)."""
    if state.terminal:
        return []
    p = state.players[state.current_player]
    if state.pending:
        # 仅生成可结算首个 pending 的动作; PassTurn 兜底(放弃 pending,
        # 官方行动卡效果为强制, 引擎允许放弃, SIMPLIFICATION 见 apply)
        actions = _pending_actions(db, p, state.pending[0])
        actions.append(PassTurn())
        return actions
    takes: list[Action] = [
        TakeCard(i) for i, card_id in enumerate(state.card_row)
        if card_id is not None and _take_card_legal(db, p, i, card_id)
    ]
    if state.round == 1:
        # 第一回合仅能拿牌, 但 PassTurn 恒在末尾(白点耗尽时不致卡死)
        takes.append(PassTurn())
        return takes
    actions: list[Action] = takes
    actions.extend(_develop_actions(db, p))
    actions.extend(_government_actions(db, p))
    actions.extend(_build_actions(db, p))
    actions.extend(_upgrade_actions(db, p))
    actions.extend(_destroy_disband_actions(p))
    actions.extend(_leader_actions(db, p))
    actions.extend(_wonder_actions(db, p))
    actions.extend(_increase_population_actions(db, p))
    actions.extend(_action_card_actions(db, p))
    actions.append(PassTurn())
    return actions
