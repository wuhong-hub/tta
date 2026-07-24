"""最小牌库结构测试."""

from collections import Counter

from tta.cards.minimal import MINIMAL_DB
from tta.engine.enums import Age, CardCategory


def test_deck_sizes() -> None:
    assert set(MINIMAL_DB.civil_decks) == {Age.A, Age.I, Age.II, Age.III}
    for deck in MINIMAL_DB.civil_decks.values():
        assert len(deck) == 17


def test_all_deck_cards_defined() -> None:
    for deck in MINIMAL_DB.civil_decks.values():
        for cid in deck:
            assert cid in MINIMAL_DB.cards


def test_initial_tableau_defined() -> None:
    for cid in MINIMAL_DB.initial_tableau:
        assert cid in MINIMAL_DB.cards
    assert MINIMAL_DB.initial_government in MINIMAL_DB.cards


def test_each_age_has_one_government() -> None:
    for age, deck in MINIMAL_DB.civil_decks.items():
        govs = [cid for cid in deck
                if MINIMAL_DB.cards[cid].category is CardCategory.GOVERNMENT]
        assert len(govs) == 1, age


def test_card_ids_unique_definitions() -> None:
    assert len(MINIMAL_DB.cards) == len(set(MINIMAL_DB.cards))
    counts = Counter(cid for deck in MINIMAL_DB.civil_decks.values() for cid in deck)
    assert sum(counts.values()) == 68
