"""开局设置测试: new_game 官方化."""

import pytest

from tta.cards import build_card_db
from tta.engine.enums import Age
from tta.engine.setup import new_game
from tta.engine.state import ROW_SLOTS, state_hash, workers_total

INITIAL_BUILDINGS = {
    "farm": {"agriculture": 2},
    "mine": {"bronze": 2},
    "lab": {"philosophy": 1},
    "infantry": {"warriors": 1},
}
"""官方开局工人布局(宗教 0 工人)."""

FUTURE_DECK_SIZES = {
    "I": {2: 44, 3: 50, 4: 53},
    "II": {2: 43, 3: 50, 4: 53},
    "III": {2: 44, 3: 50, 4: 53},
}
"""各未来时代牌堆长度(按人数)."""


@pytest.fixture(scope="module")
def db():
    return build_card_db()


def test_player_count_validation(db) -> None:
    for bad in (0, 1, 5):
        with pytest.raises(ValueError):
            new_game(db, bad, seed=1)
    for good in (2, 3, 4):
        assert len(new_game(db, good, seed=1).players) == good


def test_deterministic_same_seed(db) -> None:
    a = new_game(db, 2, seed=42)
    b = new_game(db, 2, seed=42)
    assert state_hash(a) == state_hash(b)


def test_different_seeds_shuffle_differently(db) -> None:
    a = new_game(db, 2, seed=1)
    b = new_game(db, 2, seed=2)
    assert a.card_row != b.card_row or a.future_decks != b.future_decks


def test_card_row_full_and_age_a_split(db) -> None:
    state = new_game(db, 3, seed=7)
    assert len(state.card_row) == ROW_SLOTS
    assert all(card_id is not None for card_id in state.card_row)
    assert len(state.civil_deck) == 7
    dealt = [c for c in state.card_row if c is not None]
    assert sorted(dealt + list(state.civil_deck)) == sorted(db.deck_for(Age.A, 3))


def test_future_decks_keys_and_lengths(db) -> None:
    for n in (2, 3, 4):
        state = new_game(db, n, seed=99)
        assert set(state.future_decks) == {"I", "II", "III"}
        for key, sizes in FUTURE_DECK_SIZES.items():
            assert len(state.future_decks[key]) == sizes[n]


def test_future_decks_match_deck_for_multiset(db) -> None:
    n = 3
    state = new_game(db, n, seed=11)
    for key, age in (("I", Age.I), ("II", Age.II), ("III", Age.III)):
        assert sorted(state.future_decks[key]) == sorted(db.deck_for(age, n))


def test_initial_player_state(db) -> None:
    state = new_game(db, 2, seed=5)
    for p in state.players:
        assert p.yellow_bank == 18
        assert p.blue_bank == 16
        assert p.worker_pool == 1
        assert p.buildings == INITIAL_BUILDINGS
        assert p.card_tokens == {}
        assert set(p.developed) == set(db.initial_tableau)
        assert "religion" in p.developed
        assert p.government == db.initial_government == "despotism"
        assert p.leader is None
        assert workers_total(p) == 7


def test_first_round_action_points_by_seat(db) -> None:
    state = new_game(db, 4, seed=5)
    for i, p in enumerate(state.players):
        assert p.civil_actions == i + 1
        assert p.military_actions == 0


def test_game_state_meta(db) -> None:
    state = new_game(db, 4, seed=3)
    assert state.round == 1
    assert state.age is Age.A
    assert state.current_player == 0
    assert not state.terminal
    assert isinstance(state.rng_state, int)
