"""棋谱记录器链路测试(P1 Task 14 重建).

经 T13 的 orchestrator.run_game + ReplayRecorder 跑一整局, 校验
meta / decision / result 三类事件的结构与内容, 以及 decision 事件
action 的序列化往返(action_to_dict -> action_from_dict)。
"""

import json

import pytest

from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.engine.actions import action_from_dict
from tta.orchestrator.runner import run_game
from tta.replay.recorder import ReplayRecorder

SEED = 42


@pytest.fixture(scope="module")
def db():
    return build_card_db()


@pytest.fixture()
def events(db, tmp_path):
    """跑一局并返回 (events, result, path)."""
    path = tmp_path / "game.jsonl"
    players = [RandomPlayer(seed=4200), RandomPlayer(seed=4201)]
    with ReplayRecorder(path) as recorder:
        result = run_game(db, players, seed=SEED, recorder=recorder)
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines], result


def test_meta_event_structure(events) -> None:
    meta = events[0][0]
    assert meta["type"] == "meta"
    assert meta["seed"] == SEED
    assert meta["players"] == ["P0", "P1"]
    assert meta["agents"] == ["RandomPlayer", "RandomPlayer"]


def test_decision_events_structure(events) -> None:
    evs, result = events
    decisions = [e for e in evs if e["type"] == "decision"]
    # 每步一条 decision, 与 GameResult.steps 一致
    assert len(decisions) == result.steps
    for e in decisions:
        assert set(e) == {
            "type", "round", "player", "state_hash", "legal_count", "action",
        }
        assert e["round"] >= 1
        assert e["player"] in (0, 1)
        assert len(e["state_hash"]) == 64
        int(e["state_hash"], 16)  # 合法十六进制
        assert e["legal_count"] >= 1
        # action 可经 action_from_dict 还原
        action = action_from_dict(e["action"])
        assert action is not None
    # 回合数单调不减, 玩家轮转于 0/1
    rounds = [e["round"] for e in decisions]
    assert rounds == sorted(rounds)
    assert rounds[-1] == result.rounds


def test_result_event_structure(events) -> None:
    evs, result = events
    last = evs[-1]
    assert last["type"] == "result"
    assert last["scores"] == list(result.scores)
    assert last["winners"] == list(result.winners)
    assert last["rounds"] == result.rounds
    assert last["steps"] == result.steps
    # 事件序列: meta -> decision* -> result
    types = [e["type"] for e in evs]
    assert types[0] == "meta"
    assert types[-1] == "result"
    assert set(types[1:-1]) == {"decision"}


def test_recorder_creates_parent_dirs(db, tmp_path) -> None:
    path = tmp_path / "nested" / "dir" / "game.jsonl"
    with ReplayRecorder(path) as recorder:
        recorder.write_meta({"seed": 1})
    assert path.exists()
    meta = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert meta == {"type": "meta", "seed": 1}
