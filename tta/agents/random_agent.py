"""随机玩家: 基线与引擎模糊测试用."""

import random

from tta.engine.actions import Action
from tta.engine.model import CardDB
from tta.engine.state import GameState


class RandomPlayer:
    """均匀随机选择合法动作."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def choose(self, state: GameState, legal: list[Action], db: CardDB) -> Action:
        """从合法动作中均匀随机选一个."""
        return self._rng.choice(legal)
