"""命令行入口: tta selfplay / tta replay."""

import argparse
import json
import sys
from pathlib import Path

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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
