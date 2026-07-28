"""对局运行器: 驱动引擎与玩家完成一整局.

悔棋(history=True, 默认): 每次决策前压入检查点(状态/步数/座位/已写决策数);
人类玩家抛 UndoRequest 时回退到"该玩家上一个决策点"(AI 决策随之作废,
只回到人类自己的决策点, AI 决策本身不可单独悔), 该点之后的棋谱 decision
行以一条 {"type": "undo", "void": N} 标记作废(回放方应跳过最近 N 条
decision)。history=False 时 UndoRequest 被忽略并重新询问同一玩家。

保存退出: 玩家抛 QuitGame 时写入未完成标记的 result(completed=False,
scores 为当前文化分的参考值, winners 为空)并优雅返回。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from tta.agents.base import Player, QuitGame, UndoRequest
from tta.engine.actions import IllegalActionError
from tta.engine.apply import apply
from tta.engine.constants import MAX_STEPS
from tta.engine.legal import is_self_validating, legal_actions
from tta.engine.model import CardDB
from tta.engine.setup import new_game
from tta.engine.state import GameState, acting_index, state_hash
from tta.replay.recorder import ReplayRecorder


@dataclass(frozen=True)
class GameResult:
    """终局结果. completed=False 表示人类保存退出的未完成对局."""

    scores: tuple[int, ...]
    winners: tuple[int, ...]
    rounds: int
    steps: int
    completed: bool = True


@dataclass(frozen=True)
class _Checkpoint:
    """决策点检查点: 决策前状态 + 当时步数/座位/已写棋谱决策数."""

    state: GameState
    steps: int
    seat: int
    decisions_written: int


def run_game(db: CardDB, players: Sequence[Player], seed: int,
             recorder: ReplayRecorder | None = None,
             history: bool = True) -> GameResult:
    """运行一整局.

    Args:
        history: 是否记录检查点栈以支持悔棋(默认开; AI 自弈可关).

    Raises:
        IllegalActionError: 玩家返回了非法动作.
        RuntimeError: 超过 MAX_STEPS(引擎疑似死循环).
    """
    state = new_game(db, len(players), seed)
    if recorder:
        recorder.write_meta({
            "seed": seed,
            "players": [p.name for p in state.players],
            "agents": [type(a).__name__ for a in players],
        })
    steps = 0
    decisions_written = 0
    checkpoints: list[_Checkpoint] = []
    while not state.terminal:
        if steps >= MAX_STEPS:
            raise RuntimeError(f"step limit {MAX_STEPS} exceeded")
        legal = legal_actions(db, state)
        # 行动者 = pending[0].responder(响应期切换)或 current_player
        seat = acting_index(state)
        actor = players[seat]
        if history:
            checkpoints.append(
                _Checkpoint(state, steps, seat, decisions_written))
        try:
            action = actor.choose(state, legal, db)
        except UndoRequest:
            if not history:
                continue  # 悔棋关闭: 忽略并重新询问同一玩家
            state, steps, decisions_written = _rollback(
                checkpoints, seat, recorder, decisions_written)
            continue
        except QuitGame:
            result = GameResult(
                scores=tuple(p.culture for p in state.players),
                winners=(), rounds=state.round, steps=steps,
                completed=False)
            if recorder:
                recorder.write_result(result)
            return result
        # 合法性闸口: 常规动作须在 legal 中; 自校验动作(组合枚举爆炸无法
        # 完全入 legal, 如 ColonizeSacrifice 精确子集)由 apply 独立保证
        # 合法性, 闸口放行(非法仍由 apply 抛 IllegalActionError)
        if action not in legal and not is_self_validating(action):
            raise IllegalActionError(
                f"agent {type(actor).__name__} returned illegal action {action!r}")
        if recorder:
            recorder.write_decision(round_=state.round,
                                    player=seat,
                                    state_hash=state_hash(state),
                                    legal_count=len(legal), action=action)
            decisions_written += 1
        state = apply(state, action, db)
        steps += 1

    if state.final_scores is None:
        raise RuntimeError("terminal state without final scores")
    scores = state.final_scores
    best = max(scores)
    result = GameResult(scores=scores,
                        winners=tuple(i for i, s in enumerate(scores) if s == best),
                        rounds=state.round, steps=steps)
    if recorder:
        recorder.write_result(result)
    return result


def _rollback(checkpoints: list[_Checkpoint], seat: int,
              recorder: ReplayRecorder | None,
              decisions_written: int) -> tuple[GameState, int, int]:
    """回退到 seat 玩家上一个决策点; 无可回退时原地不动(重新询问).

    当前决策点的检查点是栈顶, 上一个同座位检查点之前的决策全部作废:
    状态/步数回退, 棋谱写 undo 标记作废该跨度内的 decision 行。
    """
    index = len(checkpoints) - 2  # 跳过栈顶(当前决策点)
    while index >= 0 and checkpoints[index].seat != seat:
        index -= 1
    if index < 0:
        current = checkpoints[-1]
        return current.state, current.steps, decisions_written
    checkpoint = checkpoints[index]
    voided = decisions_written - checkpoint.decisions_written
    if recorder and voided > 0:
        recorder.write_undo(voided)
    del checkpoints[index:]
    return checkpoint.state, checkpoint.steps, checkpoint.decisions_written
