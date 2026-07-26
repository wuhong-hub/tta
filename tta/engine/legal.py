"""合法动作枚举(官方规则 P1 + P2 相位化).

legal_actions(db, state) 枚举行动者的全部合法动作:
- 终局 -> [];
- pending 非空 -> 仅可结算首个 pending 的动作; 行动者为 pending[0].responder
  (None 时为 current_player)。DeclineResponse 兜底仅当 pending[0].kind 在
  可放弃白名单(events.DECLINABLE_PENDING_KINDS; 强制类如 discard_military
  与强制失去类事件 pending 不可放弃); PassTurn 兜底仅当 pending[0].kind
  可放弃、行动者即 current_player、处于 ACTION 相位且 pending 栈中无他玩家
  responder(防止一次 PassTurn 丢弃他玩家的事件选择 pending 或逃避强制失去);
- phase == POLITICS -> 政治动作(politics.politics_actions, 每回合限 1)
  + SkipPolitics;
- phase == TURN_START -> [](引擎自动相位, 玩家不可行动);
- phase == ACTION 且第一回合(state.round == 1) -> 仅 TakeCard + 末尾 PassTurn;
- 其余情况: TakeCard / DevelopTech / DevelopGovernment / Build / Upgrade /
  Destroy / Disband / PlayLeader / BuildWonderStage / PlayActionCard /
  IncreasePopulation / PlayTactics / CopyTactics,
  PassTurn 恒在末尾(PassTurn 仅在 ACTION 相位合法)。

阵型动作(规则书 p6): PlayTactics 打出手牌阵型 1 红点; CopyTactics 复制
任一对手已公开阵型 2 红点; 两者合计每回合限 1(tactics_this_turn)。

pending 子行动(行动卡压入, 见 effects): 0 行动点, 费用享折扣(下限 0);
breakthrough 的 develop_tech 子行动为 0 行动点全价研发手牌科技。
回合修饰(turn_discounts): 目前仅兵种的 "unit_build" 建造折扣。
选择类行动卡(如 reserves_i)按 effects.ACTION_OPTIONS 每个选项枚举一个
PlayActionCard。

领袖钩子(Task 9): hammurabi 拿领袖牌 -1 白点; hammurabi 红点垫付白点
(官方规则: 每回合一次, 1 红点抵 1 白点, 仅 TakeCard/DevelopTech/Build/
Upgrade 四处挂钩, 见 effects.flexible_actions); frugality 等行动卡的
额外打出条件经 effects.PLAY_CONDITIONS 预判。
"""

from tta.engine import effects, events, military, politics
from tta.engine.actions import (
    Action,
    Build,
    BuildWonderStage,
    ChooseEventOption,
    ColonizeBid,
    ColonizePass,
    ColonizePlayBonus,
    ColonizeSacrifice,
    CopyTactics,
    DeclineResponse,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    DiscardForStrength,
    DiscardMilitary,
    IncreasePopulation,
    PactAccept,
    PactReject,
    PassResponse,
    PassTurn,
    PlayActionCard,
    PlayDefenseBonus,
    PlayLeader,
    PlayTactics,
    SkipPolitics,
    TakeCard,
    Upgrade,
)
from tta.engine.civ import civ_values, hand_limit_civil
from tta.engine.constants import ROW_COSTS
from tta.engine.economy import food_total, resource_total
from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    WORKER_CATEGORIES,
    Age,
    CardCategory,
    Phase,
)
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import GameState, PendingEffect, PlayerState, acting_index

