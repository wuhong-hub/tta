"""黄金回归: 随机玩家 2 人 seed 42 整局指纹锁死(P1 Task 14 重建).

指纹 = run_game 的 GameResult(scores/winners/rounds/steps) + 终局
state_hash。任何影响对局轨迹的引擎/卡牌改动都会破坏本测试, 届时须
人工确认变更符合官方规则后再回填指纹。

T13 回填说明(2026-07-26): 阵型替换旧卡由军事弃牌堆改入 removed(规则书
p3, 永不回流)改变终局状态分布 -> 仅终局 hash 变化, 轨迹四元组
(scores/winners/rounds/steps)不变。终局分数实际值为 (0, 0): 随机玩家
全程无文化增速, 4 张时代 III Impact 事件(impact_of_colonies/
architecture/agriculture/industry, 见终局 past_events)于 endgame_scoring
生效但各计 0 分——Impact 计分通路已被触发, 非零产出口径由
tests/engine/test_events_iii.py 脚本化场景覆盖(final_scores (13, 7) 等)。
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
    "4ece2aad2795bae7b5626471e7d3154bb854e2715cf464b073c4e7def108bbc4"
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
