"""棋谱解析/回合摘要/指定手跳转/文本战报测试(P3-T9).

覆盖: undo 作废解释(有效决策 = decisions − void)、round 摘要动作聚合、
--turn N 确定性重放(与当时 state_hash 一致)、text_report 结构、
recorder 版本信息补写与回放版本警告。
"""

import json

import pytest

from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.cli.main import main
from tta.engine.state import state_hash
from tta.orchestrator.runner import run_game
from tta.replay.recorder import ReplayRecorder, current_engine_version
from tta.replay.report import (
    parse_replay,
    replay_to_state,
    round_summary,
    text_report,
    turning_points,
    walk_states,
)

SEED = 42


@pytest.fixture(scope="module")
def db():
    return build_card_db()


@pytest.fixture()
def game_path(db, tmp_path):
    """跑一局真实对局并返回棋谱路径."""
    path = tmp_path / "game.jsonl"
    players = [RandomPlayer(seed=4200), RandomPlayer(seed=4201)]
    with ReplayRecorder(path) as recorder:
        run_game(db, players, seed=SEED, recorder=recorder)
    return path


def _decision(round_: int, player: int, action_type: str = "pass",
              **action_kw: object) -> dict:
    return {
        "type": "decision",
        "round": round_,
        "player": player,
        "state_hash": "0" * 64,
        "legal_count": 1,
        "action": {"type": action_type, **action_kw},
    }


def _write_events(path, events) -> None:
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n"
                            for e in events), encoding="utf-8")


def _crafted_path(tmp_path, extra_decisions: list[dict],
                  undos: list[int] | None = None,
                  with_result: bool = True):
    """手工棋谱: meta + extra_decisions(中间按 undos 插入 undo 标记) + result."""
    events: list[dict] = [{
        "type": "meta", "seed": 1, "players": ["P0", "P1"],
        "agents": ["RandomPlayer", "RandomPlayer"],
        "engine_version": current_engine_version(),
    }]
    events.extend(extra_decisions)
    for void in undos or []:
        events.append({"type": "undo", "void": void})
    if with_result:
        events.append({
            "type": "result", "scores": [10, 8], "winners": [0],
            "rounds": 3, "steps": len(extra_decisions), "completed": True,
        })
    path = tmp_path / "crafted.jsonl"
    _write_events(path, events)
    return path


# --- parse_replay / undo 作废解释 --------------------------------------------


def test_parse_real_game(game_path) -> None:
    replay = parse_replay(game_path)
    assert replay.meta["seed"] == SEED
    assert replay.meta["players"] == ["P0", "P1"]
    assert replay.result is not None
    assert replay.result["winners"]
    assert replay.decisions  # 非空
    assert replay.undos == ()
    # 无 undo 时全部有效
    assert replay.effective == replay.decisions
    assert replay.voided == ()
    # 原始序号连续
    assert [d.index for d in replay.decisions] == list(
        range(len(replay.decisions)))


def test_parse_undo_marks_recent_decisions_void(tmp_path) -> None:
    decisions = [_decision(1, i % 2) for i in range(5)]
    path = _crafted_path(tmp_path, decisions, undos=[2])
    replay = parse_replay(path)
    assert replay.undos == (2,)
    voided_index = {d.index for d in replay.voided}
    assert voided_index == {3, 4}  # 最近 2 条作废
    assert [d.index for d in replay.effective] == [0, 1, 2]


def test_parse_undo_then_new_decisions(tmp_path) -> None:
    """undo 后新写的 decision 有效; 作废只回溯最近 N 条."""
    events_decisions = [_decision(1, i % 2) for i in range(4)]
    path = tmp_path / "g.jsonl"
    events: list[dict] = [{
        "type": "meta", "seed": 1, "players": ["P0", "P1"],
        "engine_version": current_engine_version(),
    }]
    events.extend(events_decisions)
    events.append({"type": "undo", "void": 3})
    events.extend([_decision(1, 0), _decision(1, 1)])
    events.append({"type": "result", "scores": [1, 0], "winners": [0],
                   "rounds": 1, "steps": 3, "completed": True})
    _write_events(path, events)
    replay = parse_replay(path)
    assert {d.index for d in replay.voided} == {1, 2, 3}
    assert [d.index for d in replay.effective] == [0, 4, 5]