_DECLINABLE_PENDING_KINDS: frozenset[str] = (
    events.DECLINABLE_PENDING_KINDS | frozenset({politics.KIND_WAR_SEIZE})
)
"""可放弃 pending 白名单: 事件/行动卡白名单 + 科技之战夺取(可选效果,
规则书 p3: 胜利者"可以"夺取; 白名单定义于 events, 战争 kind 属 politics,
在此合并以避免 events <-> politics 循环 import)。"""

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
    # hammurabi: 白点不足时每回合一次可用 1 红点抵 1 白点
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
    if card.category is CardCategory.GOVERNMENT and card_id == p.government:
        # 官方规则: 当前政体即游戏区域中的卡, 同名政府牌不可拿取
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
        if card_id == p.government:
            # 官方规则: 不得变更为当前同名政体(和平演变与革命均禁)
            continue
        if p.civil_actions >= 1 and p.science >= card.cost_science:
            actions.append(DevelopGovernment(card_id, False))
        # robespierre: 革命花全部红点(而非全部白点), 合法性按红点判定
        revolution_ok = (
            p.military_actions >= 1
            if effects.revolution_uses_military(db, p)
            else p.civil_actions >= 1
        )
        if revolution_ok and p.science >= card.cost_science_revolution:
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


def _develop_tech_pending_actions(
    db: CardDB, p: PlayerState, discount: int = 0,
) -> list[Action]:
    """develop_tech pending 子行动: 0 行动点研发手牌中一项科技.

    breakthrough 为全价研发(discount=0, 完成后 +science_gain 科技);
    development_of_civilization 事件的 tech 选项带科技费折扣(discount=1)。
    """
    actions: list[Action] = []
    for card_id in dict.fromkeys(p.hand_civil):
        card = db.get(card_id)
        if card.category not in _DEVELOP_CATEGORIES:
            continue
        if p.science < max(0, card.cost_science - discount):
            continue
        actions.append(DevelopTech(card_id))
    return actions


