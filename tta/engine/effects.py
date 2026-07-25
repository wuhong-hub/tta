"""领袖/特殊科技静态加成与行动卡结算的处理器注册表.

civ.py 在合成文明数值的最后一步调用 static_bonuses, 叠加领袖与已研发
特殊科技(SPECIAL 类别)卡提供的静态加成; 各卡的 handler 字段为注册表
STATIC_BONUS_HANDLERS 中的处理器名, 空 handler 或未注册者跳过。
apply.py 的 PlayActionCard 分支按卡的 handler 字段查 ACTION_HANDLERS
结算行动卡效果。

本模块仅提供空注册表骨架, 具体处理器自 Task 7(行动卡)与 Task 9(牌库
填充)起逐步注册。
"""

from collections.abc import Callable

from tta.engine.enums import CardCategory
from tta.engine.model import CardDB
from tta.engine.state import GameState, PlayerState

STATIC_BONUS_HANDLERS: dict[str, Callable[[CardDB, PlayerState], dict[str, int]]] = {}
"""静态加成处理器注册表: handler 名 -> (db, player) -> 加成 dict."""

ACTION_HANDLERS: dict[str, Callable[[CardDB, GameState], GameState]] = {}
"""行动卡结算处理器注册表: handler 名 -> (db, state) -> 新 state(Task 7 填充).

apply 在调用前已从手牌移除该卡并扣 1 白点; 效果结算、pending 压栈与
弃牌由处理器负责(见 Task 7)。
"""


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
