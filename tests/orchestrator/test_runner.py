"""对局运行器测试: 随机玩家整局跑通 + 确定性 + 棋谱链."""

import json

import pytest

import tta.orchestrator.runner as runner_module
from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.engine import politics
from tta.engine.actions import (
    ColonizeSacrifice,
    DevelopTech,
    IllegalActionError,
    Resign,
)
from tta.engine.enums import Age, Phase
from tta.engine.state import ROW_SLOTS, GameState, PendingEffect, PlayerState
from tta.orchestrator.runner import GameResult, run_game
from tta.replay.recorder import ReplayRecorder


@pytest.fixture(scope="module")
def db():
    return build_card_db()


def _players(n: int, seed: int) -> list[RandomPlayer]:
    return [RandomPlayer(seed=seed * 100 + i) for i in range(n)]


def test_two_player_game_completes(db) -> None:
    result = run_game(db, _players(2, 42), seed=42)
    assert isinstance(result, GameResult)
    assert len(result.scores) == 2
    assert result.winners
    assert all(i in (0, 1) for i in result.winners)
    assert result.scores[result.winners[0]] == max(result.scores)
    assert result.steps > 0
    assert result.rounds > 1


def test_deterministic_same_seed(db) -> None:
    r1 = run_game(db, _players(2, 42), seed=42)
    r2 = run_game(db, _players(2, 42), seed=42)
    assert r1 == r2


def test_four_player_game_completes(db) -> None:
    result = run_game(db, _players(4, 7), seed=7)
    assert len(result.scores) == 4
    assert result.winners


class _CheatPlayer:
    """恒返回非法动作的玩家."""

    def choose(self, state, legal, db):  # noqa: ANN001, ANN201
        return DevelopTech("nonexistent_card")


def test_illegal_action_raises(db) -> None:
    with pytest.raises(IllegalActionError):
        run_game(db, [_CheatPlayer(), RandomPlayer(seed=1)], seed=1)


# --- 自校验复合动作闸口(P3-T1) -----------------------------------------------


_DEVELOPED = (
    "agriculture", "agriculture", "bronze", "bronze",
    "philosophy", "religion", "warriors",
)


def _sacrifice_game_state() -> GameState:
    """2 人局: P0 为殖民牺牲响应者(5 武士, 出价 4), P1 政治阶段的待决状态."""
    p0 = PlayerState(
        name="P0", developed=_DEVELOPED,
        buildings={
            "farm": {"agriculture": 2}, "mine": {"bronze": 2},
            "lab": {"philosophy": 1}, "infantry": {"warriors": 5},
        })
    p1 = PlayerState(
        name="P1", developed=_DEVELOPED,
        buildings={
            "farm": {"agriculture": 2}, "mine": {"bronze": 2},
            "lab": {"philosophy": 1}, "infantry": {"warriors": 1},
        })
    pending = PendingEffect(
        politics.KIND_COLONIZE_SACRIFICE, 0, responder=0,
        context={"territory": "developed_territory_i", "bid": 4, "bonus": 0})
    return GameState(
        round=2, age=Age.A, current_player=1,
        card_row=(None,) * ROW_SLOTS, civil_deck=(), future_decks={},
        discard=(), removed=(), players=(p0, p1), rng_state=42,
        phase=Phase.POLITICS, pending=(pending,))


class _SubsetSacrificePlayer:
    """提交 ColonizeSacrifice 精确子集(4/5 武士, 不在 legal 中)的玩家."""

    def choose(self, state, legal, db):  # noqa: ANN001, ANN201
        return ColonizeSacrifice(("warriors",) * 4)


class _WeakSacrificePlayer:
    """提交军力不足的非法 ColonizeSacrifice 子集的玩家."""

    def choose(self, state, legal, db):  # noqa: ANN001, ANN201
        return ColonizeSacrifice(("warriors",))  # 军力 1 < 出价 4


class _ResignPlayer:
    """政治阶段直接体面退出(2 人局 -> 对方立即判胜)的玩家."""

    def choose(self, state, legal, db):  # noqa: ANN001, ANN201
        return Resign()


def _patch_new_game(monkeypatch) -> None:  # noqa: ANN001, ANN202
    monkeypatch.setattr(
        runner_module, "new_game",
        lambda db, num_players, seed: _sacrifice_game_state())


def test_self_validating_subset_action_passes_gate(db, monkeypatch) -> None:
    # 精确子集(4 武士, 军力 4 = 出价 4)不在 legal(legal 仅 <=3 张组合 +
    # 全选锚点): 旧闸口必拒; 自校验动作放行后由 apply 独立校验通过
    _patch_new_game(monkeypatch)
    result = run_game(
        db, [_SubsetSacrificePlayer(), _ResignPlayer()], seed=1)
    # 第 1 步 P0 牺牲获殖民地; 第 2 步 P1 退出 -> P0 直接判胜
    assert result.steps == 2
    assert result.winners == (0,)


def test_invalid_self_validating_action_rejected_by_apply(db, monkeypatch) -> None:
    # 自校验动作过闸口不代表合法: 非法子集由 apply 抛 IllegalActionError
    _patch_new_game(monkeypatch)
    with pytest.raises(IllegalActionError):
        run_game(db, [_WeakSacrificePlayer(), _ResignPlayer()], seed=1)


def test_recorder_writes_meta_decision_result(db, tmp_path) -> None:
    path = tmp_path / "game.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(db, _players(2, 42), seed=42, recorder=rec)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert events[0]["type"] == "meta"
    assert events[0]["seed"] == 42
    assert events[0]["players"] == ["P0", "P1"]
    decisions = [e for e in events if e["type"] == "decision"]
    assert len(decisions) == result.steps
    assert all(len(e["state_hash"]) == 64 for e in decisions)
    last = events[-1]
    assert last["type"] == "result"
    assert last["scores"] == list(result.scores)
    assert last["winners"] == list(result.winners)
