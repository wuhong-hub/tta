"""开局测试."""

from tta.cards.minimal import MINIMAL_DB
from tta.engine.constants import INITIAL_YELLOW, ROW_SLOTS
from tta.engine.enums import Age
from tta.engine.setup import new_game
from tta.engine.state import workers_total


def test_new_game_basic() -> None:
    s = new_game(MINIMAL_DB, 2, seed=42)
    assert len(s.players) == 2
    assert s.age is Age.A and s.round == 1 and s.current_player == 0
    assert len(s.card_row) == ROW_SLOTS
    assert all(c is not None for c in s.card_row)
    assert len(s.civil_deck) == 17 - ROW_SLOTS  # 4
    assert set(s.future_decks) == {"I", "II", "III"}


def test_new_game_deterministic() -> None:
    assert new_game(MINIMAL_DB, 3, seed=7) == new_game(MINIMAL_DB, 3, seed=7)
    assert new_game(MINIMAL_DB, 3, seed=7) != new_game(MINIMAL_DB, 3, seed=8)


def test_player_initial_state() -> None:
    s = new_game(MINIMAL_DB, 2, seed=1)
    for p in s.players:
        assert p.government == "despotism"
        assert workers_total(p) == 4
        assert p.yellow_bank + workers_total(p) == INITIAL_YELLOW
        assert p.civil_actions == 4 and p.military_actions == 2


def test_supports_2_to_4_players() -> None:
    for n in (2, 3, 4):
        assert len(new_game(MINIMAL_DB, n, seed=1).players) == n
