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
"""

from collections.abc import Callable
from dataclasses import replace

from tta.engine.enums import URBAN_CATEGORIES, CardCategory
from tta.engine.model import CardDB
from tta.engine.state import GameState, PendingEffect, PlayerState

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
压入的 PendingEffect 须与此处一致(Task 9 注册时成对维护)。
"""

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
