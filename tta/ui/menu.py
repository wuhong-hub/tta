"""动作菜单与参数询问: 全部 IO 经注入的 input_fn/output_fn(脚本化可测试).

菜单编号口径 = render.ordered_actions(分组重排, 与 render_actions 一致)。
控制键: u=悔棋(抛 UndoRequest), ?=重显整屏, q=保存退出(抛 QuitGame);
EOF/KeyboardInterrupt 一律按 q 处理(递归子菜单同理, 直接终止对局)。

参数化动作子菜单(输入数字选中动作后触发):
- BuildWonderStage: legal 含多个阶段数时询问建造阶段数;
- PlayActionCard: 同卡多 option 时询问选项;
- ProposePact: 同(卡, 目标)多侧别时询问侧别;
- ColonizeSacrifice: 直接执行枚举组合, 或自定义逐张选单位直至军力达标
  (显示累计/需求; 组合可不在 legal 中, 由 apply 自校验闸口放行)。
ChooseEventOption/ChooseTurnStart/ColonizeBid 等参数已逐项枚举入主菜单,
无需子菜单。
"""

from collections.abc import Callable

from tta.agents.base import QuitGame, UndoRequest
from tta.engine import (
    UNIT_CATEGORIES,
    Action,
    BuildWonderStage,
    CardDB,
    ColonizeSacrifice,
    GameState,
    PlayActionCard,
    PlayerState,
    ProposePact,
    civ_values,
    military,
    politics,
)
from tta.engine.state import acting_index
from tta.ui.render import describe_action, ordered_actions, render_actions, render_game

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]

_MENU_PROMPT = "选择动作编号 (u=悔棋 ?=重显 q=退出): "
_CANCEL_HINT = "c=取消"


def read_line(prompt: str, input_fn: InputFn) -> str:
    """读一行输入; EOF/KeyboardInterrupt 按 q(保存退出)处理."""
    try:
        return input_fn(prompt).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise QuitGame from exc


def parse_menu_input(text: str, count: int) -> int | str | None:
    """解析菜单输入.

    Returns:
        int: 合法编号的 0 基索引;
        str: 控制键 "u" / "?" / "q";
        None: 非法输入.
    """
    token = text.strip().lower()
    if token in ("u", "?", "q"):
        return token
    if token.isdigit():
        index = int(token)
        if 1 <= index <= count:
            return index - 1
    return None


def prompt_action(state: GameState, legal: list[Action], db: CardDB,
                  input_fn: InputFn, output_fn: OutputFn) -> Action:
    """动作菜单主循环: 渲染菜单 -> 读编号 -> 参数引导 -> 返回动作.

    Raises:
        UndoRequest: 输入 u(悔棋).
        QuitGame: 输入 q 或 EOF/KeyboardInterrupt(保存退出).
    """
    ordered = ordered_actions(legal)
    output_fn(render_actions(legal, db))
    while True:
        parsed = parse_menu_input(read_line(_MENU_PROMPT, input_fn),
                                  len(ordered))
        if parsed == "u":
            raise UndoRequest
        if parsed == "q":
            raise QuitGame
        if parsed == "?":
            output_fn(render_game(state, db, seat=acting_index(state)))
            output_fn(render_actions(legal, db))
            continue
        if parsed is None:
            output_fn(f"无效输入, 请输入 1..{len(ordered)} 或 u/?/q")
            continue
        resolved = resolve_parameters(
            ordered[parsed], state, legal, db, input_fn, output_fn)
        if resolved is not None:
            return resolved
        output_fn(render_actions(legal, db))


def resolve_parameters(action: Action, state: GameState, legal: list[Action],
                       db: CardDB, input_fn: InputFn,
                       output_fn: OutputFn) -> Action | None:
    """参数化动作的参数引导; 无需参数时原样返回.

    Returns:
        补全参数后的动作; None 表示用户取消(返回主菜单).
    """
    if isinstance(action, ColonizeSacrifice):
        return _resolve_sacrifice(action, state, db, input_fn, output_fn)
    variants = _param_variants(action, legal)
    if len(variants) <= 1:
        return action
    return _pick_variant(variants, db, input_fn, output_fn)


