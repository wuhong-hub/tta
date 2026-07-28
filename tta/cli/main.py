"""命令行入口: tta selfplay / tta replay / tta play."""

import argparse
import sys
from pathlib import Path

from tta.agents.human_player import HumanPlayer
from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.orchestrator.runner import run_game
from tta.replay.recorder import ReplayRecorder, current_engine_version
from tta.replay.report import (
    ReplayMismatchError,
    parse_replay,
    replay_to_state,
    text_report,
)
from tta.ui.render import render_game


def _cmd_selfplay(args: argparse.Namespace) -> int:
    out = Path(args.out)
    db = build_card_db()
    for g in range(args.games):
        seed = args.seed + g
        players = [RandomPlayer(seed=seed * 100 + i) for i in range(args.players)]
        path = out / f"selfplay_seed{seed}_game{g}.jsonl"
        with ReplayRecorder(path) as rec:
            result = run_game(db, players, seed=seed, recorder=rec)
        print(f"game {g}: seed={seed} rounds={result.rounds} "
              f"scores={list(result.scores)} winner={list(result.winners)} "
              f"-> {path}")
    return 0


def _cmd_play(args: argparse.Namespace) -> int:
    total = args.ai + 1
    if not 0 <= args.seat < total:
        print(f"座位越界: --seat {args.seat} (共 {total} 人, 合法 0..{total - 1})")
        return 2
    out = Path(args.out)
    db = build_card_db()
    players: list = [RandomPlayer(seed=args.seed * 100 + i) for i in range(total)]
    players[args.seat] = HumanPlayer()
    path = out / f"play_seed{args.seed}_seat{args.seat}.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(db, players, seed=args.seed, recorder=rec)
    if result.completed:
        print(f"对局结束: rounds={result.rounds} "
              f"scores={list(result.scores)} winner={list(result.winners)} "
              f"-> {path}")
    else:
        print(f"对局未完成(已保存): rounds={result.rounds} "
              f"scores={list(result.scores)} -> {path}")
    return 0


def _warn_version(meta: dict) -> None:
    """棋谱引擎版本与当前不符时打印警告(stderr), 不阻止回放."""
    recorded = meta.get("engine_version")
    current = current_engine_version()
    if recorded is None:
        print("警告: 棋谱无引擎版本信息, 重放结果可能与录制时不一致",
              file=sys.stderr)
    elif recorded != current:
        print(f"警告: 棋谱引擎版本 {recorded} 与当前 {current} 不符, "
              "重放轨迹可能偏离记录", file=sys.stderr)


def _cmd_replay(args: argparse.Namespace) -> int:
    replay = parse_replay(Path(args.file))
    _warn_version(replay.meta)
    if args.report:
        print(text_report(replay, db=build_card_db()))
        return 0
    if args.turn is not None:
        db = build_card_db()
        try:
            state = replay_to_state(replay, db, args.turn)
        except (ValueError, ReplayMismatchError) as exc:
            print(f"跳转失败: {exc}", file=sys.stderr)
            return 2
        seat = (args.seat if args.seat is not None
                else replay.effective[args.turn - 1].player)
        print(f"第 {args.turn} 个有效决策前的盘面(P{seat} 视角):")
        print(render_game(state, db, seat))
        return 0
    meta = replay.meta
    result = replay.result
    print(f"seed: {meta['seed']}, players: {meta['players']}")
    print(f"decisions: {len(replay.effective)} effective "
          f"({len(replay.voided)} voided)")
    if result is None:
        print("result: (无终局记录)")
    else:
        print(f"rounds: {result['rounds']}, scores: {result['scores']}, "
              f"winners: {result['winners']}"
              f"{'' if result.get('completed', True) else ' (未完成)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口."""
    parser = argparse.ArgumentParser(prog="tta")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("selfplay", help="随机/AI 玩家自我对弈")
    sp.add_argument("--players", type=int, default=2, choices=[2, 3, 4])
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--games", type=int, default=1)
    sp.add_argument("--out", default="replays")
    sp.set_defaults(func=_cmd_selfplay)

    rp = sub.add_parser("replay", help="查看棋谱摘要/指定手跳转/文本战报")
    rp.add_argument("file")
    rp.add_argument("--turn", type=int, default=None,
                    help="重放到第 N 个有效决策前的盘面并渲染")
    rp.add_argument("--seat", type=int, default=None,
                    help="--turn 渲染视角(默认取该决策的行动者)")
    rp.add_argument("--report", action="store_true",
                    help="输出完整文本战报(回合摘要+终局+关键转折点)")
    rp.set_defaults(func=_cmd_replay)

    pp = sub.add_parser("play", help="人机对局(人类坐 --seat, 其余为随机 AI)")
    pp.add_argument("--seat", type=int, default=0)
    pp.add_argument("--ai", type=int, default=2, choices=[1, 2, 3],
                    help="AI 对手数(总人数 = ai + 1)")
    pp.add_argument("--seed", type=int, default=42)
    pp.add_argument("--out", default="replays")
    pp.set_defaults(func=_cmd_play)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