def _pending_actions(
    db: CardDB, p: PlayerState, pending: PendingEffect,
    state: GameState | None = None,
) -> list[Action]:
    """生成可结算首个 pending 的动作(0 行动点, 费用享折扣).

    state 仅个别 kind 需要(事件拿卡牌列, 见 international_agreement);
    legal_actions 恒传入, 行动卡子行动的合法性预判(_action_card_actions)
    不涉及该类 kind, 缺省 None。
    """
    categories = effects.PENDING_BUILD_CATEGORIES.get(pending.kind)
    if categories is not None:
        actions = _build_actions(
            db, p, categories=categories, point_cost=0,
            discount=pending.discount)
        actions += _upgrade_actions(
            db, p, categories=categories, point_cost=0,
            discount=pending.discount)
        return actions
    # 仅升级类 pending(efficient_upgrade): 只生成 Upgrade
    upgrade_categories = effects.PENDING_UPGRADE_CATEGORIES.get(pending.kind)
    if upgrade_categories is not None:
        return _upgrade_actions(
            db, p, categories=upgrade_categories, point_cost=0,
            discount=pending.discount)
    if pending.kind == effects.KIND_WONDER_STAGE:
        return _wonder_actions(db, p, point_cost=0, discount=pending.discount)
    if pending.kind == effects.KIND_DEVELOP_TECH:
        return _develop_tech_pending_actions(db, p, discount=pending.discount)
    if pending.kind == effects.KIND_DISCARD_MILITARY:
        # 回合末弃多余军事牌: 逐张选择直到合规。
        # 法律兜底: 超上限时手牌必非空, 故恒有 DiscardMilitary 可用
        return [DiscardMilitary(card_id)
                for card_id in dict.fromkeys(p.hand_military)]
    if pending.kind == events.KIND_EVENT_MARKETS:
        # development_of_markets: +2 食物或 +2 资源二选一
        return [ChooseEventOption("food"), ChooseEventOption("resource")]
    if pending.kind == events.KIND_EVENT_DESTROY_BUILDING:
        # border_conflict: 选 1 张有工人的城市建筑/农场/矿场卡失去(强制;
        # 压入前已保证非空, 见 events._border_conflict)
        return [
            ChooseEventOption(card_id)
            for card_id in events.destroyable_building_ids(p)
        ]
    if pending.kind == events.KIND_EVENT_DESTROY_URBAN:
        # terrorism: 选 1 张有工人的城市建筑卡摧毁(强制; 压入前已保证非空)
        return [
            ChooseEventOption(card_id)
            for card_id in events.urban_destroyable_ids(p)
        ]
    if pending.kind == events.KIND_EVENT_LOSE_COLONY:
        # independence_declaration: 选 1 个殖民地失去(强制; 压入前已保证非空)
        return [ChooseEventOption(colony) for colony in p.colonies]
    if pending.kind == events.KIND_EVENT_RAVAGES:
        # ravages_of_time: 选 1 个 A/I 奇迹翻面(强制; 压入前已保证非空)
        return [
            ChooseEventOption(card_id)
            for card_id in events.ravages_eligible_wonders(db, p)
        ]
    if pending.kind == events.KIND_EVENT_AGREEMENT:
        # international_agreement: 预算内拿卡牌列的牌, 或 "done" 结束
        if state is None:  # pragma: no cover - legal_actions 恒传入
            return []
        budget = int(pending.context["budget"])
        options = events.agreement_take_options(db, state, p, budget)
        return (
            [ChooseEventOption(str(i)) for i in options]
            + [ChooseEventOption(events.AGREEMENT_DONE)]
        )
    if pending.kind == events.KIND_EVENT_FORAY:
        # foray: 食物/资源组合(按价值共 3), 恒可执行(供给不足尽力而为)
        return [ChooseEventOption(option) for option in events.FORAY_OPTIONS]
    if pending.kind == events.KIND_EVENT_RAIDERS:
        # raiders: 食物/资源组合(按价值共 2), 恒可执行(不足损失到此为止)
        return [ChooseEventOption(option) for option in events.RAIDERS_OPTIONS]
    if pending.kind in events.EVENT_FREE_BUILD:
        # development_of_religion/warfare: 免费建 1 宗教/战士
        return _free_build_actions(p, events.EVENT_FREE_BUILD[pending.kind])
    if pending.kind == events.KIND_EVENT_CIVILIZATION:
        return _civilization_choice_actions(db, p)
    if pending.kind == politics.KIND_COLONIZE_BID:
        return _colonize_bid_actions(db, p, pending)
    if pending.kind == politics.KIND_COLONIZE_SACRIFICE:
        return _colonize_sacrifice_actions(db, p, pending)
    if pending.kind == politics.KIND_AGGRESSION_DEFENSE:
        return _aggression_defense_actions(db, p, pending)
    if pending.kind == politics.KIND_AGGRESSION_PLUNDER:
        # plunder: 食物/资源组合(按价值共 amount), 恒可执行(不足封顶)
        amount = int(pending.context["amount"])
        return [ChooseEventOption(option)
                for option in politics.plunder_options(amount)]
    if pending.kind == politics.KIND_AGGRESSION_RAID:
        # raid: 选 1 个 <= max_age 级城市建筑摧毁(强制); 无合格建筑时
        # PassResponse 跳过该次摧毁(受害者没有可失去的建筑, 不卡死)
        actions = [
            ChooseEventOption(card_id)
            for card_id in politics.raid_eligible_building_ids(
                db, p, Age(str(pending.context["max_age"])))
        ]
        if not actions:
            actions.append(PassResponse())
        return actions
    if pending.kind == politics.KIND_AGGRESSION_ANNEX:
        # annex: 选 1 个殖民地转交攻击方(强制; 压入前已保证非空)
        return [ChooseEventOption(colony) for colony in p.colonies]
    if pending.kind == politics.KIND_AGGRESSION_INFILTRATE:
        # infiltrate: 弃领袖或未完成奇迹(强制; 压入前已保证非空)
        return [ChooseEventOption(option)
                for option in politics.infiltrate_options(p)]
    if pending.kind == politics.KIND_WAR_SEIZE:
        # 科技之战: 胜者夺取败方 1 张特殊科技(可选; 可夺取集合在压入时
        # 快照入 context, 与 war_seize_options 同口径; 放弃由白名单兜底)
        return [ChooseEventOption(card_id)
                for card_id in str(pending.context["options"]).split(",")]
    if pending.kind == politics.KIND_PACT_OFFER:
        # 条约提议: 对方接受或拒绝(恒可响应, 不可放弃)
        return [PactAccept(), PactReject()]
    return []


