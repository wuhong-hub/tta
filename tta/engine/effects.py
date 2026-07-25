"""领袖/特殊科技静态加成与行动卡结算的处理器注册表.

civ.py 在合成文明数值的最后一步调用 static_bonuses, 叠加领袖与已研发
特殊科技(SPECIAL 类别)卡提供的静态加成; 各卡的 handler 字段为注册表
STATIC_BONUS_HANDLERS 中的处理器名, 空 handler 或未注册者跳过。
apply.py 的 PlayActionCard 分支按卡的 handler 字段查 ACTION_HANDLERS
结算行动卡效果。

行动卡三类行为(Task 7 实现机制, Task 9 注册 Age A 首批 handler):
1. 即时收益类(如 stockpile): handler 直接改 state;
2. 折扣子行动类(如 rich_land): handler 经 push_pending 压入
   PendingEffect, 下一动作必须是对应 Build/Upgrade/BuildWonderStage
   (0 行动点、费用享折扣), 执行后 pop;
3. 回合修饰类(如 patriotism): 立即调整行动点并写 turn_discounts。

Age A 领袖钩子(Task 9):
- alexander_the_great / julius_caesar / homer: STATIC_BONUS_HANDLERS
  静态加成(经 civ_values 生效);
- homer: turn_start_discounts 在每回合行动点恢复时注入 unit_build 折扣;
- moses: population_food_discount 使增人口食物费 -1(挂钩于
  increase_population, 当前唯一调用点为 frugality handler);
- hammurabi: leader_take_discount 使拿领袖牌 -1 白点; flexible_actions
  实现"红点当白点"(SIMPLIFICATION 见函数 docstring);
- aristotle: on_take_card_gains 在 apply TakeCard 结算时 +1 科技。

engine 包不得 import tta.cards, 故领袖卡 id 以字符串常量定义于此。
"""

from collections.abc import Callable
from dataclasses import replace

from tta.engine import economy
from tta.engine.enums import UNIT_CATEGORIES, URBAN_CATEGORIES, WORKER_CATEGORIES, CardCategory
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import GameState, PendingEffect, PlayerState, replace_player
from tta.engine.tracks import population_cost

STATIC_BONUS_HANDLERS: dict[str, Callable[[CardDB, PlayerState], dict[str, int]]] = {}
"""静态加成处理器注册表: handler 名 -> (db, player) -> 加成 dict."""

