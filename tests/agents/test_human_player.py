"""HumanPlayer 测试: 脚本化输入驱动 choose、悔棋回退、保存退出、人机整局."""

import json
import re

import pytest

from tta.agents.base import QuitGame, UndoRequest
from tta.agents.human_player import HumanPlayer
from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.engine import legal_actions, new_game
from tta.orchestrator.runner import run_game
from tta.replay.recorder import ReplayRecorder


@pytest.fixture(scope="module")
def db():
    return build_card_db()


class _Script:
    """脚本化 input/output: 静态队列 + 全 pass 动态回退.

    队列耗尽后进入 pass 模式: 从最近一次渲染的动作菜单中解析
    "结束回合/跳过政治阶段/退出殖民竞拍/结束响应/放弃响应" 的编号,
    否则回 "1"(菜单首项、子菜单首选项, 恒为合法或可被引导流程消化).
    """

    _PASS_PATTERNS = (
        r"^\s*(\d+)\. 结束回合",
        r"^\s*(\d+)\. 跳过政治阶段",
        r"^\s*(\d+)\. 退出殖民竞拍",
        r"^\s*(\d+)\. 结束响应",
        r"^\s*(\d+)\. 放弃响应",
    )

    def __init__(self, lines: list[str] | None = None) -> None:
        self._lines = list(lines or [])
        self.out: list[str] = []
        self._menu = ""

    def input(self, prompt: str = "") -> str:
        if self._lines:
            return self._lines.pop(0)
        for pattern in self._PASS_PATTERNS:
            m = re.search(pattern, self._menu, re.M)
            if m:
                return m.group(1)
        return "1"

    def output(self, text: str = "") -> None:
        self.out.append(text)
        if "可用动作" in text:
            self._menu = text

    @property
    def text(self) -> str:
        return "\n".join(self.out)


# --- choose 基本行为 ------------------------------------------------------------


def test_choose_renders_and_picks(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["1"])
    player = HumanPlayer(input_fn=script.input, output_fn=script.output)
    action = player.choose(state, legal, db)
    assert action == legal[0]
    # 输出含整屏渲染与动作菜单
    assert "时代" in script.text
    assert "可用动作" in script.text
    assert "你的面板" in script.text


def test_choose_invalid_input_retries(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["foo", "2"])
    player = HumanPlayer(input_fn=script.input, output_fn=script.output)
    assert player.choose(state, legal, db) == legal[1]
    assert "无效" in script.text


def test_choose_quit_raises(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["q"])
    player = HumanPlayer(input_fn=script.input, output_fn=script.output)
    with pytest.raises(QuitGame):
        player.choose(state, legal, db)


def test_choose_undo_raises(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["u"])
    player = HumanPlayer(input_fn=script.input, output_fn=script.output)
    with pytest.raises(UndoRequest):
        player.choose(state, legal, db)


def test_choose_eof_treated_as_quit(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)

    def eof_input(prompt: str = "") -> str:
        raise EOFError

    player = HumanPlayer(input_fn=eof_input, output_fn=lambda t: None)
    with pytest.raises(QuitGame):
        player.choose(state, legal, db)


# --- runner 集成: 悔棋 / 退出 / 整局 ----------------------------------------------


class _UndoOncePlayer:
    """第二次决策时请求悔棋, 其余选首个合法动作."""

    def __init__(self) -> None:
        self.calls = 0

    def choose(self, state, legal, db):  # noqa: ANN001, ANN201
        self.calls += 1
        if self.calls == 2:
            raise UndoRequest
        return legal[0]


class _QuitPlayer:
    """首次决策即保存退出."""

    def choose(self, state, legal, db):  # noqa: ANN001, ANN201
        raise QuitGame


def test_runner_undo_rolls_back(db, tmp_path) -> None:
    path = tmp_path / "undo.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(db, [_UndoOncePlayer(), RandomPlayer(seed=1)],
                          seed=3, recorder=rec)
    assert result.completed
    events = [json.loads(x) for x in path.read_text().splitlines()]
    undos = [e for e in events if e["type"] == "undo"]
    assert len(undos) == 1
    assert undos[0]["void"] >= 1  # 作废决策数 = 回退跨度
    assert events[-1]["type"] == "result"


def test_runner_undo_disabled_reasks(db) -> None:
    """history=False 时不支持悔棋: UndoRequest 被忽略并重新询问同一玩家."""
    player = _UndoOncePlayer()
    result = run_game(db, [player, RandomPlayer(seed=1)], seed=3,
                      history=False)
    assert result.completed
    assert player.calls > 2  # 悔棋请求后仍被再次询问


def test_runner_quit_saves_unfinished(db, tmp_path) -> None:
    path = tmp_path / "quit.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(db, [_QuitPlayer(), RandomPlayer(seed=1)],
                          seed=3, recorder=rec)
    assert not result.completed
    assert result.winners == ()
    events = [json.loads(x) for x in path.read_text().splitlines()]
    last = events[-1]
    assert last["type"] == "result"
    assert last["completed"] is False


def test_human_vs_ai_full_game(db, tmp_path) -> None:
    """2 人人机整局: 人类全程 pass 脚本, 跑通并终局, 棋谱完整."""
    script = _Script()
    human = HumanPlayer(input_fn=script.input, output_fn=script.output)
    path = tmp_path / "game.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(db, [human, RandomPlayer(seed=7)], seed=11,
                          recorder=rec)
    assert result.completed
    assert len(result.scores) == 2
    assert result.rounds > 1
    events = [json.loads(x) for x in path.read_text().splitlines()]
    assert events[0]["type"] == "meta"
    assert events[0]["agents"] == ["HumanPlayer", "RandomPlayer"]
    assert events[-1]["type"] == "result"
    assert events[-1]["completed"] is True
    decisions = [e for e in events if e["type"] == "decision"]
    assert len(decisions) == result.steps
    # 人类确实有决策行
    assert any(e["player"] == 0 for e in decisions)


def test_human_undo_then_continue(db, tmp_path) -> None:
    """人类首步先悔棋(无可回退, 重新询问), 之后正常 pass 到终局."""
    script = _Script(["u"])
    human = HumanPlayer(input_fn=script.input, output_fn=script.output)
    path = tmp_path / "undo_first.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(db, [human, RandomPlayer(seed=5)], seed=13,
                          recorder=rec)
    assert result.completed
    # 首个决策点悔棋无可回退: 棋谱无 undo 标记
    events = [json.loads(x) for x in path.read_text().splitlines()]
    assert not any(e["type"] == "undo" for e in events)
