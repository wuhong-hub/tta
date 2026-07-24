"""棋谱记录器测试."""

import json
from pathlib import Path

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.orchestrator.runner import run_game
from tta.replay.recorder import ReplayRecorder


def test_replay_file_structure(tmp_path: Path) -> None:
    path = tmp_path / "game.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(MINIMAL_DB, [RandomPlayer(1), RandomPlayer(2)],
                          seed=42, recorder=rec)
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert lines[0]["type"] == "meta"
    assert lines[0]["seed"] == 42
    assert lines[-1]["type"] == "result"
    assert lines[-1]["scores"] == list(result.scores)
    decisions = [x for x in lines if x["type"] == "decision"]
    assert len(decisions) == result.steps
    for d in decisions:
        assert {"round", "player", "state_hash", "legal_count", "action"} <= set(d)
