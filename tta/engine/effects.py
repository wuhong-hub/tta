"""领袖/特殊科技静态加成与行动卡结算的处理器注册表.

civ.py 在合成文明数值的最后一步调用 static_bonuses, 叠加领袖与已研发
特殊科技(SPECIAL 类别)卡提供的静态加成; 各卡的 handler 字段为注册表
STATIC_BONUS_HANDLERS 中的处理器名, 空 handler 或未注册者跳过。
apply.py 的 PlayActionCard 分支按卡的 handler 字段查 ACTION_HANDLERS
结算行动卡效果。

行动卡行为(Task 7 实现机制, Task 9 注册 Age A 首批 handler, Task 10
注册时代 I 实例并新增选择类):
1. 即时收益类(如 stockpile): handler 直接改 state;
2. 折扣子行动类(如 rich_land): handler 经 push_pending 压入
   PendingEffect, 下一动作必须是对应 Build/Upgrade/BuildWonderStage
   (0 行动点、费用享折扣), 执行后 pop; breakthrough 压入
   develop_tech pending(0 行动点全价研发, 完成后 +X 科技);
3. 回合修饰类(如 patriotism): 立即调整行动点并写 turn_discounts;
4. 选择类(如 reserves_i): 合法 option 见 ACTION_OPTIONS, 打出动作
   携带 option, handler 按 option 结算。

Age A 领袖钩子(Task 9):
- alexander_the_great / julius_caesar / homer: STATIC_BONUS_HANDLERS
  静态加成(经 civ_values 生效);
- homer: turn_start_discounts 在每回合行动点恢复时注入 unit_build 折扣;
- moses: population_food_discount 使增人口食物费 -1(挂钩于
  increase_population, 调用点为 IncreasePopulation 动作(apply)与
  frugality handler);
- hammurabi: leader_take_discount 使拿领袖牌 -1 白点; flexible_actions
  实现"每回合一次, 1 红点当 1 白点"(官方规则, 见函数 docstring);
- aristotle: on_take_card_gains 在 apply TakeCard 结算时 +1 科技。

时代 I 钩子(Task 10):
- michelangelo: STATIC_BONUS(寺庙/剧院/奇迹每 1 笑脸 +1 文化);
  wonder_take_surcharge 使拿奇迹不付每已完成奇迹 +1 的白点(挂钩于
  legal/apply 的 TakeCard 奇迹费用);
- joan_of_arc: STATIC_BONUS(+1 军事行动 +1 文化; 寺庙与政体每 1 笑脸
  +1 军力; 政治看牌 P2-DEFERRED);
- leonardo_da_vinci: STATIC_BONUS(最佳实验室/图书馆每级 +1 科技);
  on_develop_tech_gains 在 apply DevelopTech 结算时 +1 资源;
- genghis_khan / christopher_columbus / frederick_barbarossa:
  互动能力(阵型/殖民/红点建军)P2-DEFERRED, 仅卡文本;
- 特殊科技: warfare / code_of_laws / cartography 静态加成;
  masonry 建造折扣与双阶段见 P3-T6 钩子(construction_urban_discount /
  wonder_stages_per_action);
- 奇迹: great_wall 经 static_bonuses 的奇迹 handler 维度提供
  每步兵/炮兵 +1 军力; st_peters_basilica 他文明笑脸与 taj_mahal
  蓝点/换领袖折扣 P2-DEFERRED。

时代 II 钩子(Task 11):
- napoleon_bonaparte: STATIC_BONUS(+2 军事行动; 每种军事单位类型
  +2 军力, 同种多工人只计 1 种);
- maximilien_robespierre: STATIC_BONUS(+1 军事行动);
  revolution_uses_military 使革命花全部红点而非全部白点(挂钩于
  legal/apply 的 DevelopGovernment); 革命时 +3 笑脸(一次性)
  P2-DEFERRED;
- isaac_newton: STATIC_BONUS(最佳实验室/图书馆每级 +1 科技, 同
  leonardo 口径); on_develop_tech_gains 在 apply DevelopTech 结算时
  拿回 1 白点;
- william_shakespeare: STATIC_BONUS(+1 笑脸 + 每对图书馆-剧院 +2 文化,
  T13; 配对口径: 图书馆按已研发、剧院按有工人卡); 图书馆/剧院配对建造
  折扣 -1 资源(P3-T6, 见 shakespeare_build_discount; 研发 -1 白点
  P2-DEFERRED); james_cook 殖民与弃军事牌 P2-DEFERRED, 仅卡文本;
- j_s_bach: STATIC_BONUS(每个有工人剧院 +1 文化, T13); 研发剧院 -2 科技
  与每回合一次特殊升级(P3-T6, 见 theater_science_discount /
  bach_upgrade_available);
- 特殊科技: strategy / justice_system / navigation 静态加成;
  justice_system 研发时 +3 蓝点(on_develop_tech_gains 按卡 id);
  architecture 建造折扣与三阶段(P3-T6, 同 masonry 口径);
- 奇迹: transcontinental_railroad 最佳矿场翻倍与 ocean_liner_service
  免费增人口 P2-DEFERRED; kremlin 的 -1 笑脸经 wonder_bonus 静态生效。

时代 III 钩子(Task 12):
- albert_einstein: STATIC_BONUS(最佳实验室/图书馆每级 +1 科技, 同
  leonardo 口径); on_develop_tech_gains 在 apply DevelopTech 结算时
  +3 文化(PDF 图标为文化竖琴, 每次研发触发, 非一次性);
- mahatma_gandhi: STATIC_BONUS(+2 文化, PDF 图标为文化竖琴);
  不能打侵略/战争与双倍军事行动 P2-DEFERRED;
- charlie_chaplin: STATIC_BONUS(+2 笑脸; 最佳剧院按工人数 × 卡面文化
  再计一份文化, 即双倍);
- sid_meier: STATIC_BONUS(实验室每级 +1 文化、每个实验室 -1 科技,
  按已研发卡计, 同 leonardo 口径);
- bill_gates: 实验室产资源(P3-T4, 见 economy 的 LAB 口径); 被替换离场时
  +文化 = Σ 每个实验室工人 × 该卡时代等级(即时, 见 gates_lab_bonus_culture,
  挂钩于 apply._play_leader; 终局奖励已在 P2-T12 实现, 见
  events._bill_gates_endgame);
- winston_churchill: 每回合二选一(P3-T4, 回合开始选择机制见 choices):
  +3 文化, 或 +3 科技 + 本回合军事建造折扣 3;
- 特殊科技: military_theory / civil_service / satellites 静态加成;
  civil_service 研发时 +3 蓝点(on_develop_tech_gains 按卡 id);
  engineering 建造折扣与四阶段(P3-T6, 同 masonry 口径);
- 奇迹: internet(城市建筑每 1 科技/文化产出 +1 文化)、
  first_space_flight(每项已研发科技每级 +1 文化)、
  fast_food_chains(农场/矿场每卡 +2 文化, 城市建筑/兵种每卡 +1 文化)
  经 static_bonuses 的奇迹 handler 维度静态生效; hollywood 建成时
  一次性得分 P2-DEFERRED。

engine 包不得 import tta.cards, 故领袖卡 id 以字符串常量定义于此。
"""

