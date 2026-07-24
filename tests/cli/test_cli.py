"""CLI 冒烟测试."""

import json
from pathlib import Path

from tta.cli.main import main


def test_selfplay_writes_replay(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    main(["selfplay", "--players", "2", "--seed", "42", "--games", "1",
          "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert "winner" in out
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    first = json.loads(files[0].read_text().splitlines()[0])
    assert first["type"] == "meta"


def test_replay_command(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    main(["selfplay", "--players", "2", "--seed", "42", "--games", "1",
          "--out", str(tmp_path)])
    capsys.readouterr()
    file = next(tmp_path.glob("*.jsonl"))
    main(["replay", str(file)])
    out = capsys.readouterr().out
    assert "scores" in out and "seed: 42" in out