def test_parse_missing_result(tmp_path) -> None:
    path = _crafted_path(tmp_path, [_decision(1, 0)], with_result=False)
    replay = parse_replay(path)
    assert replay.result is None
    assert len(replay.effective) == 1


# --- round_summary 聚合 -------------------------------------------------------


def test_round_summary_aggregates_action_types(tmp_path) -> None:
    decisions = [
        _decision(1, 0, "play_aggression", card_id="raid", target=1),
        _decision(1, 1, "play_leader", card_id="leader_x"),
        _decision(1, 0),
        _decision(2, 1, "declare_war", card_id="war_x", target=0),
        _decision(2, 0, "build_wonder_stage", count=2),
        _decision(2, 1, "colonize_bid", amount=3),
    ]
    path = _crafted_path(tmp_path, decisions)
    summary = round_summary(parse_replay(path))
    lines = summary.splitlines()
    r1 = next(x for x in lines if x.startswith("第 1 轮"))
    r2 = next(x for x in lines if x.startswith("第 2 轮"))
    assert "P0×2" in r1 and "P1×1" in r1
    assert "侵略×1" in r1 and "领袖×1" in r1
    assert "P0×1" in r2 and "P1×2" in r2
    assert "宣战×1" in r2 and "奇迹阶段×2" in r2 and "殖民×1" in r2


def test_round_summary_excludes_void(tmp_path) -> None:
    decisions = [_decision(1, 0), _decision(1, 1), _decision(1, 1)]
    path = _crafted_path(tmp_path, decisions, undos=[1])
    summary = round_summary(parse_replay(path))
    r1 = next(x for x in summary.splitlines() if x.startswith("第 1 轮"))
    assert "P0×1" in r1 and "P1×1" in r1  # 作废的 P1 决策不计入
    assert "作废 1" in summary


def test_round_summary_with_db_detects_age_transition(db, game_path) -> None:
    summary = round_summary(parse_replay(game_path), db=db)
    # 完整对局必经历时代切换
    assert "时代切换" in summary


# --- replay_to_state 确定性重放 ------------------------------------------------


