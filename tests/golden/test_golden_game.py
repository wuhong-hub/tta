"""黄金回归: 固定种子对局的终局指纹不得变化."""

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.orchestrator.runner import run_game

EXPECTED_SCORES = (0, 0)
EXPECTED_ROUNDS = 23
EXPECTED_STEPS = 140


def test_golden_game() -> None:
    result = run_game(MINIMAL_DB, [RandomPlayer(11), RandomPlayer(22)], seed=42)
    assert result.scores == EXPECTED_SCORES
    assert result.rounds == EXPECTED_ROUNDS
    assert result.steps == EXPECTED_STEPS
