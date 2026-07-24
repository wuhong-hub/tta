"""对局运行器测试."""

import pytest

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.engine import IllegalActionError
from tta.orchestrator.runner import GameResult, run_game


def _players(n: int, seed: int) -> list[RandomPlayer]:
    return [RandomPlayer(seed=seed + i) for i in range(n)]


def test_full_game_completes() -> None:
    result = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    assert isinstance(result, GameResult)
    assert len(result.scores) == 2
    assert result.winners
    assert result.rounds > 1 and result.steps > 0
    assert all(s >= 0 for s in result.scores)


def test_deterministic_same_seed() -> None:
    r1 = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    r2 = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    assert r1 == r2


def test_different_seed_differs() -> None:
    r1 = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    r2 = run_game(MINIMAL_DB, _players(2, 100), seed=43)
    assert r1 != r2


def test_four_players() -> None:
    result = run_game(MINIMAL_DB, _players(4, 7), seed=1)
    assert len(result.scores) == 4


def test_agent_illegal_action_raises() -> None:
    from tta.engine import TakeCard

    class Cheater:
        def choose(self, state, legal, db):  # type: ignore[no-untyped-def]
            return TakeCard(99)

    with pytest.raises(IllegalActionError):
        run_game(MINIMAL_DB, [Cheater(), RandomPlayer(seed=1)], seed=1)
