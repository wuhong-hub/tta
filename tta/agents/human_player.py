"""人类玩家: 渲染 + 动作菜单交互(全部 IO 经注入的 input_fn/output_fn).

choose 流程: render_game 整屏 -> menu.prompt_action(菜单/参数引导/控制键)。
控制键 u/?/q 与 EOF 处理见 tta.ui.menu; 悔棋与保存退出的对局级支持见
orchestrator.runner。
"""

from collections.abc import Callable

from tta.engine import Action, CardDB, GameState
from tta.engine.state import acting_index
from tta.ui.menu import prompt_action
from tta.ui.render import render_game


class HumanPlayer:
    """命令行人类玩家(实现 agents.base.Player 协议)."""

    def __init__(self, input_fn: Callable[[str], str] = input,
                 output_fn: Callable[[str], None] = print) -> None:
        self._input = input_fn
        self._output = output_fn

    def choose(self, state: GameState, legal: list[Action], db: CardDB) -> Action:
        """渲染整屏与动作菜单, 循环读输入直到选出合法动作.

        Raises:
            UndoRequest: 玩家输入 u(runner 回退到其上一个决策点).
            QuitGame: 玩家输入 q 或 EOF/KeyboardInterrupt(保存退出).
        """
        self._output(render_game(state, db, seat=acting_index(state)))
        return prompt_action(state, legal, db, self._input, self._output)
