"""资源支付引擎测试(确定性找零算法, 见 tta/engine/economy.py 模块 docstring)."""

import pytest

from tta.engine.economy import (
    food_total,
    gain_tokens,
    pay,
    produce,
    resource_total,
    settle_loss,
)
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import PlayerState


def _card(card_id: str, category: CardCategory, token_value: int) -> CardDefinition:
    return CardDefinition(
        id=card_id,
        name=card_id,
        name_en=card_id,
        age=Age.A,
        deck=DeckType.CIVIL,
        category=category,
        token_value=token_value,
    )


def _db() -> CardDB:
    cards = {
        "agriculture": _card("agriculture", CardCategory.FARM, 1),
        "irrigation": _card("irrigation", CardCategory.FARM, 2),
        "bronze": _card("bronze", CardCategory.MINE, 1),
        "iron": _card("iron", CardCategory.MINE, 2),
    }
    return CardDB(cards=cards, initial_tableau=("agriculture", "bronze"),
                  initial_government="despotism")


def _player(**overrides: object) -> PlayerState:
    base: dict = {
        "name": "P0",
        "blue_bank": 16,
        "buildings": {
            "farm": {"agriculture": 2, "irrigation": 1},
            "mine": {"bronze": 1},
        },
        "card_tokens": {"agriculture": 2, "irrigation": 1},
        "developed": ("agriculture", "irrigation", "bronze", "iron"),
    }
    base.update(overrides)
    return PlayerState(**base)


def test_food_total() -> None:
    # agriculture 2 蓝点 ×1 + irrigation 1 蓝点 ×2 = 4
    assert food_total(_db(), _player()) == 4


def test_resource_total() -> None:
    p = _player(card_tokens={"bronze": 3, "iron": 1})
    # bronze 3×1 + iron 1×2 = 5
    assert resource_total(_db(), p) == 5


def test_total_ignores_other_category_tokens() -> None:
    p = _player(card_tokens={"agriculture": 2, "bronze": 3})
    assert food_total(_db(), p) == 2
    assert resource_total(_db(), p) == 3


def test_pay_food_exact_from_lowest_first() -> None:
    p = _player()
    q = pay(_db(), p, "food", 1)
    # 先取 token_value 最小的 agriculture: 2 -> 1, irrigation 不动
    assert q.card_tokens == {"agriculture": 1, "irrigation": 1}
    assert q.blue_bank == 16
    # 入参不被改动
    assert p.card_tokens == {"agriculture": 2, "irrigation": 1}


def test_pay_food_three_exact_no_change() -> None:
    p = _player()
    q = pay(_db(), p, "food", 3)
    # agriculture×2 (付2) + irrigation×1 (付2) 累计 4 >= 3? 否: 取到 2 后再取
    # irrigation 价值 2 会超付; 算法取到累计 >= 3: 2 + 2 = 4, 超付 1, 找零 1
    # 找零向最低等级农场 agriculture 放 1 蓝点
    assert q.card_tokens == {"agriculture": 1}
    assert q.blue_bank == 15


def test_pay_food_four_exact_all_spent() -> None:
    p = _player()
    q = pay(_db(), p, "food", 4)
    # 2 + 2 = 4 恰好, 无找零; 空卡槽从 card_tokens 移除
    assert q.card_tokens == {}
    assert q.blue_bank == 16


def test_pay_overpay_change_to_lowest_card() -> None:
    # 仅 irrigation 1 蓝点(值2), 付 1, 供给 3
    p = _player(card_tokens={"irrigation": 1}, blue_bank=3)
    q = pay(_db(), p, "food", 1)
    # irrigation 取空; 超付 1 -> 向最低等级农场 agriculture(值1) 放 1 蓝点
    assert q.card_tokens == {"agriculture": 1}
    assert q.blue_bank == 2


def test_pay_overpay_change_lost_when_supply_empty() -> None:
    p = _player(card_tokens={"irrigation": 1}, blue_bank=0)
    q = pay(_db(), p, "food", 1)
    # 找零 1 但供给空 -> 损失, 无补偿
    assert q.card_tokens == {}
    assert q.blue_bank == 0