def _aggression_defense_actions(
    db: CardDB, p: PlayerState, pending: PendingEffect,
) -> list[Action]:
    """侵略防御响应: 奖励牌 / 弃牌 +1 军力 / PassResponse.

    规则书 p4 限制: 打出+弃置的牌总数不能超过防御方总军事行动点数
    (defense_cards 计数, 达上限后仅剩 PassResponse)。PassResponse 恒可用
    (对手可不与你比较, 规则书 p4)。
    """
    actions: list[Action] = []
    used = int(pending.context.get("defense_cards", 0))
    if used < p.military_actions:
        for card_id in dict.fromkeys(p.hand_military):
            card = db.get(card_id)
            if card.category is CardCategory.BONUS and card.defense_bonus > 0:
                actions.append(PlayDefenseBonus(card_id))
            actions.append(DiscardForStrength(card_id))
    actions.append(PassResponse())
    return actions


def _colonize_bid_actions(
    db: CardDB, p: PlayerState, pending: PendingEffect,
) -> list[Action]:
    """殖民竞拍: ColonizeBid(高于当前出价且 <= 可承诺上限) + ColonizePass.

    无军事单位者不可出价(规则书 p7: 必须挑出至少 1 个军事单位, 不能只靠
    奖励牌与殖民修正); ColonizePass 恒可用(退出竞拍)。
    """
    actions: list[Action] = []
    if politics.has_military_unit(p):
        current_bid = int(pending.context.get("current_bid", 0))
        cap = politics.colonization_cap(db, p)
        actions.extend(
            ColonizeBid(amount) for amount in range(current_bid + 1, cap + 1))
    actions.append(ColonizePass())
    return actions


def _colonize_sacrifice_actions(
    db: CardDB, p: PlayerState, pending: PendingEffect,
) -> list[Action]:
    """胜者牺牲结算: 逐张 ColonizePlayBonus + "全选"锚点 ColonizeSacrifice.

    牺牲元组组合枚举爆炸, legal 仅提供"牺牲全部单位"锚点(出价 <= 上限
    保证其恒可履约, 配合奖励牌); 精确子集由 apply 独立校验(见
    politics.colonize_sacrifice), LLM 玩家可构造任意元组动作。
    """
    actions: list[Action] = [
        ColonizePlayBonus(card_id)
        for card_id in dict.fromkeys(p.hand_military)
        if db.get(card_id).category is CardCategory.BONUS
        and db.get(card_id).colonize_bonus > 0
    ]
    all_units = tuple(
        card_id
        for category in sorted(UNIT_CATEGORIES, key=lambda c: c.value)
        for card_id, workers in sorted(p.buildings.get(category.value, {}).items())
        for _ in range(workers)
    )
    if all_units:
        bid = int(pending.context["bid"])
        bonus = int(pending.context.get("bonus", 0))
        strength = (
            military.units_strength(db, p, all_units)
            + civ_values(db, p).colonization
            + bonus
        )
        if strength >= bid:
            actions.append(ColonizeSacrifice(all_units))
    return actions


def _free_build_actions(p: PlayerState, card_id: str) -> list[Action]:
    """事件免费建造 pending: 有可用工人且该卡有空槽 -> [Build(card_id)]."""
    if p.worker_pool < 1:
        return []
    placed = sum(slots.get(card_id, 0) for slots in p.buildings.values())
    if placed >= p.developed.count(card_id):
        return []
    return [Build(card_id)]


def _civilization_choice_actions(db: CardDB, p: PlayerState) -> list[Action]:
    """development_of_civilization 三选一(官方): 仅枚举当前可行的选项.

    官方选项 ① +1 人口付 1 食物(事件固定价, moses 折扣不适用): 需
    yellow_bank > 0 且食物总量 >= 1; ② 建造(引擎拆为 farm_mine/urban 两个
    option, 折扣 1); ③ 研发科技(科技费折扣 1)。全部不可行时仅剩
    DeclineResponse。
    """
    actions: list[Action] = []
    if (p.yellow_bank > 0
            and food_total(db, p) >= events.CIVILIZATION_POPULATION_FOOD_COST):
        actions.append(ChooseEventOption(events.CIVILIZATION_OPTION_POPULATION))
    farm_mine = effects.PENDING_BUILD_CATEGORIES[effects.KIND_BUILD_FARM_MINE]
    if _build_actions(db, p, categories=farm_mine, point_cost=0, discount=1):
        actions.append(ChooseEventOption("farm_mine"))
    if _build_actions(db, p, categories=URBAN_CATEGORIES, point_cost=0,
                      discount=1):
        actions.append(ChooseEventOption("urban"))
    if _develop_tech_pending_actions(db, p, discount=1):
        actions.append(ChooseEventOption("tech"))
    return actions


