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


class UndoRequest(Exception):
    """悔棋请求: 玩家(人类)要求回退到自己上一个决策点.

    由 Player.choose 抛出, runner 捕获后回退状态栈并重新询问;
    仅人类玩家使用(AI 决策不可悔, 见 runner.run_game)。
    """


class QuitGame(Exception):
    """保存退出请求: 玩家(人类)要求终止对局并保留棋谱.

    由 Player.choose 抛出, runner 捕获后写入未完成标记的 result
    (completed=False)并优雅返回。
    """