from collections.abc import Callable
from dataclasses import replace

from tta.engine import economy
from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    WORKER_CATEGORIES,
    Age,
    CardCategory,
)
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import GameState, PendingEffect, PlayerState, replace_player
from tta.engine.tracks import population_cost

STATIC_BONUS_HANDLERS: dict[str, Callable[[CardDB, PlayerState], dict[str, int]]] = {}
"""静态加成处理器注册表: handler 名 -> (db, player) -> 加成 dict."""

ACTION_HANDLERS: dict[
    str, Callable[[GameState, int, CardDB, str], GameState]] = {}
"""行动卡结算处理器注册表: handler 名 -> (state, 玩家 idx, db, option) -> 新 state.

apply 在调用前已完成: 扣 1 白点、手牌移除该卡、卡入弃牌堆; handler 只负责
效果结算与 pending 压栈。option 为选择类行动卡(见 ACTION_OPTIONS)打出时
的选项, 非选择类恒为 ""。

handler 名全局唯一: 同名行动卡的不同时代实例(X 加成不同)以带时代后缀的
卡 id 各自注册(如 Age A "rich_land" X=1, 时代 I "rich_land_i" X=2),
由工厂函数按 X 参数生成。Task 9 注册 Age A 首批, Task 10 注册时代 I。
"""

ACTION_OPTIONS: dict[str, tuple[str, ...]] = {}
"""选择类行动卡 handler 名 -> 合法 option 取值(如 reserves_i 二选一).

legal 为每个 option 枚举一个 PlayActionCard; 未注册者仅枚举 option="" 的
默认形式。
"""

PENDING_SPECS: dict[str, PendingEffect] = {}
"""折扣子行动类行动卡 handler 名 -> 其压入的 PendingEffect 样例.

legal 用它做打出预判: 无对应合法子行动时该行动卡不可打出。handler 实际
压入的 PendingEffect 须与此处一致(注册时成对维护)。
"""

PLAY_CONDITIONS: dict[str, Callable[[CardDB, PlayerState], bool]] = {}
"""行动卡额外打出条件: handler 名 -> (db, player) -> 是否可打出.

用于非 pending 类的合法性预判(如 frugality 需能增人口); 未注册者恒可打出
(仍须通过 PENDING_SPECS 预判, 若有)。
"""

UNIT_BUILD_DISCOUNT_KEY = "unit_build"
"""turn_discounts 中兵种建造折扣的键(回合修饰类行动卡/领袖钩子写入)."""

HAMMURABI_FLEX_KEY = "hammurabi_flex"
"""turn_discounts 中 hammurabi 本回合红点垫付已用标记的键(回合末清空)."""

# Age A 领袖卡 id(engine 不 import tta.cards, 以字符串常量引用)
LEADER_ALEXANDER = "alexander_the_great"
LEADER_ARISTOTLE = "aristotle"
LEADER_HAMMURABI = "hammurabi"
LEADER_HOMER = "homer"
LEADER_JULIUS_CAESAR = "julius_caesar"
LEADER_MOSES = "moses"

# 时代 I 领袖卡 id
LEADER_MICHELANGELO = "michelangelo"
LEADER_JOAN_OF_ARC = "joan_of_arc"
LEADER_LEONARDO = "leonardo_da_vinci"
LEADER_GENGHIS_KHAN = "genghis_khan"           # P2-DEFERRED, 无钩子
LEADER_COLUMBUS = "christopher_columbus"       # P2-DEFERRED, 无钩子
LEADER_BARBAROSSA = "frederick_barbarossa"     # P2-DEFERRED, 无钩子

# 时代 II 领袖卡 id
LEADER_SHAKESPEARE = "william_shakespeare"         # 静态 +1 笑脸 + 配对文化(T13)
LEADER_COOK = "james_cook"                         # P2-DEFERRED, 无钩子
LEADER_NAPOLEON = "napoleon_bonaparte"
LEADER_ROBESPIERRE = "maximilien_robespierre"
LEADER_BACH = "j_s_bach"                           # 静态每剧院 +1 文化(T13)
LEADER_NEWTON = "isaac_newton"

# 时代 III 领袖卡 id
LEADER_EINSTEIN = "albert_einstein"
LEADER_GANDHI = "mahatma_gandhi"
LEADER_CHAPLIN = "charlie_chaplin"
LEADER_BILL_GATES = "bill_gates"                   # 产资源见 economy, 离场见下
LEADER_CHURCHILL = "winston_churchill"             # 每回合二选一, 见 choices
LEADER_SID_MEIER = "sid_meier"

# 时代 II 特殊科技卡 id(justice_system 研发时 +3 蓝点, 按卡 id 挂钩)
SPECIAL_JUSTICE_SYSTEM = "justice_system"

# 时代 III 特殊科技卡 id(civil_service 研发时 +3 蓝点, 按卡 id 挂钩)
SPECIAL_CIVIL_SERVICE = "civil_service"

KIND_BUILD_FARM_MINE = "build_farm_mine"
KIND_BUILD_URBAN = "build_urban"
KIND_WONDER_STAGE = "wonder_stage"
KIND_DEVELOP_TECH = "develop_tech"
KIND_UPGRADE_FARM_MINE_URBAN = "upgrade_farm_mine_urban"
KIND_DISCARD_MILITARY = "discard_military"
"""回合末弃多余军事牌 pending(turn.py 压入, context["count"] = 需弃数量)."""

PENDING_BUILD_CATEGORIES: dict[str, frozenset[CardCategory]] = {
    KIND_BUILD_FARM_MINE: frozenset({CardCategory.FARM, CardCategory.MINE}),
    KIND_BUILD_URBAN: URBAN_CATEGORIES,
}
"""建造类 pending kind -> 允许的卡牌类别(Build/Upgrade 目标须在其中)."""

PENDING_UPGRADE_CATEGORIES: dict[str, frozenset[CardCategory]] = {
    KIND_UPGRADE_FARM_MINE_URBAN: (
        frozenset({CardCategory.FARM, CardCategory.MINE}) | URBAN_CATEGORIES
    ),
}
"""仅升级类 pending kind -> 允许的卡牌类别(efficient_upgrade, 不含兵种)."""

DECLINABLE_PENDING_KINDS: frozenset[str] = frozenset({
    KIND_BUILD_FARM_MINE,
    KIND_BUILD_URBAN,
    KIND_WONDER_STAGE,
    KIND_DEVELOP_TECH,
    KIND_UPGRADE_FARM_MINE_URBAN,
})
"""可放弃(DeclineResponse)的 pending kind 白名单(非强制类).

强制类(如 KIND_DISCARD_MILITARY: 恒有 DiscardMilitary 可执行)不在名单;
事件选择类 kind 由 events.py 并入(见 events.DECLINABLE_PENDING_KINDS)。
"""


def push_pending(state: GameState, pending: PendingEffect) -> GameState:
    """将子行动压入 pending 栈(供折扣子行动类 handler 使用)."""
    return replace(state, pending=state.pending + (pending,))


