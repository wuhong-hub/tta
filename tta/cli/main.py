"""命令行入口: tta selfplay / tta replay / tta play."""

import argparse
import json
import sys
from pathlib import Path

from tta.agents.human_player import HumanPlayer
from tta.agents.random_agent import RandomPlayer
from tta.cards import build_card_db
from tta.orchestrator.runner import run_game
from tta.replay.recorder import ReplayRecorder


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


def _cmd_replay(args: argparse.Namespace) -> int:
    lines = [json.loads(x) for x in Path(args.file).read_text().splitlines()]
    meta = next(x for x in lines if x["type"] == "meta")
    result = next(x for x in lines if x["type"] == "result")
    decisions = sum(1 for x in lines if x["type"] == "decision")
    print(f"seed: {meta['seed']}, players: {meta['players']}")
    print(f"decisions: {decisions}, rounds: {result['rounds']}, "
          f"scores: {result['scores']}, winners: {result['winners']}")
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

    rp = sub.add_parser("replay", help="查看棋谱摘要")
    rp.add_argument("file")
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
