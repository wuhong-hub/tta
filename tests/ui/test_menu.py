"""动作菜单测试: 输入解析、主循环控制键、参数化动作子菜单(脚本化输入)."""

from dataclasses import replace

import pytest

from tta.agents.base import QuitGame, UndoRequest
from tta.cards import build_card_db
from tta.engine import (
    BuildWonderStage,
    ColonizeSacrifice,
    PassTurn,
    PlayActionCard,
    PlayerState,
    ProposePact,
    legal_actions,
    new_game,
)
from tta.ui.menu import (
    parse_menu_input,
    prompt_action,
    prompt_sacrifice,
    resolve_parameters,
)
from tta.ui.render import render_actions


@pytest.fixture(scope="module")
def db():
    return build_card_db()


class _Script:
    """脚本化 input/output: 输入按队列弹出, 输出累积成文本."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.out: list[str] = []

    def input(self, prompt: str = "") -> str:
        if prompt:
            self.out.append(prompt)
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)

    def output(self, text: str = "") -> None:
        self.out.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self.out)


# --- parse_menu_input ---------------------------------------------------------


def test_parse_digit() -> None:
    assert parse_menu_input("1", 5) == 0
    assert parse_menu_input(" 3 ", 5) == 2
    assert parse_menu_input("5", 5) == 4


def test_parse_digit_out_of_range() -> None:
    assert parse_menu_input("0", 5) is None
    assert parse_menu_input("6", 5) is None
    assert parse_menu_input("-1", 5) is None


def test_parse_control_tokens() -> None:
    assert parse_menu_input("u", 5) == "u"
    assert parse_menu_input(" U ", 5) == "u"
    assert parse_menu_input("?", 5) == "?"
    assert parse_menu_input("q", 5) == "q"
    assert parse_menu_input("Q", 5) == "q"


def test_parse_invalid() -> None:
    assert parse_menu_input("", 5) is None
    assert parse_menu_input("abc", 5) is None
    assert parse_menu_input("1.5", 5) is None
    assert parse_menu_input("1,2", 5) is None


# --- prompt_action 主循环 ------------------------------------------------------


def test_prompt_action_pick_by_number(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["2"])
    action = prompt_action(state, legal, db, script.input, script.output)
    assert action == legal[1]


def test_prompt_action_invalid_then_valid(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["xyz", "99", "1"])
    action = prompt_action(state, legal, db, script.input, script.output)
    assert action == legal[0]
    assert "无效" in script.text


def test_prompt_action_help_reprints_menu(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["?", "1"])
    action = prompt_action(state, legal, db, script.input, script.output)
    assert action == legal[0]
    assert script.text.count("可用动作") >= 1
    assert "时代" in script.text  # 重新渲染整屏


def test_prompt_action_quit(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["q"])
    with pytest.raises(QuitGame):
        prompt_action(state, legal, db, script.input, script.output)


def test_prompt_action_undo(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script(["u"])
    with pytest.raises(UndoRequest):
        prompt_action(state, legal, db, script.input, script.output)


def test_prompt_action_eof_treated_as_quit(db) -> None:
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    script = _Script([])  # 立即 EOF
    with pytest.raises(QuitGame):
        prompt_action(state, legal, db, script.input, script.output)


def test_prompt_action_menu_numbering_matches_render(db) -> None:
    """菜单编号口径与 render_actions 一致: 分组后连续编号映射回 legal 顺序."""
    state = new_game(db, 2, 42)
    legal = legal_actions(db, state)
    for n in range(1, len(legal) + 1):
        script = _Script([str(n)])
        action = prompt_action(state, legal, db, script.input, script.output)
        assert action in legal
    # 编号 1 恒为 legal[0](分组内保持 legal 相对顺序, 首组首项)
    assert "1." in render_actions(legal, db)


# --- BuildWonderStage 阶段数子菜单 ---------------------------------------------


def test_resolve_wonder_stage_count(db) -> None:
    state = new_game(db, 2, 42)
    legal = [BuildWonderStage(1), BuildWonderStage(2), BuildWonderStage(3)]
    script = _Script(["3"])
    action = resolve_parameters(
        BuildWonderStage(2), state, legal, db, script.input, script.output)
    assert action == BuildWonderStage(3)


def test_resolve_wonder_stage_invalid_then_valid(db) -> None:
    state = new_game(db, 2, 42)
    legal = [BuildWonderStage(1), BuildWonderStage(2)]
    script = _Script(["9", "1"])
    action = resolve_parameters(
        BuildWonderStage(1), state, legal, db, script.input, script.output)
    assert action == BuildWonderStage(1)
    assert "无效" in script.text


def test_resolve_wonder_stage_cancel(db) -> None:
    state = new_game(db, 2, 42)
    legal = [BuildWonderStage(1), BuildWonderStage(2)]
    script = _Script(["c"])
    assert resolve_parameters(
        BuildWonderStage(1), state, legal, db,
        script.input, script.output) is None


def test_resolve_wonder_stage_single_count_no_prompt(db) -> None:
    """只有一种可选阶段数时不询问, 直接返回."""
    state = new_game(db, 2, 42)
    legal = [BuildWonderStage(1), PassTurn()]
    script = _Script([])
    action = resolve_parameters(
        BuildWonderStage(1), state, legal, db, script.input, script.output)
    assert action == BuildWonderStage(1)


# --- PlayActionCard 选项子菜单 -------------------------------------------------


def test_resolve_action_card_option(db) -> None:
    state = new_game(db, 2, 42)
    legal = [
        PlayActionCard("reserves_i", "resource"),
        PlayActionCard("reserves_i", "food"),
        PassTurn(),
    ]
    script = _Script(["2"])
    action = resolve_parameters(
        PlayActionCard("reserves_i", "resource"), state, legal, db,
        script.input, script.output)
    assert action == PlayActionCard("reserves_i", "food")


def test_resolve_action_card_single_option_no_prompt(db) -> None:
    state = new_game(db, 2, 42)
    legal = [PlayActionCard("reserves_i", "food"), PassTurn()]
    script = _Script([])
    action = resolve_parameters(
        PlayActionCard("reserves_i", "food"), state, legal, db,
        script.input, script.output)
    assert action == PlayActionCard("reserves_i", "food")


# --- ProposePact 侧别子菜单 ----------------------------------------------------


def test_resolve_pact_side(db) -> None:
    state = new_game(db, 3, 42)
    legal = [
        ProposePact("trade_routes_agreement", 1, "A"),
        ProposePact("trade_routes_agreement", 1, "B"),
        PassTurn(),
    ]
    script = _Script(["2"])
    action = resolve_parameters(
        ProposePact("trade_routes_agreement", 1, "A"), state, legal, db,
        script.input, script.output)
    assert action == ProposePact("trade_routes_agreement", 1, "B")


def test_resolve_pact_single_side_no_prompt(db) -> None:
    state = new_game(db, 3, 42)
    legal = [ProposePact("trade_routes_agreement", 1, "A"), PassTurn()]
    script = _Script([])
    action = resolve_parameters(
        ProposePact("trade_routes_agreement", 1, "A"), state, legal, db,
        script.input, script.output)
    assert action == ProposePact("trade_routes_agreement", 1, "A")


# --- ColonizeSacrifice 牺牲引导 -------------------------------------------------


def _unit_player() -> PlayerState:
    """2 个武士(步兵, 各军力 1)的合成玩家(无阵型, 基础军力口径)."""
    return PlayerState(
        name="P0", buildings={"infantry": {"warriors": 2}})


def test_sacrifice_comma_separated(db) -> None:
    script = _Script(["1,2"])
    action = prompt_sacrifice(db, _unit_player(), need=2,
                              input_fn=script.input, output_fn=script.output)
    assert action == ColonizeSacrifice(("warriors", "warriors"))
    assert "累计" in script.text


def test_sacrifice_accumulates_until_enough(db) -> None:
    """分多次选择, 累计军力达标后自动确认."""
    script = _Script(["1", "2"])
    action = prompt_sacrifice(db, _unit_player(), need=2,
                              input_fn=script.input, output_fn=script.output)
    assert action == ColonizeSacrifice(("warriors", "warriors"))


def test_sacrifice_invalid_retry_and_no_duplicates(db) -> None:
    script = _Script(["x", "1,1", "2"])
    action = prompt_sacrifice(db, _unit_player(), need=2,
                              input_fn=script.input, output_fn=script.output)
    assert action == ColonizeSacrifice(("warriors", "warriors"))
    assert "无效" in script.text


def test_sacrifice_cancel(db) -> None:
    script = _Script(["c"])
    assert prompt_sacrifice(db, _unit_player(), need=2,
                            input_fn=script.input,
                            output_fn=script.output) is None


def test_sacrifice_insufficient_units_never_confirms(db) -> None:
    """军力永远不够时持续询问直至取消."""
    script = _Script(["1,2", "c"])
    assert prompt_sacrifice(db, _unit_player(), need=5,
                            input_fn=script.input,
                            output_fn=script.output) is None


def test_resolve_sacrifice_direct_or_custom(db) -> None:
    """选中枚举组合: 1=直接执行, 2=进入自定义选择."""
    state = new_game(db, 2, 42)
    player = _unit_player()
    state = replace(state, players=(player, state.players[1]))
    anchor = ColonizeSacrifice(("warriors", "warriors"))
    legal = [anchor, PassTurn()]
    direct = _Script(["1"])
    assert resolve_parameters(anchor, state, legal, db,
                              direct.input, direct.output) == anchor
    # 自定义: 只选 1 个武士(need 由 state pending 提供, 无 pending 时按 1)
    custom = _Script(["2", "1"])
    action = resolve_parameters(anchor, state, legal, db,
                                custom.input, custom.output)
    assert action == ColonizeSacrifice(("warriors",))