def static_bonuses(db: CardDB, p: PlayerState) -> dict[str, int]:
    """累加领袖、已研发特殊科技卡与已完成奇迹的静态文明加成.

    遍历 p.leader、p.developed 中 SPECIAL 类别卡与 p.wonders 中有 handler
    的奇迹卡(Task 10 起, 如 great_wall), 按 handler 字段查
    STATIC_BONUS_HANDLERS; 无 handler 或未注册者跳过。返回的 dict 键为
    收益名(同 GovernmentStats.bonus 语义)。
    """
    card_ids: list[str] = []
    if p.leader is not None:
        card_ids.append(p.leader)
    for card_id in p.developed:
        card = db.cards.get(card_id)
        if card is not None and card.category is CardCategory.SPECIAL:
            card_ids.append(card_id)
    # 翻面奇迹(ravages_of_time)效果失效, 不参与静态加成
    card_ids.extend(w for w in p.wonders if w not in p.wonders_facedown)

    result: dict[str, int] = {}
    for card_id in card_ids:
        card = db.cards.get(card_id)
        if card is None or not card.handler:
            continue
        handler = STATIC_BONUS_HANDLERS.get(card.handler)
        if handler is None:
            continue
        for key, value in handler(db, p).items():
            result[key] = result.get(key, 0) + value
    return result


# --- Age A 领袖钩子 -----------------------------------------------------------


def _alexander_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """alexander: 每个军事单位(兵种卡上的工人)+1 军力."""
    units = sum(
        workers
        for category in UNIT_CATEGORIES
        for workers in p.buildings.get(category.value, {}).values()
    )
    return {"strength": units} if units else {}


def _julius_caesar_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """julius_caesar: +1 军力 +1 军事行动(双政治一次性见 politics P2-T10)."""
    return {"strength": 1, "military_actions": 1}


def _homer_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """homer: +1 笑脸(替换滑入奇迹 P2-DEFERRED)."""
    return {"happiness": 1}


STATIC_BONUS_HANDLERS.update({
    LEADER_ALEXANDER: _alexander_bonus,
    LEADER_JULIUS_CAESAR: _julius_caesar_bonus,
    LEADER_HOMER: _homer_bonus,
})


def turn_start_discounts(db: CardDB, p: PlayerState) -> dict[str, int]:
    """回合行动点恢复时注入的 turn_discounts(当前仅 homer 军事建造折扣 1)."""
    if p.leader == LEADER_HOMER:
        return {UNIT_BUILD_DISCOUNT_KEY: 1}
    return {}


def population_food_discount(db: CardDB, p: PlayerState) -> int:
    """增人口食物费折扣(moses: -1)."""
    return 1 if p.leader == LEADER_MOSES else 0


def increase_population_cost(db: CardDB, p: PlayerState) -> int:
    """增人口实际食物费 = 轨道人口费 - 领袖折扣(下限 0)."""
    return max(0, population_cost(p.yellow_bank) - population_food_discount(db, p))


def can_increase_population(db: CardDB, p: PlayerState) -> bool:
    """能否增人口: 黄点银行非空且食物(含 trade_routes 替换)足够支付人口费."""
    if p.yellow_bank <= 0:
        return False
    food = economy.food_total(db, p) + trade_routes_substitution(db, p, "food")
    return food >= increase_population_cost(db, p)


def increase_population(db: CardDB, p: PlayerState) -> PlayerState:
    """增人口结算(共用): 支付食物费(含 moses 折扣), 黄点银行 -1, 空闲工人 +1.

    调用点: apply 的 IncreasePopulation 动作(另扣 1 白点)与 frugality
    行动卡 handler(不扣行动点)。本函数不含行动点扣减。食物费经
    pay_with_trade_routes 结算(trade_routes B 侧可用 1 资源抵 1 食物)。
    """
    p = pay_with_trade_routes(db, p, "food", increase_population_cost(db, p))
    return replace(p, yellow_bank=p.yellow_bank - 1,
                   worker_pool=p.worker_pool + 1)


def leader_take_discount(db: CardDB, p: PlayerState) -> int:
    """从卡牌列拿领袖牌的白点折扣(hammurabi: -1)."""
    return 1 if p.leader == LEADER_HAMMURABI else 0


def flexible_actions(db: CardDB, p: PlayerState) -> int:
    """可用于垫付白点费用的红点数(hammurabi: 0 或 1; 否则 0).

    官方规则: hammurabi 每回合一次, 可将 1 个军事行动当作内政行动使用。
    实现为: 白点不足支付白点费用时, 可用 1 红点抵 1 白点(每次垫付最多
    1 点, 且本回合限一次, 已用标记存于 turn_discounts 并在回合末清空),
    仅 legal/apply 的 TakeCard / DevelopTech / Build / Upgrade 四处挂钩,
    其余白点花费(PlayLeader / Destroy / BuildWonderStage 等)不垫付。
    """
    if p.leader != LEADER_HAMMURABI:
        return 0
    if p.turn_discounts.get(HAMMURABI_FLEX_KEY, 0):
        return 0
    return 1 if p.military_actions >= 1 else 0


# --- 条约效果(P3-T5): trade_routes / scientific_cooperation -------------------------

PACT_TRADE_ROUTES = "trade_routes_agreement"
"""贸易路线协议(时代 I 对称条约)卡 id."""

PACT_SCIENTIFIC_COOPERATION = "scientific_cooperation"
"""科学合作(时代 II 对称条约)卡 id."""

TRADE_ROUTES_USED_KEY = "trade_routes_used"
"""turn_discounts 中 trade_routes 本回合替换已用标记的键(回合末清空)."""

SCIENTIFIC_COOPERATION_DISCOUNT = 2
"""scientific_cooperation: 研发科技费 -2(对称双方可用; 卡面无 each turn, 不限次)."""

SCIENTIFIC_COOPERATION_PARTNER_COST = 1
"""scientific_cooperation: 研发结算时缔约对方支付的科技(强制, 下限 0)."""

# 本方侧 -> (主货币, 替换货币): A 侧付资源可用食物抵; B 侧付食物可用资源抵
_TRADE_ROUTES_SUBSTITUTE: dict[str, tuple[str, str]] = {
    "A": ("resource", "food"),
    "B": ("food", "resource"),
}


def pact_partner_seat(
    players: tuple[PlayerState, ...], idx: int, card_id: str,
) -> int | None:
    """同录同一条约卡 id 的另一玩家座位(缔约对方); 无则 None."""
    for j, other in enumerate(players):
        if j != idx and any(cid == card_id for cid, _ in other.pacts):
            return j
    return None


def _kind_total(db: CardDB, p: PlayerState, kind: str) -> int:
    if kind == "food":
        return economy.food_total(db, p)
    if kind == "resource":
        return economy.resource_total(db, p)
    msg = f'kind 须为 "food" 或 "resource", 收到 {kind!r}'
    raise ValueError(msg)


