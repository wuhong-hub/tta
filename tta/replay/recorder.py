"""JSONL 棋谱记录器."""

import json
from pathlib import Path
from types import TracebackType
from typing import Any

from tta.engine.actions import action_to_dict


class ReplayRecorder:
    """逐行写入棋谱事件; 每行一个 JSON 对象, 带 type 字段."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w", encoding="utf-8")

    def __enter__(self) -> "ReplayRecorder":
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def close(self) -> None:
        """关闭文件句柄."""
        if not self._fh.closed:
            self._fh.close()

    def _write(self, obj: dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._fh.flush()

    def write_meta(self, meta: dict[str, Any]) -> None:
        """写入对局元信息(seed/模型/手册版本等)."""
        self._write({"type": "meta", **meta})

    def write_decision(self, *, round_: int, player: int, state_hash: str,
                       legal_count: int, action: Any) -> None:
        """写入一次决策."""
        self._write({
            "type": "decision",
            "round": round_,
            "player": player,
            "state_hash": state_hash,
            "legal_count": legal_count,
            "action": action_to_dict(action),
        })

    def write_undo(self, void: int) -> None:
        """写入悔棋标记: 最近 void 条 decision 作废(回放方应跳过)."""
        self._write({"type": "undo", "void": void})

    def write_result(self, result: Any) -> None:
        """写入终局结果(GameResult; completed=False 为保存退出的未完成局)."""
        self._write({
            "type": "result",
            "scores": list(result.scores),
            "winners": list(result.winners),
            "rounds": result.rounds,
            "steps": result.steps,
            "completed": getattr(result, "completed", True),
        })
