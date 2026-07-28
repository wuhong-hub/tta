"""CLI 冒烟测试."""

import json

from tta.cli.main import main


def test_selfplay_produces_jsonl(tmp_path) -> None:
    rc = main(["selfplay", "--players", "2", "--seed", "42",
               "--games", "1", "--out", str(tmp_path)])
    assert rc == 0
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    events = [json.loads(x) for x in files[0].read_text().splitlines()]
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "result"
    assert any(e["type"] == "decision" for e in events)


def test_selfplay_multiple_games(tmp_path) -> None:
    rc = main(["selfplay", "--players", "3", "--seed", "9",
               "--games", "2", "--out", str(tmp_path)])
    assert rc == 0
    assert len(list(tmp_path.glob("*.jsonl"))) == 2


def test_selfplay_four_players(tmp_path) -> None:
    """4 人局冒烟(T13): 产出 1 局 JSONL 且 meta/result 齐全."""
    rc = main(["selfplay", "--players", "4", "--seed", "7",
               "--games", "1", "--out", str(tmp_path)])
    assert rc == 0
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    events = [json.loads(x) for x in files[0].read_text().splitlines()]
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "result"


def test_selfplay_deterministic_same_seed(tmp_path) -> None:
    """同种子两局 JSONL 逐字节一致(P2 完成判定: 同种子确定性)."""
    for sub in ("a", "b"):
        rc = main(["selfplay", "--players", "3", "--seed", "11",
                   "--games", "1", "--out", str(tmp_path / sub)])
        assert rc == 0
    fa = next((tmp_path / "a").glob("*.jsonl")).read_bytes()
    fb = next((tmp_path / "b").glob("*.jsonl")).read_bytes()
    assert fa == fb


def test_replay_summary(tmp_path, capsys) -> None:
    main(["selfplay", "--players", "2", "--seed", "42",
          "--games", "1", "--out", str(tmp_path)])
    path = next(tmp_path.glob("*.jsonl"))
    assert main(["replay", str(path)]) == 0
    out = capsys.readouterr().out
    assert "seed: 42" in out
    assert "winners" in out


def test_play_quit_saves_unfinished(tmp_path, monkeypatch, capsys) -> None:
    """tta play 接线: HumanPlayer 可被注入; 保存退出后写未完成棋谱."""
    from tta.agents.base import QuitGame

    class _StubHuman:
        def __init__(self, **kwargs) -> None:
            pass

        def choose(self, state, legal, db):  # noqa: ANN001, ANN201
            raise QuitGame

    monkeypatch.setattr("tta.cli.main.HumanPlayer", _StubHuman)
    rc = main(["play", "--seat", "0", "--ai", "1", "--seed", "5",
               "--out", str(tmp_path)])
    assert rc == 0
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    events = [json.loads(x) for x in files[0].read_text().splitlines()]
    assert events[-1]["type"] == "result"
    assert events[-1]["completed"] is False
    assert "未完成" in capsys.readouterr().out


def test_play_invalid_seat(tmp_path, capsys) -> None:
    """座位越界(>= 总人数)直接报错返回非 0."""
    rc = main(["play", "--seat", "2", "--ai", "1", "--seed", "5",
               "--out", str(tmp_path)])
    assert rc == 2
    assert not list(tmp_path.glob("*.jsonl"))