def trade_routes_substitute_kind(
    db: CardDB, p: PlayerState, kind: str,
) -> str | None:
    """trade_routes: 支付 kind 费用时可垫付的对方货币种类; 不可替换返回 None.

    卡牌数值表 v1.09 p3: A 侧 "Can use 1食物 instead of 1资源 each turn",
    B 侧 "Can use 1资源 instead of 1食物 each turn"。每回合一次(已用标记存
    turn_discounts, 回合末行动点恢复时清空); 替换货币须持有 >= 1。

    唯一性前提: 官方规则每方至多参与一项条约(politics.propose_pact 接受
    新约时既有约失效), 故 p.pacts 中 trade_routes 至多一条, 循环命中即
    返回不遗漏。
    """
    for card_id, side in p.pacts:
        if card_id != PACT_TRADE_ROUTES:
            continue
        primary, substitute = _TRADE_ROUTES_SUBSTITUTE[side]
        if (kind == primary
                and not p.turn_discounts.get(TRADE_ROUTES_USED_KEY, 0)
                and _kind_total(db, p, substitute) >= 1):
            return substitute
        return None
    return None


def trade_routes_substitution(db: CardDB, p: PlayerState, kind: str) -> int:
    """trade_routes 可垫付点数(0 或 1), legal 费用口径与 apply 同口径."""
    return 1 if trade_routes_substitute_kind(db, p, kind) is not None else 0


def pay_with_trade_routes(
    db: CardDB, p: PlayerState, kind: str, amount: int,
) -> PlayerState:
    """economy.pay 入口包装: trade_routes 替换支付(legal/apply 支付统一口径).

    SIMPLIFICATION: 官方为玩家主动选择是否替换; 引擎确定性口径仅当主货币
    不足且差额恰为 1 时启用(替换 = 对方货币 1 点 + 主货币 amount-1 点两次
    确定性 pay, 并写已用标记), 主货币足够时不替换(P4 可改显式选择);
    其余情况与 economy.pay 完全一致。
    """
    substitute = (
        trade_routes_substitute_kind(db, p, kind)
        if 0 < amount == _kind_total(db, p, kind) + 1
        else None
    )
    if substitute is None:
        return economy.pay(db, p, kind, amount)
    p = economy.pay(db, p, substitute, 1)
    p = economy.pay(db, p, kind, amount - 1)
    discounts = dict(p.turn_discounts)
    discounts[TRADE_ROUTES_USED_KEY] = 1
    return replace(p, turn_discounts=discounts)


def scientific_cooperation_discount(p: PlayerState) -> int:
    """研发科技(DevelopTech)的科技费折扣(scientific_cooperation: -2).

    卡牌数值表 v1.09 p3: "Discover a technology for -2💡, other player pays
    1💡"(对称, 双方可用)。卡面无 "each turn" 字样 -> 不限次(对照
    trade_routes 的 each turn); 对方支付 1 科技为强制, 不足时扣到 0
    (见 apply._develop_tech)。政府变更不属 "discover a technology", 不适用。
    """
    if any(cid == PACT_SCIENTIFIC_COOPERATION for cid, _ in p.pacts):
        return SCIENTIFIC_COOPERATION_DISCOUNT
    return 0


_TECH_TAKE_CATEGORIES = (
    WORKER_CATEGORIES
    | frozenset({CardCategory.SPECIAL, CardCategory.GOVERNMENT})
)
"""aristotle 视野内的"科技牌"类别(工人科技 ∪ 特殊科技 ∪ 政府)."""


def on_take_card_gains(
    db: CardDB, p: PlayerState, card: CardDefinition,
) -> dict[str, int]:
    """TakeCard 结算时的即时收益(aristotle: 拿科技牌 +1 科技)."""
    if p.leader == LEADER_ARISTOTLE and card.category in _TECH_TAKE_CATEGORIES:
        return {"science": 1}
    return {}


# --- 时代 I 领袖/特殊科技/奇迹钩子(Task 10) -------------------------------------

_TECH_LEVEL = {Age.A: 1, Age.I: 2, Age.II: 3, Age.III: 4}
"""科技等级 = 时代序(A=1, I=2, II=3, III=4).

官方卡面"等级"即时代标记; Age A 计 1 级(实现者解释, 见 Task 10 报告)。
"""


def _happiness_from(
    db: CardDB, p: PlayerState, categories: tuple[CardCategory, ...],
) -> int:
    """指定城市建筑类别上工人提供的笑脸总数(工人数 × 卡面笑脸)."""
    total = 0
    for category in categories:
        for card_id, workers in p.buildings.get(category.value, {}).items():
            if workers > 0:
                produces = db.get(card_id).urban_produces
                total += produces.get("happiness", 0) * workers
    return total


def _michelangelo_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """michelangelo: 寺庙/剧院/已完成奇迹每提供 1 笑脸, +1 文化."""
    culture = _happiness_from(
        db, p, (CardCategory.TEMPLE, CardCategory.THEATER))
    culture += sum(
        db.get(card_id).wonder_bonus.get("happiness", 0)
        for card_id in p.wonders
        if card_id not in p.wonders_facedown  # 翻面奇迹效果失效
    )
    return {"culture": culture} if culture else {}


def _joan_of_arc_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """joan_of_arc: +1 军事行动 +1 文化; 寺庙与政体每 1 笑脸 +1 军力.

    政治阶段看下一事件 P2-DEFERRED。
    """
    strength = _happiness_from(db, p, (CardCategory.TEMPLE,))
    government = db.get(p.government).government
    if government is not None:
        strength += government.bonus.get("happiness", 0)
    return {"military_actions": 1, "culture": 1, "strength": strength}


def _leonardo_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """leonardo: 最佳实验室/图书馆每级 +1 科技.

    SIMPLIFICATION: 按已研发卡计(不要求卡上有工人)。
    """
    best = 0
    for card_id in p.developed:
        card = db.get(card_id)
        if card.category in (CardCategory.LAB, CardCategory.LIBRARY):
            best = max(best, _TECH_LEVEL[card.age])
    return {"science": best} if best else {}


def _warfare_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """warfare(特殊科技): +1 军力 +1 军事行动."""
    return {"strength": 1, "military_actions": 1}


def _code_of_laws_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """code_of_laws(特殊科技): +1 内政行动."""
    return {"civil_actions": 1}


def _cartography_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """cartography(特殊科技): +1 殖民修正(殖民费 -2 P2-DEFERRED)."""
    return {"colonization": 1}


def _great_wall_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """great_wall(奇迹): 每个步兵/炮兵单位 +1 军力."""
    units = sum(
        workers
        for category in (CardCategory.INFANTRY, CardCategory.ARTILLERY)
        for workers in p.buildings.get(category.value, {}).values()
    )
    return {"strength": units} if units else {}


STATIC_BONUS_HANDLERS.update({
    LEADER_MICHELANGELO: _michelangelo_bonus,
    LEADER_JOAN_OF_ARC: _joan_of_arc_bonus,
    LEADER_LEONARDO: _leonardo_bonus,
    "warfare": _warfare_bonus,
    "code_of_laws": _code_of_laws_bonus,
    "cartography": _cartography_bonus,
    "great_wall": _great_wall_bonus,
})


