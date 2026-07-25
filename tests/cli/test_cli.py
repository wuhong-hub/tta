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


def test_replay_summary(tmp_path, capsys) -> None:
    main(["selfplay", "--players", "2", "--seed", "42",
          "--games", "1", "--out", str(tmp_path)])
    path = next(tmp_path.glob("*.jsonl"))
    assert main(["replay", str(path)]) == 0
    out = capsys.readouterr().out
    assert "seed: 42" in out
    assert "winners" in out