ACTION_HANDLERS: dict[str, Callable[[GameState, int, CardDB], GameState]] = {}
"""行动卡结算处理器注册表: handler 名 -> (state, 玩家 idx, db) -> 新 state.

apply 在调用前已完成: 扣 1 白点、手牌移除该卡、卡入弃牌堆; handler 只负责
效果结算与 pending 压栈。Task 9 与牌库一起注册第一批(Age A 10 种)。
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

KIND_BUILD_FARM_MINE = "build_farm_mine"
KIND_BUILD_URBAN = "build_urban"
KIND_WONDER_STAGE = "wonder_stage"

PENDING_BUILD_CATEGORIES: dict[str, frozenset[CardCategory]] = {
    KIND_BUILD_FARM_MINE: frozenset({CardCategory.FARM, CardCategory.MINE}),
    KIND_BUILD_URBAN: URBAN_CATEGORIES,
}
"""建造类 pending kind -> 允许的卡牌类别(Build/Upgrade 目标须在其中)."""


def push_pending(state: GameState, pending: PendingEffect) -> GameState:
    """将子行动压入 pending 栈(供折扣子行动类 handler 使用)."""
    return replace(state, pending=state.pending + (pending,))


def static_bonuses(db: CardDB, p: PlayerState) -> dict[str, int]:
    """累加领袖与已研发特殊科技卡的静态文明加成.

    遍历 p.leader 与 p.developed 中 SPECIAL 类别卡, 按 handler 字段查
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
    """增人口: 支付食物费(含 moses 折扣), 黄点银行 -1, 空闲工人 +1.

    引擎尚无独立"增人口"动作(P1 动作集未含), 当前唯一调用点为
    frugality 行动卡 handler; 未来增人口动作应复用本函数。
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


# --- Age A 行动卡 handler(X 加成取 Card Reference Bonus 列 Age A 值) -----------
#
# 注意: 以下 handler 硬编码 Age A 的 X 值; 时代 I/II 同名行动卡 X 不同
# (Task 10-12 引入时须按时代区分 handler 或从打出卡读取加成)。

_STOCKPILE_GAIN = 1
_FRUGALITY_FOOD_GAIN = 1
_ENGINEERING_GENIUS_DISCOUNT = 2
_PATRIOTISM_MILITARY_ACTIONS = 1
_PATRIOTISM_UNIT_DISCOUNT = 1
_BUILD_SUBACTION_DISCOUNT = 1
_CULTURAL_HERITAGE_SCIENCE = 1
_CULTURAL_HERITAGE_CULTURE = 4


def _stockpile_handler(state: GameState, player_index: int, db: CardDB) -> GameState:
    """stockpile: 获得 1 食物 + 1 资源(经 gain_tokens 入最低级卡)."""
    p = state.players[player_index]
    p = economy.gain_tokens(db, p, "food", _STOCKPILE_GAIN)
    p = economy.gain_tokens(db, p, "resource", _STOCKPILE_GAIN)
    return replace_player(state, player_index, p)


def _frugality_handler(state: GameState, player_index: int, db: CardDB) -> GameState:
    """frugality: 增人口(全费, 含 moses 折扣), 然后 +1 食物."""
    p = state.players[player_index]
    p = increase_population(db, p)
    p = economy.gain_tokens(db, p, "food", _FRUGALITY_FOOD_GAIN)
    return replace_player(state, player_index, p)


def _engineering_genius_handler(
    state: GameState, player_index: int, db: CardDB,
) -> GameState:
    """engineering_genius: 下一奇迹阶段 0 行动点且折扣 2."""
    return push_pending(
        state, PendingEffect(KIND_WONDER_STAGE, _ENGINEERING_GENIUS_DISCOUNT))


def _patriotism_handler(
    state: GameState, player_index: int, db: CardDB,
) -> GameState:
    """patriotism: 本回合 +1 军事行动, 兵种建造折扣 1(可与 homer 叠加)."""
    p = state.players[player_index]
    discounts = dict(p.turn_discounts)
    key = UNIT_BUILD_DISCOUNT_KEY
    discounts[key] = discounts.get(key, 0) + _PATRIOTISM_UNIT_DISCOUNT
    p = replace(p,
                military_actions=p.military_actions + _PATRIOTISM_MILITARY_ACTIONS,
                turn_discounts=discounts)
    return replace_player(state, player_index, p)


def _rich_land_handler(state: GameState, player_index: int, db: CardDB) -> GameState:
    """rich_land: 下一农场/矿场 Build/Upgrade 0 行动点且折扣 1."""
    return push_pending(
        state, PendingEffect(KIND_BUILD_FARM_MINE, _BUILD_SUBACTION_DISCOUNT))


def _urban_growth_handler(
    state: GameState, player_index: int, db: CardDB,
) -> GameState:
    """urban_growth: 下一城市建筑 Build/Upgrade 0 行动点且折扣 1."""
    return push_pending(
        state, PendingEffect(KIND_BUILD_URBAN, _BUILD_SUBACTION_DISCOUNT))


def _cultural_heritage_handler(
    state: GameState, player_index: int, db: CardDB,
) -> GameState:
    """cultural_heritage: +1 科技 +4 文化."""
    p = state.players[player_index]
    p = replace(p,
                science=p.science + _CULTURAL_HERITAGE_SCIENCE,
                culture=p.culture + _CULTURAL_HERITAGE_CULTURE)
    return replace_player(state, player_index, p)


ACTION_HANDLERS.update({
    "stockpile": _stockpile_handler,
    "frugality": _frugality_handler,
    "engineering_genius": _engineering_genius_handler,
    "patriotism": _patriotism_handler,
    "rich_land": _rich_land_handler,
    "urban_growth": _urban_growth_handler,
    "cultural_heritage": _cultural_heritage_handler,
})

# 折扣子行动类与 handler 成对注册(legal 打出预判用)
PENDING_SPECS.update({
    "engineering_genius": PendingEffect(
        KIND_WONDER_STAGE, _ENGINEERING_GENIUS_DISCOUNT),
    "rich_land": PendingEffect(KIND_BUILD_FARM_MINE, _BUILD_SUBACTION_DISCOUNT),
    "urban_growth": PendingEffect(KIND_BUILD_URBAN, _BUILD_SUBACTION_DISCOUNT),
})

PLAY_CONDITIONS.update({
    "frugality": can_increase_population,
})