def wonder_take_surcharge(db: CardDB, p: PlayerState) -> int:
    """拿奇迹牌的额外白点费 = 已完成奇迹数(michelangelo: 免除)."""
    if p.leader == LEADER_MICHELANGELO:
        return 0
    return len(p.wonders)


def on_develop_tech_gains(
    db: CardDB, p: PlayerState, card_id: str = "",
) -> PlayerState:
    """DevelopTech 结算后的即时收益(领袖钩子 + 特殊科技自身效果).

    - leonardo: +1 资源(蓝点入最低级矿场);
    - isaac_newton: 拿回 1 白点(SIMPLIFICATION: 研发兵种科技所花红点
      也以白点形式拿回; breakthrough pending 0 行动点研发同样触发);
    - albert_einstein: +3 文化(每次研发触发, 非一次性);
    - justice_system / civil_service(特殊科技自身): 研发时立即 +3 蓝点。

    调用点为 apply 的 DevelopTech(含 breakthrough pending 子行动);
    变更政体(DevelopGovernment)不触发。
    """
    if p.leader == LEADER_LEONARDO:
        p = economy.gain_tokens(db, p, "resource", 1)
    elif p.leader == LEADER_NEWTON:
        p = replace(p, civil_actions=p.civil_actions + 1)
    elif p.leader == LEADER_EINSTEIN:
        p = replace(p, culture=p.culture + 3)
    if card_id in (SPECIAL_JUSTICE_SYSTEM, SPECIAL_CIVIL_SERVICE):
        p = replace(p, blue_bank=p.blue_bank + 3)
    return p


# --- 时代 II 领袖/特殊科技钩子(Task 11) ---------------------------------------


def _napoleon_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """napoleon: +2 军事行动; 每种军事单位类型(有工人的兵种卡)+2 军力."""
    unit_types = sum(
        1
        for category in UNIT_CATEGORIES
        for workers in p.buildings.get(category.value, {}).values()
        if workers > 0
    )
    return {"military_actions": 2, "strength": 2 * unit_types}


def _robespierre_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """robespierre: +1 军事行动(革命红点费见 revolution_uses_military)."""
    return {"military_actions": 1}


def revolution_uses_military(db: CardDB, p: PlayerState) -> bool:
    """革命是否花全部红点而非全部白点(robespierre).

    挂钩于 legal 的 DevelopGovernment 合法性与 apply 的革命扣点;
    革命时 +3 笑脸(一次性)P2-DEFERRED。
    """
    return p.leader == LEADER_ROBESPIERRE


def _newton_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """isaac_newton: 最佳实验室/图书馆每级 +1 科技(同 leonardo 口径).

    SIMPLIFICATION: 按已研发卡计(不要求卡上有工人)。
    """
    best = 0
    for card_id in p.developed:
        card = db.get(card_id)
        if card.category in (CardCategory.LAB, CardCategory.LIBRARY):
            best = max(best, _TECH_LEVEL[card.age])
    return {"science": best} if best else {}


def _strategy_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """strategy(特殊科技): +3 军力 +2 军事行动."""
    return {"strength": 3, "military_actions": 2}


def _justice_system_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """justice_system(特殊科技): +1 内政行动(研发 +3 蓝点见 on_develop)."""
    return {"civil_actions": 1}


def _navigation_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """navigation(特殊科技): +2 殖民修正(殖民 P2-DEFERRED)+3 军力."""
    return {"colonization": 2, "strength": 3}


SHAKESPEARE_PAIR_CULTURE = 2
"""shakespeare 每对图书馆-剧院的文化(PDF 第 2 页: 2/lib-theatre pair)."""


def _theater_count(p: PlayerState) -> int:
    """在场剧院数 = 有工人的剧院卡数(每卡 1 次, 与工人数无关; 同 chaplin 口径)."""
    return sum(
        1
        for workers in p.buildings.get(CardCategory.THEATER.value, {}).values()
        if workers > 0
    )


def _shakespeare_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """shakespeare: +1 笑脸; 每对图书馆-剧院 +2 文化(PDF 第 2 页).

    配对口径(SIMPLIFICATION): 图书馆按已研发卡计(同 leonardo 口径), 剧院
    按有工人的卡计(同 chaplin 口径); 对数 = min(图书馆数, 剧院数)。
    图书馆/剧院配对建造折扣见 shakespeare_build_discount(P3-T6)。
    """
    libraries = sum(
        1
        for card_id in p.developed
        if db.get(card_id).category is CardCategory.LIBRARY
    )
    pairs = min(libraries, _theater_count(p))
    result: dict[str, int] = {"happiness": 1}
    if pairs:
        result["culture"] = SHAKESPEARE_PAIR_CULTURE * pairs
    return result


def _bach_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """j_s_bach: 每个剧院 +1 文化(PDF 第 2 页; 有工人的卡, 同 chaplin 口径).

    剧院研发折扣(-2 科技)与每回合升级能力见下方 P3-T6 钩子。
    """
    theaters = _theater_count(p)
    return {"culture": theaters} if theaters else {}


STATIC_BONUS_HANDLERS.update({
    LEADER_NAPOLEON: _napoleon_bonus,
    LEADER_ROBESPIERRE: _robespierre_bonus,
    LEADER_NEWTON: _newton_bonus,
    LEADER_SHAKESPEARE: _shakespeare_bonus,
    LEADER_BACH: _bach_bonus,
    "strategy": _strategy_bonus,
    "justice_system": _justice_system_bonus,
    "navigation": _navigation_bonus,
})


# --- 建造/研发折扣与奇迹多阶段钩子(P3-T6) ------------------------------------------

SHAKESPEARE_BUILD_DISCOUNT = 1
"""shakespeare: 图书馆/剧院配对时建造/升级对方的资源费折扣(PDF 第 2 页)."""

BACH_THEATER_SCIENCE_DISCOUNT = 2
"""j_s_bach: 研发剧院科技的科技费折扣(PDF 第 2 页, 图标为科技)."""

BACH_UPGRADE_KEY = "bach_upgrade"
"""turn_discounts 中 bach 每回合一次特殊升级已用标记的键(回合末清空)."""

# masonry 系列(特殊科技 CONSTRUCTION): 卡 id -> 每白点可建奇迹阶段数
CONSTRUCTION_STAGES_PER_ACTION = {
    "masonry": 2, "architecture": 3, "engineering": 4,
}
"""PDF 第 1 页 Construction 区: "2/3/4 stages per ⚪"."""

CONSTRUCTION_URBAN_MAX = {"masonry": 1, "architecture": 2, "engineering": 3}
"""PDF 第 1 页 Construction 区: 城市建筑折扣上限 "(max 1/2/3)"."""

_CONSTRUCTION_LEVEL = {Age.A: 0, Age.I: 1, Age.II: 2, Age.III: 3}
"""城市建筑建造折扣的"级" = 时代序(A 计 0 级).

官方规则书 "Construction Technologies and Upgrading Urban Buildings" 例:
masonry 下时代 A 实验室仍全价(0 级无折扣), 时代 I -1; 与 _TECH_LEVEL
(A=1) 口径不同, 勿混用。
"""