def _param_variants(action: Action, legal: list[Action]) -> list[Action]:
    """同族参数变体(仅 BuildWonderStage/PlayActionCard/ProposePact 有多值参数)."""
    if isinstance(action, BuildWonderStage):
        counts = sorted({
            a.count for a in legal if isinstance(a, BuildWonderStage)})
        return [BuildWonderStage(c) for c in counts]
    if isinstance(action, PlayActionCard):
        return [a for a in legal
                if isinstance(a, PlayActionCard) and a.card_id == action.card_id]
    if isinstance(action, ProposePact):
        return [a for a in legal
                if isinstance(a, ProposePact)
                and a.card_id == action.card_id and a.target == action.target]
    return [action]


def _pick_variant(variants: list[Action], db: CardDB, input_fn: InputFn,
                  output_fn: OutputFn) -> Action | None:
    """参数变体子菜单: 编号选择, c 取消."""
    output_fn("参数选择:")
    for i, variant in enumerate(variants, start=1):
        output_fn(f"  {i}. {describe_action(variant, db)}")
    while True:
        line = read_line(f"选择 1..{len(variants)} ({_CANCEL_HINT}): ",
                         input_fn)
        if line.lower() == "c":
            return None
        parsed = parse_menu_input(line, len(variants))
        if isinstance(parsed, int):
            return variants[parsed]
        output_fn(f"无效输入, 请输入 1..{len(variants)} 或 c")


def _resolve_sacrifice(action: ColonizeSacrifice, state: GameState,
                       db: CardDB, input_fn: InputFn,
                       output_fn: OutputFn) -> Action | None:
    """殖民牺牲: 1=直接执行枚举组合, 2=自定义选单位, c=取消."""
    output_fn(f"所选组合: {describe_action(action, db)}")
    output_fn("  1. 直接执行该组合")
    output_fn("  2. 自定义选择单位")
    while True:
        line = read_line(f"选择 1..2 ({_CANCEL_HINT}): ", input_fn)
        if line.lower() == "c":
            return None
        if line == "1":
            return action
        if line == "2":
            seat = acting_index(state)
            need = _sacrifice_need(db, state, seat)
            return prompt_sacrifice(db, state.players[seat], need,
                                    input_fn, output_fn)
        output_fn("无效输入, 请输入 1/2 或 c")


def _sacrifice_need(db: CardDB, state: GameState, seat: int) -> int:
    """履约还缺的单位军力 = 出价 - 殖民修正 - 已出奖励(无 pending 时保守取 1)."""
    if state.pending and state.pending[0].kind == politics.KIND_COLONIZE_SACRIFICE:
        context = state.pending[0].context
        bid = int(context.get("bid", 1))
        bonus = int(context.get("bonus", 0))
        player = state.players[seat]
        fixed = civ_values(db, player, state.players, seat).colonization + bonus
        return max(1, bid - fixed)
    return 1


def _unit_copies(p: PlayerState) -> list[str]:
    """全部军事单位按份展开(顺序与 legal._colonize_sacrifice_actions 一致)."""
    return [
        card_id
        for category in sorted(UNIT_CATEGORIES, key=lambda c: c.value)
        for card_id, workers in sorted(p.buildings.get(category.value, {}).items())
        for _ in range(workers)
    ]


def prompt_sacrifice(db: CardDB, p: PlayerState, need: int,
                     input_fn: InputFn,
                     output_fn: OutputFn) -> ColonizeSacrifice | None:
    """自定义牺牲选择: 逗号分隔编号逐批添加, 累计军力达标即确认.

    每行输入中: 非法编号整行作废并提示; 重复编号忽略; c 取消(返回 None)。
    """
    units = _unit_copies(p)
    output_fn(f"可选军事单位(需求军力 {need}):")
    for i, card_id in enumerate(units, start=1):
        card = db.get(card_id)
        output_fn(f"  {i}. {card.name}(军力{card.strength})")
    selected: list[int] = []
    while True:
        chosen = tuple(units[i] for i in selected)
        strength = military.units_strength(db, p, chosen) if chosen else 0
        if selected and strength >= need:
            return ColonizeSacrifice(chosen)
        line = read_line(
            f"牺牲单位编号(累计{strength}/需{need}, 逗号分隔, "
            f"{_CANCEL_HINT}): ", input_fn)
        if line.lower() == "c":
            return None
        indices: list[int] = []
        valid = True
        for token in line.split(","):
            token = token.strip()
            if not token.isdigit() or not 1 <= int(token) <= len(units):
                valid = False
                break
            index = int(token) - 1
            if index not in selected and index not in indices:
                indices.append(index)
        if not valid or not indices:
            output_fn(f"无效输入, 请输入 1..{len(units)} 的编号(逗号分隔)或 c")
            continue
        selected.extend(indices)
