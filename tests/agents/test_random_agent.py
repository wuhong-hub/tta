"""随机玩家测试."""

from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.engine.legal import legal_actions
from tta.engine.setup import new_game


def test_choose_returns_legal_action() -> None:
    db = build_card_db()
    state = new_game(db, 2, seed=42)
    legal = legal_actions(db, state)
    agent = RandomPlayer(seed=1)
    for _ in range(20):
        assert agent.choose(state, legal, db) in legal


def test_same_seed_same_choices() -> None:
    db = build_card_db()
    state = new_game(db, 2, seed=42)
    legal = legal_actions(db, state)
    agent_a = RandomPlayer(seed=7)
    agent_b = RandomPlayer(seed=7)
    choices_a = [agent_a.choose(state, legal, db) for _ in range(10)]
    choices_b = [agent_b.choose(state, legal, db) for _ in range(10)]
    assert choices_a == choices_b