def shakespeare_build_discount(
    db: CardDB, p: PlayerState, category: CardCategory,
) -> int:
    """shakespeare 配对建造/升级资源折扣(0 或 1, 同类型多卡不叠加).

    PDF 第 2 页: 有图书馆时剧院建造 -1 资源, 反之亦然。配对条件按已研发
    卡计(图书馆与剧院均取 developed, 一次动作至多 -1)。研发时的 -1 内政
    行动折扣 P2-DEFERRED(见报告)。
    """
    if p.leader != LEADER_SHAKESPEARE:
        return 0
    if category is CardCategory.THEATER:
        pair = CardCategory.LIBRARY
    elif category is CardCategory.LIBRARY:
        pair = CardCategory.THEATER
    else:
        return 0
    has_pair = any(
        db.get(card_id).category is pair for card_id in p.developed)
    return SHAKESPEARE_BUILD_DISCOUNT if has_pair else 0


def theater_science_discount(db: CardDB, p: PlayerState, card: CardDefinition) -> int:
    """研发科技的科技费折扣(j_s_bach: 剧院科技 -2, PDF 图标为科技).

    挂钩于 legal/apply 的 DevelopTech(含 develop_tech pending 子行动),
    与 scientific_cooperation 折扣叠加。
    """
    if p.leader == LEADER_BACH and card.category is CardCategory.THEATER:
        return BACH_THEATER_SCIENCE_DISCOUNT
    return 0


def bach_upgrade_available(p: PlayerState) -> bool:
    """j_s_bach 每回合一次特殊升级是否可用(本回合未用)."""
    return (p.leader == LEADER_BACH
            and not p.turn_discounts.get(BACH_UPGRADE_KEY, 0))


def bach_upgrade_target_ok(
    from_card: CardDefinition, to_card: CardDefinition,
) -> bool:
    """bach 特殊升级目标合法性: 任一城市建筑 -> 同级或高一级剧院.

    "级" = 时代序(_TECH_LEVEL 口径, A=1); 源不可已为剧院(剧院间升级走
    普通 Upgrade, 不占用每回合一次)。
    """
    if from_card.category not in URBAN_CATEGORIES:
        return False
    if from_card.category is CardCategory.THEATER:
        return False
    if to_card.category is not CardCategory.THEATER:
        return False
    diff = _TECH_LEVEL[to_card.age] - _TECH_LEVEL[from_card.age]
    return diff in (0, 1)


def is_bach_upgrade(from_card: CardDefinition, to_card: CardDefinition) -> bool:
    """Upgrade 是否为 bach 特殊升级(跨类别到剧院; apply 记次用).

    普通升级限同类别, 故"目标剧院且源非剧院"的 Upgrade 必为 bach 升级
    (合法性由 legal 枚举保证)。
    """
    return (to_card.category is CardCategory.THEATER
            and from_card.category is not CardCategory.THEATER)


def _construction_card_id(db: CardDB, p: PlayerState) -> str | None:
    """玩家已研发的 CONSTRUCTION 特殊科技卡 id; 无则 None.

    同类型特殊科技并存时低级者立即移除(apply._replace_lower_special),
    故至多一张; 防御性取每白点阶段数最高者。
    """
    found = [
        card_id for card_id in p.developed
        if card_id in CONSTRUCTION_STAGES_PER_ACTION
    ]
    if not found:
        return None
    return max(found, key=lambda cid: CONSTRUCTION_STAGES_PER_ACTION[cid])


def wonder_stages_per_action(db: CardDB, p: PlayerState) -> int:
    """一次 BuildWonderStage 动作(1 白点)可建的最多奇迹阶段数(1/2/3/4)."""
    card_id = _construction_card_id(db, p)
    if card_id is None:
        return 1
    return CONSTRUCTION_STAGES_PER_ACTION[card_id]


def construction_urban_discount(
    db: CardDB, p: PlayerState, card: CardDefinition,
) -> int:
    """城市建筑建造/升级的资源费折扣 = min(卡级, max)(masonry 系列).

    "级" = 时代序(A 计 0 级, 见 _CONSTRUCTION_LEVEL); 升级按双边折后差价
    (官方规则书: "apply the card's modifiers to both costs")。
    """
    if card.category not in URBAN_CATEGORIES:
        return 0
    card_id = _construction_card_id(db, p)
    if card_id is None:
        return 0
    return min(
        _CONSTRUCTION_LEVEL[card.age], CONSTRUCTION_URBAN_MAX[card_id])


# --- 时代 III 领袖/特殊科技/奇迹钩子(Task 12) ------------------------------------


def _einstein_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """albert_einstein: 最佳实验室/图书馆每级 +1 科技(同 leonardo 口径).

    SIMPLIFICATION: 按已研发卡计(不要求卡上有工人)。
    """
    best = 0
    for card_id in p.developed:
        card = db.get(card_id)
        if card.category in (CardCategory.LAB, CardCategory.LIBRARY):
            best = max(best, _TECH_LEVEL[card.age])
    return {"science": best} if best else {}


def _gandhi_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """mahatma_gandhi: +2 文化(侵略/战争限制与双倍军事行动 P2-DEFERRED)."""
    return {"culture": 2}


def _chaplin_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """charlie_chaplin: +2 笑脸; 最佳剧院产出双倍文化.

    双倍实现为: 文化 += 最佳剧院当前文化产出(工人数 × 卡面文化),
    即该剧院再计一份。SIMPLIFICATION: 不计其他来源对该剧院的加成。
    """
    best = 0
    for card_id, workers in p.buildings.get(CardCategory.THEATER.value, {}).items():
        if workers > 0:
            produces = db.get(card_id).urban_produces
            best = max(best, produces.get("culture", 0) * workers)
    result: dict[str, int] = {"happiness": 2}
    if best:
        result["culture"] = best
    return result


def _sid_meier_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """sid_meier: 实验室每级 +1 文化, 每个实验室 -1 科技.

    SIMPLIFICATION: 按已研发卡计(不要求卡上有工人), 同 leonardo 口径。
    """
    culture = 0
    labs = 0
    for card_id in p.developed:
        card = db.get(card_id)
        if card.category is CardCategory.LAB:
            culture += _TECH_LEVEL[card.age]
            labs += 1
    if not labs:
        return {}
    return {"culture": culture, "science": -labs}


def _military_theory_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """military_theory(特殊科技): +5 军力 +3 军事行动."""
    return {"strength": 5, "military_actions": 3}


def _civil_service_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """civil_service(特殊科技): +2 内政行动(研发 +3 蓝点见 on_develop)."""
    return {"civil_actions": 2}


def _satellites_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """satellites(特殊科技): +4 殖民修正(殖民 P2-DEFERRED)+3 军力."""
    return {"colonization": 4, "strength": 3}


def _internet_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """internet(奇迹): 城市建筑每产出 1 科技或文化, +1 文化(按工人数)."""
    culture = 0
    for category in URBAN_CATEGORIES:
        for card_id, workers in p.buildings.get(category.value, {}).items():
            if workers > 0:
                produces = db.get(card_id).urban_produces
                per_worker = (
                    produces.get("science", 0) + produces.get("culture", 0))
                culture += per_worker * workers
    return {"culture": culture} if culture else {}


