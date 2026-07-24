"""随机玩家测试."""

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.engine import legal_actions, new_game


def test_choose_returns_legal_action() -> None:
    state = new_game(MINIMAL_DB, 2, seed=1)
    legal = legal_actions(state, MINIMAL_DB)
    agent = RandomPlayer(seed=99)
    for _ in range(20):
        assert agent.choose(state, legal, MINIMAL_DB) in legal


def test_deterministic() -> None:
    state = new_game(MINIMAL_DB, 2, seed=1)
    legal = legal_actions(state, MINIMAL_DB)
    a = RandomPlayer(seed=5)
    b = RandomPlayer(seed=5)
    assert [a.choose(state, legal, MINIMAL_DB) for _ in range(10)] == \
           [b.choose(state, legal, MINIMAL_DB) for _ in range(10)]
