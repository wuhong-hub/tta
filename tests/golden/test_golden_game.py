"""黄金回归: 随机玩家 2 人 seed 42 整局指纹锁死(P1 Task 14 重建).

指纹 = run_game 的 GameResult(scores/winners/rounds/steps) + 终局
state_hash。任何影响对局轨迹的引擎/卡牌改动都会破坏本测试, 届时须
人工确认变更符合官方规则后再回填指纹。
"""

from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.engine.apply import apply
from tta.engine.legal import legal_actions
from tta.engine.setup import new_game
from tta.engine.state import acting_index, state_hash
from tta.orchestrator.runner import run_game

GOLDEN_SCORES = (0, 0)
GOLDEN_WINNERS = (0, 1)
GOLDEN_ROUNDS = 21
GOLDEN_STEPS = 211
GOLDEN_FINAL_STATE_HASH = (
    "d7e09ec2031e915ae003e2df845dc30cea16b6a820393fce34f901cb91414350"
)


def _players() -> list[RandomPlayer]:
    """与 tests/orchestrator 相同的随机玩家种子约定(seed * 100 + i)."""
    return [RandomPlayer(seed=4200), RandomPlayer(seed=4201)]


def test_golden_game_seed_42() -> None:
    db = build_card_db()
    result = run_game(db, _players(), seed=42)
    assert result.scores == GOLDEN_SCORES
    assert result.winners == GOLDEN_WINNERS
    assert result.rounds == GOLDEN_ROUNDS
    assert result.steps == GOLDEN_STEPS


def test_golden_final_state_hash() -> None:
    """按 runner 同口径重驱动(seed/玩家/动作选择一致), 锁终局 state_hash.

    行动者取 acting_index(pending 响应期为 responder), 与 runner 一致
    (T12 前误用 current_player, 终局 Impact 计分使两口径分歧暴露后修正)。
    """
    db = build_card_db()
    players = _players()
    state = new_game(db, 2, 42)
    while not state.terminal:
        legal = legal_actions(db, state)
        action = players[acting_index(state)].choose(state, legal, db)
        state = apply(state, action, db)
    assert state.final_scores == GOLDEN_SCORES
    assert state_hash(state) == GOLDEN_FINAL_STATE_HASH
