"""属性测试: 任意随机对局中引擎不变量恒成立."""

from collections import Counter

import pytest

from tta.cards.minimal import MINIMAL_DB
from tta.engine import apply, legal_actions, new_game
from tta.engine.constants import INITIAL_YELLOW, ROW_SLOTS
from tta.engine.state import GameState, workers_total


def _universe() -> tuple[Counter, Counter]:
    """全部卡牌(牌堆合计)与每名玩家的起始卡牌."""
    deck_total: Counter = Counter()
    for deck in MINIMAL_DB.civil_decks.values():
        deck_total.update(deck)
    per_player: Counter = Counter(MINIMAL_DB.initial_tableau)
    per_player[MINIMAL_DB.initial_government] += 1
    return deck_total, per_player


def _cards_in_state(state: GameState) -> Counter:
    c: Counter = Counter()
    c.update(x for x in state.card_row if x is not None)
    c.update(state.civil_deck)
    for deck in state.future_decks.values():
        c.update(deck)
    c.update(state.discard)
    c.update(state.removed)
    for p in state.players:
        c.update(p.hand_civil)
        c.update(p.developed)
        c[p.government] += 1
    return c


def _assert_invariants(state: GameState, expected_cards: Counter) -> None:
    assert len(state.card_row) == ROW_SLOTS
    for p in state.players:
        assert p.materials >= 0 and p.food >= 0
        assert p.science >= 0 and p.culture >= 0
        assert p.civil_actions >= 0 and p.military_actions >= 0
        assert p.yellow_bank >= 0 and p.worker_pool >= 0
        assert p.yellow_bank + workers_total(p) == INITIAL_YELLOW
    assert _cards_in_state(state) == expected_cards


@pytest.mark.parametrize("seed", range(10))
def test_random_game_invariants(seed: int) -> None:
    import random

    rng = random.Random(seed)
    state = new_game(MINIMAL_DB, 2, seed=seed)
    deck_total, per_player = _universe()
    expected = deck_total + per_player + per_player  # 2 名玩家
    _assert_invariants(state, expected)
    while not state.terminal:
        legal = legal_actions(state, MINIMAL_DB)
        state = apply(state, rng.choice(legal), MINIMAL_DB)
        _assert_invariants(state, expected)
    assert state.final_scores is not None