def _first_space_flight_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """first_space_flight(奇迹): 每项已研发科技每级 +1 文化.

    官方规则: 政体算科技, 当前政体按其时代等级计入(级 = 时代序,
    同 _TECH_LEVEL 口径)。
    """
    culture = sum(_TECH_LEVEL[db.get(card_id).age] for card_id in p.developed)
    culture += _TECH_LEVEL[db.get(p.government).age]
    return {"culture": culture} if culture else {}


def _fast_food_chains_bonus(db: CardDB, p: PlayerState) -> dict[str, int]:
    """fast_food_chains(奇迹): 农场/矿场每卡 +2 文化, 城市建筑/兵种每卡 +1.

    按场上有工人的卡计(每卡 1 次, 与工人数无关)。
    """
    farms_mines = sum(
        1
        for category in (CardCategory.FARM, CardCategory.MINE)
        for workers in p.buildings.get(category.value, {}).values()
        if workers > 0
    )
    others = sum(
        1
        for category in URBAN_CATEGORIES | UNIT_CATEGORIES
        for workers in p.buildings.get(category.value, {}).values()
        if workers > 0
    )
    culture = 2 * farms_mines + others
    return {"culture": culture} if culture else {}


STATIC_BONUS_HANDLERS.update({
    LEADER_EINSTEIN: _einstein_bonus,
    LEADER_GANDHI: _gandhi_bonus,
    LEADER_CHAPLIN: _chaplin_bonus,
    LEADER_SID_MEIER: _sid_meier_bonus,
    "military_theory": _military_theory_bonus,
    "civil_service": _civil_service_bonus,
    "satellites": _satellites_bonus,
    "internet": _internet_bonus,
    "first_space_flight": _first_space_flight_bonus,
    "fast_food_chains": _fast_food_chains_bonus,
})


def gates_lab_bonus_culture(db: CardDB, p: PlayerState) -> int:
    """bill_gates 被替换离场奖励: +文化 = Σ 每个实验室工人 × 该卡时代等级.

    口径为实验室的每回合额外产出(每个实验室工人在其卡上产 1 蓝点, 蓝点
    价值 = 时代等级, 规则书附录), 级 = 时代序, 同 _TECH_LEVEL 口径; 与
    events._building_levels(T12 终局奖励)同口径(每工人 = 一张同等级卡)。
    挂钩于 apply._play_leader 的替换分支(即时结算);
    终局奖励见 events._bill_gates_endgame(P2-T12 已实现)。
    """
    return sum(
        workers * _TECH_LEVEL[db.get(card_id).age]
        for card_id, workers in p.buildings.get(CardCategory.LAB.value, {}).items()
        if workers > 0
    )


# --- 行动卡 handler 工厂 ---------------------------------------------------------
#
# 同名行动卡各时代实例 X 加成不同(PDF 第 2 页 Bonus 列): handler 名 = 卡 id
# 全名(Age A 无后缀, 时代 I 带 _i 后缀), 由工厂按 X 参数生成, 解决 T9
# handler 名全局唯一问题。签名统一为 (state, player_index, db, option)。


def _stockpile_handler(
    state: GameState, player_index: int, db: CardDB, option: str = "",
) -> GameState:
    """stockpile(Age A): 获得 1 食物 + 1 资源(经 gain_tokens 入最低级卡)."""
    p = state.players[player_index]
    p = economy.gain_tokens(db, p, "food", 1)
    p = economy.gain_tokens(db, p, "resource", 1)
    return replace_player(state, player_index, p)


def _make_frugality_handler(
    food_gain: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """frugality: 增人口(全费, 含 moses 折扣), 然后 +food_gain 食物."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        p = state.players[player_index]
        p = increase_population(db, p)
        p = economy.gain_tokens(db, p, "food", food_gain)
        return replace_player(state, player_index, p)

    return handler


def _make_engineering_genius_handler(
    discount: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """engineering_genius: 下一奇迹阶段 0 行动点且折扣 discount."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        return push_pending(
            state, PendingEffect(KIND_WONDER_STAGE, discount))

    return handler


