"""枚举与卡牌数据模型测试(P1 官方规则核心)."""

import pytest

from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    WORKER_CATEGORIES,
    Age,
    CardCategory,
    DeckType,
    SpecialType,
)
from tta.engine.model import CardDB, CardDefinition, GovernmentStats


def test_age_next() -> None:
    assert Age.A.next() is Age.I
    assert Age.I.next() is Age.II
    assert Age.II.next() is Age.III
    assert Age.III.next() is None


def test_card_category_set() -> None:
    """P1 内政 16 类 + P2 军事 7 类(事件/侵略/战争/条约/阵型/奖励/地区)."""
    expected = {
        "FARM", "MINE", "LAB", "TEMPLE", "LIBRARY", "THEATER", "ARENA",
        "INFANTRY", "CAVALRY", "ARTILLERY", "AIR",
        "GOVERNMENT", "LEADER", "WONDER", "ACTION", "SPECIAL",
        "EVENT", "AGGRESSION", "WAR", "PACT", "TACTICS", "BONUS", "TERRITORY",
    }
    assert {c.name for c in CardCategory} == expected
    assert len(CardCategory) == 23


def test_category_sets() -> None:
    assert URBAN_CATEGORIES == frozenset({
        CardCategory.LAB, CardCategory.TEMPLE, CardCategory.LIBRARY,
        CardCategory.THEATER, CardCategory.ARENA,
    })
    assert UNIT_CATEGORIES == frozenset({
        CardCategory.INFANTRY, CardCategory.CAVALRY,
        CardCategory.ARTILLERY, CardCategory.AIR,
    })
    assert WORKER_CATEGORIES == (
        URBAN_CATEGORIES | UNIT_CATEGORIES
        | frozenset({CardCategory.FARM, CardCategory.MINE})
    )


def test_special_type() -> None:
    assert {s.name for s in SpecialType} == {
        "LAW", "WARFARE", "EXPLORATION", "CONSTRUCTION",
    }


def test_government_stats_default_bonus() -> None:
    stats = GovernmentStats(civil_actions=4, military_actions=2, urban_limit=2)
    assert stats.civil_actions == 4
    assert stats.military_actions == 2
    assert stats.urban_limit == 2
    assert stats.bonus == {}


def test_card_definition_defaults() -> None:
    card = CardDefinition(
        id="agriculture",
        name="农业",
        name_en="Agriculture",
        age=Age.A,
        deck=DeckType.CIVIL,
        category=CardCategory.FARM,
    )
    assert card.text == ""
    assert card.cost_science == 0
    assert card.cost_science_revolution == 0
    assert card.build_cost == 0
    assert card.token_value == 0
    assert card.urban_produces == {}
    assert card.strength == 0
    assert card.government is None
    assert card.special_type is None
    assert card.wonder_stages == ()
    assert card.wonder_bonus == {}
    assert card.handler == ""
    assert card.quantities == (0, 0, 0)


def _sample_db() -> CardDB:
    cards = {
        "agriculture": CardDefinition(
            id="agriculture", name="农业", name_en="Agriculture",
            age=Age.A, deck=DeckType.CIVIL, category=CardCategory.FARM,
            quantities=(2, 3, 4),
        ),
        "bronze": CardDefinition(
            id="bronze", name="青铜", name_en="Bronze",
            age=Age.A, deck=DeckType.CIVIL, category=CardCategory.MINE,
            quantities=(2, 2, 2),
        ),
        "iron": CardDefinition(
            id="iron", name="铁", name_en="Iron",
            age=Age.I, deck=DeckType.CIVIL, category=CardCategory.MINE,
            quantities=(2, 2, 2),
        ),
    }
    return CardDB(
        cards=cards,
        initial_tableau=("agriculture", "bronze"),
        initial_government="despotism",
    )


def test_deck_for_player_counts() -> None:
    db = _sample_db()
    assert db.deck_for(Age.A, 2) == (
        "agriculture", "agriculture", "bronze", "bronze",
    )
    assert db.deck_for(Age.A, 3) == (
        "agriculture", "agriculture", "agriculture", "bronze", "bronze",
    )
    assert db.deck_for(Age.A, 4) == (
        "agriculture", "agriculture", "agriculture", "agriculture",
        "bronze", "bronze",
    )
    assert db.deck_for(Age.I, 2) == ("iron", "iron")
    assert db.deck_for(Age.II, 2) == ()


def test_deck_for_invalid_players() -> None:
    db = _sample_db()
    with pytest.raises(ValueError):
        db.deck_for(Age.A, 5)


def test_deck_for_filters_deck_type() -> None:
    """deck_for 默认只取 CIVIL 卡(P2 军事卡入库后防御)."""
    db = _sample_db()
    military = CardDefinition(
        id="warriors_m", name="武士", name_en="Warriors",
        age=Age.A, deck=DeckType.MILITARY, category=CardCategory.INFANTRY,
        quantities=(2, 2, 2),
    )
    db = CardDB(
        cards={**db.cards, military.id: military},
        initial_tableau=db.initial_tableau,
        initial_government=db.initial_government,
    )
    assert "warriors_m" not in db.deck_for(Age.A, 2)
    assert db.deck_for(Age.A, 2, DeckType.MILITARY) == (
        "warriors_m", "warriors_m",
    )


def test_card_db_get() -> None:
    db = _sample_db()
    assert db.get("bronze").name_en == "Bronze"
    assert db.initial_tableau == ("agriculture", "bronze")
    assert db.initial_government == "despotism"
