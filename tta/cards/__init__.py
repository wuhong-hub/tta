"""官方牌库: build_card_db 合并各时代卡牌定义(P1 逐任务扩充).

当前包含: 初始科技(initial) + 时代 A(age_a) + 时代 I(age_i) +
时代 II(age_ii); 时代 III 由 Task 12 扩充。engine 包不依赖本包, 卡牌仅以
handler 名字符串引用 effects.py 注册的处理器。
"""

from tta.cards.age_a import AGE_A_CARDS
from tta.cards.age_i import AGE_I_CARDS
from tta.cards.age_ii import AGE_II_CARDS
from tta.cards.initial import INITIAL_CARDS, INITIAL_GOVERNMENT, INITIAL_TABLEAU
from tta.engine.model import CardDB

__all__ = ["build_card_db"]


def build_card_db() -> CardDB:
    """构建当前已实现的官方牌库(初始科技 + 时代 A + 时代 I + 时代 II)."""
    cards = {
        card.id: card
        for card in (*INITIAL_CARDS, *AGE_A_CARDS, *AGE_I_CARDS, *AGE_II_CARDS)
    }
    return CardDB(
        cards=cards,
        initial_tableau=INITIAL_TABLEAU,
        initial_government=INITIAL_GOVERNMENT,
    )