def _make_patriotism_handler(
    unit_discount: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """patriotism: 本回合 +1 军事行动, 兵种建造折扣 unit_discount(可叠加)."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        p = state.players[player_index]
        discounts = dict(p.turn_discounts)
        key = UNIT_BUILD_DISCOUNT_KEY
        discounts[key] = discounts.get(key, 0) + unit_discount
        p = replace(p,
                    military_actions=p.military_actions + 1,
                    turn_discounts=discounts)
        return replace_player(state, player_index, p)

    return handler


def _make_build_subaction_handler(
    kind: str, discount: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """rich_land/urban_growth: 下一匹配 Build/Upgrade 0 行动点且折扣 discount."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        return push_pending(state, PendingEffect(kind, discount))

    return handler


def _make_cultural_heritage_handler(
    science: int, culture: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """cultural_heritage: +science 科技 +culture 文化(各时代数值不同)."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        p = state.players[player_index]
        p = replace(p,
                    science=p.science + science,
                    culture=p.culture + culture)
        return replace_player(state, player_index, p)

    return handler


def _make_breakthrough_handler(
    science_gain: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """breakthrough: 压入 develop_tech pending(0 行动点全价研发后 +X 科技)."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        return push_pending(
            state, PendingEffect(
                KIND_DEVELOP_TECH, 0, science_gain=science_gain))

    return handler


def _make_reserves_handler(
    amount: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """reserves: +amount 资源或 +amount 食物, option 二选一."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        p = state.players[player_index]
        p = economy.gain_tokens(db, p, option, amount)
        return replace_player(state, player_index, p)

    return handler


def _make_revolutionary_idea_handler(
    science: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """revolutionary_idea: +science 科技(时代 II 新增即时收益类)."""

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        p = state.players[player_index]
        p = replace(p, science=p.science + science)
        return replace_player(state, player_index, p)

    return handler


def _make_upgrade_subaction_handler(
    discount: int,
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """efficient_upgrade: 下一农场/矿场/城市建筑 Upgrade 0 行动点且折扣.

    与 rich_land/urban_growth 的差别: 仅 Upgrade(不可 Build),
    兵种升级不在其列(kind 查 PENDING_UPGRADE_CATEGORIES)。
    """

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        return push_pending(
            state, PendingEffect(KIND_UPGRADE_FARM_MINE_URBAN, discount))

    return handler


_WAVE_DISCOUNT_BY_PLAYERS = {2: 6, 3: 3, 4: 2}
"""wave_of_nationalism 每个更强文明提供的兵种建造折扣(按玩家人数)."""

_BUILD_UP_DISCOUNT_BY_PLAYERS = {2: 8, 3: 5, 4: 3}
"""military_build_up 每个更强文明提供的兵种建造折扣(按玩家人数)."""

_ENDOWMENT_GAIN_BY_PLAYERS = {2: 6, 3: 3, 4: 2}
"""endowment_for_arts 每个文化分更高文明提供的文化得分(按玩家人数)."""


def _make_stronger_civs_discount_handler(
    discount_by_players: dict[int, int],
) -> Callable[[GameState, int, CardDB, str], GameState]:
    """每个军力更高文明 +N 本回合兵种建造折扣(wave_of_nationalism 等).

    强度比较需全玩家信息, 故为 handler 内即时计算(行动卡 handler 拿到
    完整 state); civ 依赖 effects, 此处延迟导入避免循环。
    """

    def handler(
        state: GameState, player_index: int, db: CardDB, option: str = "",
    ) -> GameState:
        from tta.engine.civ import civ_values
        p = state.players[player_index]
        mine = civ_values(db, p, state.players, player_index).strength
        stronger = sum(
            1
            for i, other in enumerate(state.players)
            if i != player_index and not other.resigned
            and civ_values(db, other, state.players, i).strength > mine
        )
        if not stronger:
            return state
        per = discount_by_players[len(state.players)]
        discounts = dict(p.turn_discounts)
        key = UNIT_BUILD_DISCOUNT_KEY
        discounts[key] = discounts.get(key, 0) + stronger * per
        p = replace(p, turn_discounts=discounts)
        return replace_player(state, player_index, p)

    return handler


def _endowment_for_arts_iii_handler(
    state: GameState, player_index: int, db: CardDB, option: str = "",
) -> GameState:
    """endowment_for_arts_iii: 每个文化分更高文明 +6/3/2 文化(2/3/4 人局).

    比较的是文化分存量(p.culture), 非文化增速。
    """
    p = state.players[player_index]
    higher = sum(
        1
        for i, other in enumerate(state.players)
        if i != player_index and other.culture > p.culture
    )
    if not higher:
        return state
    per = _ENDOWMENT_GAIN_BY_PLAYERS[len(state.players)]
    p = replace(p, culture=p.culture + higher * per)
    return replace_player(state, player_index, p)


# Age A 实例(X 取 PDF Bonus 列 Age A 值)
ACTION_HANDLERS.update({
    "stockpile": _stockpile_handler,
    "frugality": _make_frugality_handler(1),
    "engineering_genius": _make_engineering_genius_handler(2),
    "patriotism": _make_patriotism_handler(1),
    "rich_land": _make_build_subaction_handler(KIND_BUILD_FARM_MINE, 1),
    "urban_growth": _make_build_subaction_handler(KIND_BUILD_URBAN, 1),
    "cultural_heritage": _make_cultural_heritage_handler(1, 4),
})

# 时代 I 实例(X 取 PDF Bonus 列 Age I 值; engineering_genius X=3)
ACTION_HANDLERS.update({
    "breakthrough_i": _make_breakthrough_handler(2),
    "cultural_heritage_i": _make_cultural_heritage_handler(2, 2),
    "engineering_genius_i": _make_engineering_genius_handler(3),
    "frugality_i": _make_frugality_handler(2),
    "patriotism_i": _make_patriotism_handler(2),
    "reserves_i": _make_reserves_handler(2),
    "rich_land_i": _make_build_subaction_handler(KIND_BUILD_FARM_MINE, 2),
    "urban_growth_i": _make_build_subaction_handler(KIND_BUILD_URBAN, 2),
})

# 时代 II 实例(X 取 PDF Bonus 列 Age II 值; engineering_genius X=4,
# revolutionary_idea X=4; 时代 II 无 cultural_heritage / stockpile)
ACTION_HANDLERS.update({
    "breakthrough_ii": _make_breakthrough_handler(3),
    "efficient_upgrade_ii": _make_upgrade_subaction_handler(3),
    "engineering_genius_ii": _make_engineering_genius_handler(4),
    "frugality_ii": _make_frugality_handler(3),
    "patriotism_ii": _make_patriotism_handler(3),
    "reserves_ii": _make_reserves_handler(3),
    "revolutionary_idea_ii": _make_revolutionary_idea_handler(4),
    "rich_land_ii": _make_build_subaction_handler(KIND_BUILD_FARM_MINE, 3),
    "urban_growth_ii": _make_build_subaction_handler(KIND_BUILD_URBAN, 3),
    "wave_of_nationalism_ii": _make_stronger_civs_discount_handler(
        _WAVE_DISCOUNT_BY_PLAYERS),
})

# 时代 III 实例(X 取 PDF Bonus 列 Age III 值; engineering_genius X=5,
# revolutionary_idea X=6; 时代 III 新增 endowment_for_arts / military_build_up;
# 无 breakthrough / cultural_heritage / frugality / rich_land / stockpile /
# wave_of_nationalism)
ACTION_HANDLERS.update({
    "efficient_upgrade_iii": _make_upgrade_subaction_handler(4),
    "endowment_for_arts_iii": _endowment_for_arts_iii_handler,
    "engineering_genius_iii": _make_engineering_genius_handler(5),
    "military_build_up_iii": _make_stronger_civs_discount_handler(
        _BUILD_UP_DISCOUNT_BY_PLAYERS),
    "patriotism_iii": _make_patriotism_handler(4),
    "reserves_iii": _make_reserves_handler(4),
    "revolutionary_idea_iii": _make_revolutionary_idea_handler(6),
    "urban_growth_iii": _make_build_subaction_handler(KIND_BUILD_URBAN, 4),
})

ACTION_OPTIONS.update({
    "reserves_i": ("resource", "food"),
    "reserves_ii": ("resource", "food"),
    "reserves_iii": ("resource", "food"),
})

# 折扣/子行动类与 handler 成对注册(legal 打出预判用)
PENDING_SPECS.update({
    "engineering_genius": PendingEffect(KIND_WONDER_STAGE, 2),
    "rich_land": PendingEffect(KIND_BUILD_FARM_MINE, 1),
    "urban_growth": PendingEffect(KIND_BUILD_URBAN, 1),
    "breakthrough_i": PendingEffect(KIND_DEVELOP_TECH, 0, science_gain=2),
    "engineering_genius_i": PendingEffect(KIND_WONDER_STAGE, 3),
    "rich_land_i": PendingEffect(KIND_BUILD_FARM_MINE, 2),
    "urban_growth_i": PendingEffect(KIND_BUILD_URBAN, 2),
    "breakthrough_ii": PendingEffect(KIND_DEVELOP_TECH, 0, science_gain=3),
    "efficient_upgrade_ii": PendingEffect(KIND_UPGRADE_FARM_MINE_URBAN, 3),
    "engineering_genius_ii": PendingEffect(KIND_WONDER_STAGE, 4),
    "rich_land_ii": PendingEffect(KIND_BUILD_FARM_MINE, 3),
    "urban_growth_ii": PendingEffect(KIND_BUILD_URBAN, 3),
    "efficient_upgrade_iii": PendingEffect(KIND_UPGRADE_FARM_MINE_URBAN, 4),
    "engineering_genius_iii": PendingEffect(KIND_WONDER_STAGE, 5),
    "urban_growth_iii": PendingEffect(KIND_BUILD_URBAN, 4),
})

PLAY_CONDITIONS.update({
    "frugality": can_increase_population,
    "frugality_i": can_increase_population,
    "frugality_ii": can_increase_population,
})
