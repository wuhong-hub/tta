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
  实现"红点当白点"(SIMPLIFICATION 见函数 docstring);
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
  masonry 建造折扣与双阶段 P2-DEFERRED;
- 奇迹: great_wall 经 static_bonuses 的奇迹 handler 维度提供
  每步兵/炮兵 +1 军力; st_peters_basilica 他文明笑脸与 taj_mahal
  蓝点/换领袖折扣 P2-DEFERRED。

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

KIND_BUILD_FARM_MINE = "build_farm_mine"
KIND_BUILD_URBAN = "build_urban"
KIND_WONDER_STAGE = "wonder_stage"
KIND_DEVELOP_TECH = "develop_tech"

PENDING_BUILD_CATEGORIES: dict[str, frozenset[CardCategory]] = {
    KIND_BUILD_FARM_MINE: frozenset({CardCategory.FARM, CardCategory.MINE}),
    KIND_BUILD_URBAN: URBAN_CATEGORIES,
}
"""建造类 pending kind -> 允许的卡牌类别(Build/Upgrade 目标须在其中)."""


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
    card_ids.extend(p.wonders)

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
    """julius_caesar: +1 军力 +1 军事行动(双政治行动 P2-DEFERRED)."""
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
    """能否增人口: 黄点银行非空且食物足够支付人口费."""
    if p.yellow_bank <= 0:
        return False
    return economy.food_total(db, p) >= increase_population_cost(db, p)


def increase_population(db: CardDB, p: PlayerState) -> PlayerState:
    """增人口结算(共用): 支付食物费(含 moses 折扣), 黄点银行 -1, 空闲工人 +1.

    调用点: apply 的 IncreasePopulation 动作(另扣 1 白点)与 frugality
    行动卡 handler(不扣行动点)。本函数不含行动点扣减。
    """
    p = economy.pay(db, p, "food", increase_population_cost(db, p))
    return replace(p, yellow_bank=p.yellow_bank - 1,
                   worker_pool=p.worker_pool + 1)


def leader_take_discount(db: CardDB, p: PlayerState) -> int:
    """从卡牌列拿领袖牌的白点折扣(hammurabi: -1)."""
    return 1 if p.leader == LEADER_HAMMURABI else 0


def flexible_actions(db: CardDB, p: PlayerState) -> int:
    """可用于垫付白点费用的红点数(hammurabi: 全部红点; 否则 0).

    SIMPLIFICATION: hammurabi 官方能力为"每回合一次, 把 1 个军事行动当作
    内政行动使用"; P1 实现为"白点不足支付白点费用时, 可用红点 1:1 垫付",
    仅 legal/apply 的 TakeCard / DevelopTech / Build / Upgrade 四处挂钩,
    其余白点花费(PlayLeader / Destroy / BuildWonderStage 等)不垫付。
    """
    return p.military_actions if p.leader == LEADER_HAMMURABI else 0


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


def on_develop_tech_gains(db: CardDB, p: PlayerState) -> PlayerState:
    """DevelopTech 结算后的领袖即时收益(leonardo: +1 资源, 蓝点入最低级矿场).

    调用点为 apply 的 DevelopTech(含 breakthrough pending 子行动);
    变更政体(DevelopGovernment)不触发。
    """
    if p.leader == LEADER_LEONARDO:
        return economy.gain_tokens(db, p, "resource", 1)
    return p


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

ACTION_OPTIONS.update({
    "reserves_i": ("resource", "food"),
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
})

PLAY_CONDITIONS.update({
    "frugality": can_increase_population,
    "frugality_i": can_increase_population,
})
