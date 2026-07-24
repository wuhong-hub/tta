"""玩家抽象接口."""

from typing import Protocol

from tta.engine.actions import Action
from tta.engine.model import CardDB
from tta.engine.state import GameState


class Player(Protocol):
    """玩家协议: 面对状态与合法动作表, 返回一个动作."""

    def choose(self, state: GameState, legal: list[Action], db: CardDB) -> Action:
        """选择动作; 必须返回 legal 中的元素."""
        ...
