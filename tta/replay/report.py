"""棋谱解析与战报生成(纯函数为主, 仅 IO 在 parse_replay 入口).

Replay = meta + decisions(含 undo 作废标记) + result。undo 标记
{"type": "undo", "void": N} 表示其之前最近 N 条 decision 作废(append-only
棋谱的悔棋语义, 见 orchestrator.runner); 有效决策序列 = decisions − void。

确定性重放: walk_states / replay_to_state 从 meta.seed 重建初始状态,
按有效决策顺序 apply, 逐步校验记录的 state_hash(不一致抛
ReplayMismatchError, 通常意味着牌库/引擎版本与棋谱不符)。

round_summary / text_report 面向后续 LLM 复盘: 结构清晰的分节文本。
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tta.engine.actions import action_from_dict
from tta.engine.apply import apply
from tta.engine.enums import Age
from tta.engine.model import CardDB
from tta.engine.setup import new_game
from tta.engine.state import GameState
from tta.engine.state import state_hash as compute_state_hash


class ReplayMismatchError(RuntimeError):
    """重放状态与棋谱记录的 state_hash 不一致."""


@dataclass(frozen=True)
class DecisionRecord:
    """一条 decision 行; void=True 表示被后续 undo 标记作废."""

    index: int           # 在棋谱 decision 序列中的原始序号(0 基, 含作废)
    round: int
    player: int
    state_hash: str      # 决策时刻的状态哈希(重放校验用)
    legal_count: int
    action: dict[str, Any]
    void: bool = False


@dataclass(frozen=True)
class Replay:
    """结构化棋谱. result=None 表示棋谱无终局行(截断/异常退出)."""

    meta: dict[str, Any]
    decisions: tuple[DecisionRecord, ...]
    undos: tuple[int, ...]
    result: dict[str, Any] | None

    @property
    def effective(self) -> tuple[DecisionRecord, ...]:
        """有效决策序列(未被 undo 作废), 顺序与原棋谱一致."""
        return tuple(d for d in self.decisions if not d.void)

    @property
    def voided(self) -> tuple[DecisionRecord, ...]:
        """被 undo 作废的决策."""
        return tuple(d for d in self.decisions if d.void)


def parse_replay(path: Path) -> Replay:
    """解析 JSONL 棋谱为 Replay; undo 标记回溯作废最近 N 条 decision."""
    meta: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    decisions: list[DecisionRecord] = []
    undos: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        kind = event["type"]
        if kind == "meta":
            meta = event
        elif kind == "decision":
            decisions.append(DecisionRecord(
                index=len(decisions),
                round=event["round"],
                player=event["player"],
                state_hash=event["state_hash"],
                legal_count=event["legal_count"],
                action=event["action"],
            ))
        elif kind == "undo":
            void = int(event["void"])
            undos.append(void)
            # 回溯作废最近 void 条未作废决策
            for rec in reversed(decisions):
                if void <= 0:
                    break
                if not rec.void:
                    decisions[rec.index] = replace(rec, void=True)
                    void -= 1
        elif kind == "result":
            result = event
    return Replay(meta=meta, decisions=tuple(decisions),
                  undos=tuple(undos), result=result)


def walk_states(
    replay: Replay, db: CardDB,
) -> Iterator[tuple[DecisionRecord, GameState, GameState]]:
    """从 meta.seed 确定性重放, 逐有效决策产出 (决策, 决策前状态, 决策后状态).

    每个决策前状态与记录的 state_hash 校验, 不一致抛 ReplayMismatchError。
    """
    state = new_game(db, len(replay.meta["players"]), replay.meta["seed"])
    for rec in replay.effective:
        actual = compute_state_hash(state)
        if actual != rec.state_hash:
            raise ReplayMismatchError(
                f"决策 #{rec.index}(第 {rec.round} 轮 P{rec.player})重放哈希不符: "
                f"期望 {rec.state_hash[:12]}…, 实际 {actual[:12]}…"
                "(牌库/引擎版本可能与棋谱不符)")
        nxt = apply(state, action_from_dict(rec.action), db)
        yield rec, state, nxt
        state = nxt


def replay_to_state(replay: Replay, db: CardDB, turn: int) -> GameState:
    """重放到第 turn 个有效决策之前的状态(1 基; 即该决策被做出时的盘面).

    Raises:
        ValueError: turn 越界(合法范围 1..有效决策数).
        ReplayMismatchError: 重放轨迹与记录哈希不符.
    """
    total = len(replay.effective)
    if not 1 <= turn <= total:
        raise ValueError(
            f"turn 越界: {turn}(有效决策共 {total} 条, 合法 1..{total})")
    state = new_game(db, len(replay.meta["players"]), replay.meta["seed"])
    target = replay.effective[turn - 1]
    for rec in replay.effective[:turn - 1]:
        state = apply(state, action_from_dict(rec.action), db)
    actual = compute_state_hash(state)
    if actual != target.state_hash:
        raise ReplayMismatchError(
            f"第 {turn} 个有效决策重放哈希不符: 期望 {target.state_hash[:12]}…, "
            f"实际 {actual[:12]}…(牌库/引擎版本可能与棋谱不符)")
    return state


# --- 回合摘要 ------------------------------------------------------------------

# 动作类型 -> 关键事件标签(聚合顺序即展示顺序)
_ACTION_EVENT_LABELS: tuple[tuple[str, str], ...] = (
    ("play_aggression", "侵略"),
    ("declare_war", "宣战"),
    ("colonize", "殖民"),          # 前缀匹配 colonize_*
    ("build_wonder_stage", "奇迹阶段"),
    ("play_leader", "领袖"),
    ("play_tactics", "阵型"),
    ("copy_tactics", "阵型"),
    ("seed_event", "筹划事件"),
    ("resign", "退出"),
)


def _action_events(decisions: list[DecisionRecord]) -> list[str]:
    """按动作类型聚合一轮内的关键事件(保持 _ACTION_EVENT_LABELS 顺序)."""
    events: list[str] = []
    for action_type, label in _ACTION_EVENT_LABELS:
        count = 0
        for rec in decisions:
            kind = rec.action["type"]
            if action_type == "colonize":
                hit = kind.startswith("colonize_")
            else:
                hit = kind == action_type
            if hit:
                # 奇迹阶段按阶段数累计, 其余按次数
                count += int(rec.action.get("count", 1)) if \
                    kind == "build_wonder_stage" else 1
        if count:
            events.append(f"{label}×{count}")
    return events


@dataclass(frozen=True)
class RoundInfo:
    """一轮的摘要: 各玩家有效决策数 + 关键事件描述."""

    round: int
    per_player: tuple[tuple[int, int], ...]   # (座位, 有效决策数), 按座位升序
    events: tuple[str, ...]


def _analyze(replay: Replay, db: CardDB | None) -> tuple[list[RoundInfo],
                                                        list[str]]:
    """共用分析: 回合摘要 + 关键转折点(db 给定时经重放精确识别)."""
    by_round: dict[int, list[DecisionRecord]] = {}
    for rec in replay.effective:
        by_round.setdefault(rec.round, []).append(rec)
    sim_events: dict[int, list[str]] = {r: [] for r in by_round}
    points: list[tuple[int, int, str]] = []  # (轮次, 序号, 描述)
    seq = 0

    def _point(round_: int, text: str) -> None:
        nonlocal seq
        points.append((round_, seq, text))
        seq += 1

    # 动作层转折点(无需 db)
    for rec in replay.effective:
        kind = rec.action["type"]
        if kind == "play_aggression":
            _point(rec.round,
                   f"首次侵略(P{rec.player} → P{rec.action['target']})")
            break
    for rec in replay.effective:
        if rec.action["type"] == "declare_war":
            _point(rec.round,
                   f"首次宣战(P{rec.player} → P{rec.action['target']})")
            break

    if db is not None:
        first_wonder_done = False
        for rec, before, after in walk_states(replay, db):
            # IV 为终局标记时代(无牌堆), 不计入时代切换事件
            if after.age != before.age and after.age is not Age.IV:
                text = f"时代切换 {before.age.value}→{after.age.value}"
                sim_events[rec.round].append(text)
                _point(rec.round, text)
            for seat, (pb, pa) in enumerate(
                    zip(before.players, after.players, strict=True)):
                for card_id in pa.wonders:
                    if card_id not in pb.wonders:
                        name = db.get(card_id).name
                        sim_events[rec.round].append(
                            f"奇观完成 {name}(P{seat})")
                        if not first_wonder_done:
                            first_wonder_done = True
                            _point(rec.round, f"首个奇观完成 {name}(P{seat})")
                for card_id in pa.colonies:
                    if card_id not in pb.colonies:
                        sim_events[rec.round].append(
                            f"殖民 {db.get(card_id).name}(P{seat})")

    infos: list[RoundInfo] = []
    for round_ in sorted(by_round):
        decisions = by_round[round_]
        counts: dict[int, int] = {}
        for rec in decisions:
            counts[rec.player] = counts.get(rec.player, 0) + 1
        events = _action_events(decisions) + sim_events[round_]
        infos.append(RoundInfo(round=round_,
                               per_player=tuple(sorted(counts.items())),
                               events=tuple(events)))
    ordered_points = [f"第 {round_} 轮: {text}"
                      for round_, _, text in sorted(points)]
    return infos, ordered_points


def _format_round(info: RoundInfo) -> str:
    counts = " ".join(f"P{seat}×{n}" for seat, n in info.per_player)
    line = f"第 {info.round} 轮: {counts}"
    if info.events:
        line += " | " + " ".join(info.events)
    return line


def round_summary(replay: Replay, db: CardDB | None = None) -> str:
    """按 round 分组的摘要: 每轮各玩家有效决策数 + 关键事件聚合.

    db 给定时经确定性重放补充时代切换/奇观完成/殖民地获得等状态级事件。
    """
    infos, _ = _analyze(replay, db)
    header = (f"回合摘要(有效决策 {len(replay.effective)}, "
              f"作废 {len(replay.voided)}):")
    lines = [header]
    lines.extend(_format_round(info) for info in infos)
    return "\n".join(lines)


def turning_points(replay: Replay, db: CardDB | None = None) -> tuple[str, ...]:
    """关键转折点: 首次侵略/首次宣战(动作层) + 时代切换/首个奇观完成(db 重放)."""
    _, points = _analyze(replay, db)
    return tuple(points)


def text_report(replay: Replay, db: CardDB | None = None) -> str:
    """完整文本战报: 元信息 + 终局结果 + 关键转折点 + 回合摘要.

    分节结构面向后续 LLM 复盘(可逐节标注)。
    """
    meta = replay.meta
    agents = meta.get("agents", [])
    players = meta.get("players", [])
    pairs = [f"{name}({agents[i]})" if i < len(agents) else name
             for i, name in enumerate(players)]
    lines = ["对局战报", "=" * 40, "[元信息]"]
    lines.append(f"seed: {meta.get('seed')}")
    lines.append(f"玩家: {', '.join(pairs)}")
    lines.append(f"引擎版本: {meta.get('engine_version', '(无记录)')}")
    lines.append("[终局]")
    if replay.result is None:
        lines.append("状态: 无终局记录(棋谱截断)")
    else:
        completed = replay.result.get("completed", True)
        lines.append(f"状态: {'已完成' if completed else '未完成(保存退出)'}")
        lines.append(f"轮次: {replay.result['rounds']}")
        scores = ", ".join(f"P{i}={s}"
                           for i, s in enumerate(replay.result["scores"]))
        lines.append(f"得分: {scores}")
        winners = replay.result["winners"]
        lines.append("胜者: " + (", ".join(f"P{w}" for w in winners)
                                 if winners else "(无)"))
    lines.append(f"有效决策: {len(replay.effective)}"
                 f"(作废 {len(replay.voided)})")
    infos, points = _analyze(replay, db)
    lines.append("[关键转折点]")
    if points:
        lines.extend(points)
    else:
        lines.append("(无)")
    lines.append("[回合摘要]")
    header = (f"回合摘要(有效决策 {len(replay.effective)}, "
              f"作废 {len(replay.voided)}):")
    lines.append(header)
    lines.extend(_format_round(info) for info in infos)
    return "\n".join(lines)