def _tactics_actions(db: CardDB, state: GameState) -> list[Action]:
    """阵型动作枚举(规则书 p6: 打出 1 红点 / 复制 2 红点, 合计每回合限 1).

    - PlayTactics: 手牌中的 TACTICS 卡, 需 1 军事行动;
    - CopyTactics: 任一对手已公开(tactics_public)的阵型, 需 2 军事行动,
      不消耗手牌; 已是自己当前阵型的卡不再枚举(无意义动作)。
    """
    idx = state.current_player
    p = state.players[idx]
    if p.tactics_this_turn:
        return []
    actions: list[Action] = []
    if p.military_actions >= 1:
        for card_id in dict.fromkeys(p.hand_military):
            if db.get(card_id).category is CardCategory.TACTICS:
                actions.append(PlayTactics(card_id))
    if p.military_actions >= 2:
        copied: dict[str, None] = {}
        for i, other in enumerate(state.players):
            if i == idx or other.tactics is None or not other.tactics_public:
                continue
            if other.tactics == p.tactics:
                continue
            copied[other.tactics] = None
        actions.extend(CopyTactics(card_id) for card_id in copied)
    return actions


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
    """枚举行动者全部合法动作(规则见模块 docstring)."""
    if state.terminal:
        return []
    if state.pending:
        # 行动者 = pending[0].responder(None 时为 current_player);
        # 仅生成可结算首个 pending 的动作; DeclineResponse 兜底(放弃
        # pending[0], 仅可放弃白名单 kind, 强制类如 discard_military 除外);
        # PassTurn 兜底(放弃全部 pending 并推进回合)仅当行动者即
        # current_player、处于 ACTION 相位且栈中无他玩家 responder。
        actor = acting_index(state)
        actions = _pending_actions(
            db, state.players[actor], state.pending[0], state)
        if state.pending[0].kind in _DECLINABLE_PENDING_KINDS:
            actions.append(DeclineResponse())
        if (state.pending[0].kind in _DECLINABLE_PENDING_KINDS
                and actor == state.current_player
                and state.phase is Phase.ACTION
                and all(e.responder in (None, state.current_player)
                        for e in state.pending)):
            # PassTurn 兜底(丢弃全部 pending 并推进回合): 仅可放弃类 kind
            # (强制失去类事件 pending 如 raiders/border_conflict 不允许借此
            # 逃避); 且行动者即 current_player、ACTION 相位、栈中无他玩家
            # responder(防止一次 PassTurn 丢弃他玩家的事件选择 pending)
            actions.append(PassTurn())
        return actions
    if state.players[state.current_player].resigned:
        # 体面退出者回合: 文明已移除, 仅剩 PassTurn 推进轮换
        return [PassTurn()]
    if state.phase is Phase.POLITICS:
        # 政治阶段: 政治动作(每回合限 1, 见 politics.py) + SkipPolitics;
        # international_agreement 的"跳过下一次政治行动"生效时仅剩 SkipPolitics
        if state.players[state.current_player].miss_political_action:
            return [SkipPolitics()]
        politics_moves: list[Action] = politics.politics_actions(db, state)
        politics_moves.append(SkipPolitics())
        return politics_moves
    if state.phase is not Phase.ACTION:
        # TURN_START 为引擎自动相位, 玩家不可行动
        return []
    p = state.players[state.current_player]
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
    actions.extend(_tactics_actions(db, state))
    actions.append(PassTurn())
    return actions
