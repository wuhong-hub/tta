"""对局运行器: 驱动引擎与玩家完成一整局."""

from collections.abc import Sequence
from dataclasses import dataclass

from tta.agents.base import Player
from tta.engine.actions import IllegalActionError
from tta.engine.apply import apply
from tta.engine.constants import MAX_STEPS
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB
from tta.engine.setup import new_game
from tta.engine.state import state_hash
from tta.replay.recorder import ReplayRecorder


@dataclass(frozen=True)
class GameResult:
    """终局结果."""

    scores: tuple[int, ...]
    winners: tuple[int, ...]
    rounds: int
    steps: int


def run_game(db: CardDB, players: Sequence[Player], seed: int,
             recorder: ReplayRecorder | None = None) -> GameResult:
    """运行一整局.

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
    while not state.terminal:
        if steps >= MAX_STEPS:
            raise RuntimeError(f"step limit {MAX_STEPS} exceeded")
        legal = legal_actions(state, db)
        actor = players[state.current_player]
        action = actor.choose(state, legal, db)
        if action not in legal:
            raise IllegalActionError(
                f"agent {type(actor).__name__} returned illegal action {action!r}")
        if recorder:
            recorder.write_decision(round_=state.round,
                                    player=state.current_player,
                                    state_hash=state_hash(state),
                                    legal_count=len(legal), action=action)
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