def test_replay_to_state_hash_matches(db, game_path) -> None:
    replay = parse_replay(game_path)
    total = len(replay.effective)
    for turn in (1, 2, total // 2, total):
        state = replay_to_state(replay, db, turn)
        assert state_hash(state) == replay.effective[turn - 1].state_hash


def test_replay_to_state_out_of_range(db, game_path) -> None:
    replay = parse_replay(game_path)
    total = len(replay.effective)
    with pytest.raises(ValueError, match="turn"):
        replay_to_state(replay, db, 0)
    with pytest.raises(ValueError, match="turn"):
        replay_to_state(replay, db, total + 1)


def test_walk_states_yields_effective_only(db, game_path) -> None:
    replay = parse_replay(game_path)
    steps = list(walk_states(replay, db))
    assert len(steps) == len(replay.effective)
    for rec, before, _after in steps:
        assert state_hash(before) == rec.state_hash


# --- turning_points / text_report --------------------------------------------


def test_turning_points_first_aggression_without_db(tmp_path) -> None:
    decisions = [
        _decision(1, 0),
        _decision(3, 1, "play_aggression", card_id="raid", target=0),
        _decision(4, 0, "declare_war", card_id="war_x", target=1),
    ]
    path = _crafted_path(tmp_path, decisions)
    points = turning_points(parse_replay(path))
    assert any("第 3 轮" in p and "首次侵略" in p and "P1" in p
               for p in points)
    assert any("第 4 轮" in p and "首次宣战" in p for p in points)


def test_turning_points_with_db_age_transitions(db, game_path) -> None:
    replay = parse_replay(game_path)
    points = turning_points(replay, db=db)
    age_points = [p for p in points if "时代切换" in p]
    assert age_points  # 完整对局必有时代切换
    # 与独立重放交叉校验: 首个奇观完成记录与实际模拟一致
    wonder_done_rounds = set()
    for rec, before, after in walk_states(replay, db):
        for pb, pa in zip(before.players, after.players, strict=True):
            if len(pa.wonders) > len(pb.wonders):
                wonder_done_rounds.add(rec.round)
    if wonder_done_rounds:
        first = min(wonder_done_rounds)
        assert any("首个奇观完成" in p and f"第 {first} 轮" in p
                   for p in points)
    else:
        assert not any("首个奇观完成" in p for p in points)


def test_text_report_structure(db, game_path) -> None:
    replay = parse_replay(game_path)
    report = text_report(replay, db=db)
    for section in ("对局战报", "[元信息]", "[终局]", "[关键转折点]", "[回合摘要]"):
        assert section in report
    assert f"seed: {SEED}" in report
    assert "胜者" in report and "P0" in report
    assert "有效决策" in report
    assert "时代切换" in report  # 完整对局必有


def test_text_report_unfinished(tmp_path) -> None:
    events = [{
        "type": "meta", "seed": 7, "players": ["P0", "P1"],
        "engine_version": current_engine_version(),
    }, _decision(1, 0), {
        "type": "result", "scores": [3, 2], "winners": [],
        "rounds": 1, "steps": 1, "completed": False,
    }]
    path = tmp_path / "unfinished.jsonl"
    _write_events(path, events)
    report = text_report(parse_replay(path))
    assert "未完成" in report


# --- 版本信息 ------------------------------------------------------------------


def test_meta_carries_engine_version(game_path) -> None:
    meta = json.loads(game_path.read_text(encoding="utf-8").splitlines()[0])
    assert meta["engine_version"] == current_engine_version()


# --- CLI ----------------------------------------------------------------------


def test_cli_replay_shows_effective_and_void(tmp_path, capsys) -> None:
    decisions = [_decision(1, i % 2) for i in range(5)]
    path = _crafted_path(tmp_path, decisions, undos=[2])
    assert main(["replay", str(path)]) == 0
    out = capsys.readouterr().out
    assert "decisions: 3 effective" in out
    assert "2 voided" in out
    assert "winners" in out


def test_cli_replay_version_warning(tmp_path, capsys) -> None:
    path = _crafted_path(tmp_path, [_decision(1, 0)])
    # 篡改版本号
    lines = path.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])
    meta["engine_version"] = "0.0.0+bogus"
    lines[0] = json.dumps(meta, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["replay", str(path)]) == 0  # 警告不阻止
    err = capsys.readouterr().err
    assert "版本" in err and "0.0.0+bogus" in err


def test_cli_replay_missing_version_warns(tmp_path, capsys) -> None:
    events = [
        {"type": "meta", "seed": 1, "players": ["P0", "P1"]},
        _decision(1, 0),
        {"type": "result", "scores": [1, 0], "winners": [0],
         "rounds": 1, "steps": 1, "completed": True},
    ]
    path = tmp_path / "old.jsonl"
    _write_events(path, events)
    assert main(["replay", str(path)]) == 0
    assert "版本" in capsys.readouterr().err


def test_cli_replay_turn_renders_state(db, game_path, capsys) -> None:
    replay = parse_replay(game_path)
    turn = 3
    expected_seat = replay.effective[turn - 1].player
    assert main(["replay", str(game_path), "--turn", str(turn)]) == 0
    out = capsys.readouterr().out
    assert "卡牌列" in out and "时代" in out
    assert f"--- 你的面板 P{expected_seat} ---" in out


def test_cli_replay_turn_seat_override(db, game_path, capsys) -> None:
    assert main(["replay", str(game_path), "--turn", "3",
                 "--seat", "1"]) == 0
    out = capsys.readouterr().out
    assert "--- 你的面板 P1 ---" in out


def test_cli_replay_turn_out_of_range(db, game_path, capsys) -> None:
    rc = main(["replay", str(game_path), "--turn", "999999"])
    assert rc == 2
    assert "turn" in capsys.readouterr().err


def test_cli_replay_report(db, game_path, capsys) -> None:
    assert main(["replay", str(game_path), "--report"]) == 0
    out = capsys.readouterr().out
    assert "对局战报" in out and "[回合摘要]" in out
