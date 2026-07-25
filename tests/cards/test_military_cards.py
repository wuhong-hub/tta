"""军事牌库转录验证测试(P2-T2).

数据来源: Card Reference v1.09 第 3 页(奖励/侵略/战争/条约/阵型)、
第 4 页(事件 A 10 + I 15 + II 15 + III 15, 地区 I 6 + II 6)。
事件/地区无张数列, 每张 1 份; 条约仅 3-4 人局使用(2p 全移除);
其余军事牌张数不随人数变化。

军事牌堆各时代总数(Σ quantities, 2p/3p/4p):
- Age A:   10/10/10  (事件 10)
- Age I:   43/45/45  (事件 15 + 地区 6 + 阵型 10 + 侵略 6 + 奖励 6 + 条约 2)
- Age II:  46/50/50  (事件 15 + 地区 6 + 阵型 6 + 侵略 9 + 战争 4 + 奖励 6 + 条约 4)
- Age III: 41/45/45  (事件 15 + 阵型 6 + 侵略 8 + 战争 6 + 奖励 6 + 条约 4)
"""

from tta.cards import build_card_db
from tta.engine.enums import Age, CardCategory, DeckType

DB = build_card_db()
MILITARY_CARDS = [c for c in DB.cards.values() if c.deck is DeckType.MILITARY]

# PDF 第 3-4 页各类别卡牌定义数
CATEGORY_COUNTS = {
    CardCategory.BONUS: 3,
    CardCategory.AGGRESSION: 11,
    CardCategory.WAR: 3,
    CardCategory.PACT: 10,
    CardCategory.TACTICS: 15,
    CardCategory.EVENT: 55,
    CardCategory.TERRITORY: 12,
}

# 各时代军事牌堆总数 (2p, 3p, 4p)
DECK_SIZES = {
    Age.A: (10, 10, 10),
    Age.I: (43, 45, 45),
    Age.II: (46, 50, 50),
    Age.III: (41, 45, 45),
}

EVENT_AGES = {Age.A: 10, Age.I: 15, Age.II: 15, Age.III: 15}

# PDF 第 3 页 Tactics 表抽查: id -> (组成, 军力, 旧式军力)
TACTICS_SPOT = {
    "fighting_band": ({"INFANTRY": 2}, 1, 0),
    "phalanx": ({"INFANTRY": 2, "CAVALRY": 1}, 3, 0),
    "classic_army": ({"INFANTRY": 2, "CAVALRY": 2}, 8, 4),
    "fortifications": ({"ARTILLERY": 2}, 5, 3),
    "modern_army": ({"INFANTRY": 2, "CAVALRY": 1, "ARTILLERY": 1}, 13, 7),
}


def _by_category(category: CardCategory) -> list:
    return [c for c in MILITARY_CARDS if c.category is category]


def test_all_military_categories_present() -> None:
    assert set(CATEGORY_COUNTS) <= {c.category for c in MILITARY_CARDS}


def test_category_definition_counts() -> None:
    for category, count in CATEGORY_COUNTS.items():
        cards = _by_category(category)
        assert len(cards) == count, f"{category.name}: {len(cards)} != {count}"


def test_event_counts_by_age() -> None:
    for age, count in EVENT_AGES.items():
        cards = [c for c in _by_category(CardCategory.EVENT) if c.age is age]
        assert len(cards) == count, f"EVENT {age.name}: {len(cards)} != {count}"


def test_military_deck_sizes() -> None:
    for age, sizes in DECK_SIZES.items():
        for num_players, expected in zip((2, 3, 4), sizes, strict=True):
            deck = DB.deck_for(age, num_players, DeckType.MILITARY)
            assert len(deck) == expected, (
                f"{age.name} {num_players}p: {len(deck)} != {expected}"
            )


def test_deck_for_age_i_4p_matches_pdf() -> None:
    deck = DB.deck_for(Age.I, 4, DeckType.MILITARY)
    assert len(deck) == 45


def test_pacts_removed_in_2p() -> None:
    for card in _by_category(CardCategory.PACT):
        assert card.quantities[0] == 0, card.id
        assert card.quantities[1] == card.quantities[2] == 1, card.id


def test_bonus_fields() -> None:
    expected = {
        "defense_colonization_i": (Age.I, 2, 1),
        "defense_colonization_ii": (Age.II, 4, 2),
        "defense_colonization_iii": (Age.III, 6, 3),
    }
    for card in _by_category(CardCategory.BONUS):
        age, defense, colonize = expected[card.id]
        assert card.age is age
        assert card.defense_bonus == defense
        assert card.colonize_bonus == colonize
        assert card.quantities == (6, 6, 6)


def test_aggression_and_war_fields() -> None:
    for card in _by_category(CardCategory.AGGRESSION) + _by_category(CardCategory.WAR):
        assert card.military_cost > 0, card.id
        assert card.text, card.id
        assert card.handler == card.id, card.id


def test_event_fields() -> None:
    for card in _by_category(CardCategory.EVENT):
        assert card.text, card.id
        assert card.handler == card.id, card.id
        assert card.quantities == (1, 1, 1), card.id


def test_territory_fields() -> None:
    for card in _by_category(CardCategory.TERRITORY):
        assert card.territory_immediate, card.id
        assert card.territory_permanent, card.id
        assert card.text, card.id


def test_tactics_fields_nonempty() -> None:
    for card in _by_category(CardCategory.TACTICS):
        assert card.tactics_units, card.id
        assert card.tactics_strength > 0, card.id
        assert card.text, card.id


def test_tactics_spot_check() -> None:
    for card_id, (units, strength, outdated) in TACTICS_SPOT.items():
        card = DB.get(card_id)
        assert card.category is CardCategory.TACTICS
        assert card.tactics_units == units, f"{card_id}: {card.tactics_units}"
        assert card.tactics_strength == strength, card_id
        assert card.tactics_strength_outdated == outdated, card_id


def test_tactics_units_use_unit_categories() -> None:
    valid = {"INFANTRY", "CAVALRY", "ARTILLERY", "AIR"}
    for card in _by_category(CardCategory.TACTICS):
        assert set(card.tactics_units) <= valid, card.id
        assert all(n > 0 for n in card.tactics_units.values()), card.id


def test_civil_deck_unchanged() -> None:
    """军事牌入库后内政牌堆张数不变."""
    civil_sizes = {
        Age.A: (20, 20, 20),
        Age.I: (44, 50, 53),
        Age.II: (43, 50, 53),
        Age.III: (44, 50, 53),
    }
    for age, sizes in civil_sizes.items():
        for num_players, expected in zip((2, 3, 4), sizes, strict=True):
            deck = DB.deck_for(age, num_players)
            assert len(deck) == expected, (
                f"CIVIL {age.name} {num_players}p: {len(deck)} != {expected}"
            )
