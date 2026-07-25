"""随机玩家: 基线与引擎模糊测试用."""

import random

from tta.engine.actions import Action, Resign
from tta.engine.model import CardDB
from tta.engine.state import GameState


class RandomPlayer:
    """均匀随机选择合法动作.

    基线策略不主动体面退出(Resign 每回合政治阶段均合法, 均匀随机会以
    高概率提前终局, 丧失对局中后段的回归覆盖; 退出机制由
    tests/engine/test_pacts.py 专项覆盖)。
    """

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def choose(self, state: GameState, legal: list[Action], db: CardDB) -> Action:
        """从合法动作中均匀随机选一个(有其他选择时不选 Resign)."""
        choices = [a for a in legal if not isinstance(a, Resign)]
        return self._rng.choice(choices or legal)