def test_pay_change_partial_loss_when_token_value_too_big() -> None:
    # 仅 iron 1 蓝点(值2), 付 resource 1; 找零 1 < 矿场最低等级卡 bronze 值1?
    # bronze 已研发, 值 1 <= 1, 可找零
    p = _player(card_tokens={"iron": 1}, blue_bank=1)
    q = pay(_db(), p, "resource", 1)
    assert q.card_tokens == {"bronze": 1}
    assert q.blue_bank == 0


def test_pay_insufficient_raises() -> None:
    p = _player()
    with pytest.raises(ValueError, match="不足"):
        pay(_db(), p, "food", 5)


def test_pay_zero_returns_equal_state() -> None:
    p = _player()
    assert pay(_db(), p, "food", 0) == p


def test_pay_invalid_kind_raises() -> None:
    p = _player()
    with pytest.raises(ValueError, match="kind"):
        pay(_db(), p, "gold", 1)


def test_produce_high_value_first_when_supply_short() -> None:
    p = _player(card_tokens={}, blue_bank=2)
    q = produce(_db(), p, "food")
    # agriculture 2 工人 / irrigation 1 工人, 各得 1; 供给 2:
    # 高等级 irrigation 先得 1, agriculture 再得 1(而非 2), 供给归零
    assert q.card_tokens == {"agriculture": 1, "irrigation": 1}
    assert q.blue_bank == 0


def test_produce_only_one_blue_available() -> None:
    p = _player(card_tokens={}, blue_bank=1)
    q = produce(_db(), p, "food")
    assert q.card_tokens == {"irrigation": 1}
    assert q.blue_bank == 0


def test_produce_resource() -> None:
    p = _player(card_tokens={}, blue_bank=5,
                buildings={"mine": {"bronze": 1, "iron": 1}})
    q = produce(_db(), p, "resource")
    assert q.card_tokens == {"bronze": 1, "iron": 1}
    assert q.blue_bank == 3


def test_produce_no_workers_noop() -> None:
    p = _player(card_tokens={}, blue_bank=5,
                buildings={"farm": {"agriculture": 0}})
    assert produce(_db(), p, "food") == p


def test_gain_tokens_to_lowest_mine() -> None:
    p = _player(card_tokens={}, blue_bank=16)
    q = gain_tokens(_db(), p, "resource", 2)
    # 最低等级矿场 bronze 得 2 蓝点
    assert q.card_tokens == {"bronze": 2}
    assert q.blue_bank == 14


def test_gain_tokens_supply_short_best_effort() -> None:
    p = _player(card_tokens={}, blue_bank=1)
    q = gain_tokens(_db(), p, "resource", 3)
    assert q.card_tokens == {"bronze": 1}
    assert q.blue_bank == 0


def test_gain_tokens_no_card_noop() -> None:
    p = _player(card_tokens={}, blue_bank=5, developed=(), buildings={})
    assert gain_tokens(_db(), p, "resource", 2) == p


def test_gain_tokens_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        gain_tokens(_db(), _player(), "gold", 1)


def test_settle_loss_full_payment_equals_pay() -> None:
    # 持有足够时与 pay 一致, 实际支付 = 应付
    p = _player()
    q, paid = settle_loss(_db(), p, "food", 3)
    assert paid == 3
    assert q == pay(_db(), p, "food", 3)


def test_settle_loss_insufficient_pays_all_without_raise() -> None:
    # 持有 4 点食物, 损失 10: 全部交出, 实际支付 4, 不产生负值不抛错
    p = _player()
    q, paid = settle_loss(_db(), p, "food", 10)
    assert paid == 4
    assert q.card_tokens == {}
    assert q.blue_bank == 16


def test_settle_loss_no_tokens_returns_zero_paid() -> None:
    p = _player(card_tokens={})
    q, paid = settle_loss(_db(), p, "resource", 4)
    assert paid == 0
    assert q == p


def test_settle_loss_zero_amount_noop() -> None:
    p = _player()
    q, paid = settle_loss(_db(), p, "resource", 0)
    assert paid == 0
    assert q == p


def test_settle_loss_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        settle_loss(_db(), _player(), "gold", 1)
