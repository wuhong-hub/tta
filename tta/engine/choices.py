"""回合开始选择机制(P3-T4)与 winston_churchill 领袖钩子.

回合开始阶段(turn.proceed: 补牌 -> 战争结算 -> 公开阵型之后, phase 置
POLITICS 之前)检查当前玩家领袖/效果中需要"每回合选择"的(当前仅
winston_churchill), 压入 kind="turn_start_choice" 的 pending
(responder=None 即自己, context={"source": 卡 id}), phase 保持
TURN_START 直至 ChooseTurnStart 结算完毕再落入 POLITICS。

该 pending 为强制二选一(Churchill 卡牌文本 "choose one"), 不在
DECLINABLE_PENDING_KINDS 白名单, 不可 DeclineResponse; 未来出现可选
(可放弃)的回合开始效果时再开放白名单。

bill_gates 的实验室产资源见 economy(produce/resource_total 的 LAB 口径),
被替换离场即时奖励见 effects.gates_lab_bonus_culture 与
apply._play_leader(终局奖励已在 P2-T12 实现, 见
events._bill_gates_endgame)。

engine 包不得 import tta.cards, 领袖卡 id 引用 effects 的字符串常量。
"""

from dataclasses import replace

from tta.engine import effects
from tta.engine.actions import IllegalActionError
from tta.engine.enums import Phase
from tta.engine.model import CardDB
from tta.engine.state import (
    GameState,
    PendingEffect,
    PlayerState,
    acting_index,
    replace_player,
)

KIND_TURN_START_CHOICE = "turn_start_choice"
"""回合开始选择 pending(turn.proceed 压入; 强制, 不可 DeclineResponse)."""

CHURCHILL_OPTION_CULTURE = "culture"
CHURCHILL_OPTION_MILITARY = "military"
CHURCHILL_CULTURE = 3
"""churchill "culture" 选项: +3 文化(PDF 第 2 页)."""

CHURCHILL_MILITARY_SCIENCE = 3
"""churchill "military" 选项的科技部分: +3 科技."""

CHURCHILL_MILITARY_RESOURCE = 3
"""churchill "military" 选项的资源部分: 本回合军事建造折扣 3.

实现为 turn_discounts["unit_build"] += 3(与 homer/patriotism 的军事建造
折扣同键叠加, 回合末行动点恢复时重置; "3 资源军事用本回合"的引擎口径为
建造/升级兵种的费用折扣, 与 patriotism 行动卡一致)。
"""

_CHURCHILL_OPTIONS = (CHURCHILL_OPTION_CULTURE, CHURCHILL_OPTION_MILITARY)


def turn_start_choice_pending(db: CardDB, state: GameState) -> PendingEffect | None:
    """当前玩家需要回合开始选择时返回待压入的 pending, 否则 None.

    当前仅 winston_churchill(每回合二选一); responder=None 即由
    current_player 自己响应, context 记录来源卡 id 供选项枚举与结算。
    """
    p = state.players[state.current_player]
    if p.leader == effects.LEADER_CHURCHILL:
        return PendingEffect(
            KIND_TURN_START_CHOICE, 0, context={"source": p.leader})
    return None


def turn_start_options(pending: PendingEffect) -> tuple[str, ...]:
    """turn_start_choice pending 的合法选项(按 context 来源卡)."""
    if pending.context.get("source") == effects.LEADER_CHURCHILL:
        return _CHURCHILL_OPTIONS
    return ()


def apply_turn_start_choice(
    db: CardDB, state: GameState, option: str,
) -> GameState:
    """结算 ChooseTurnStart: 应用选项效果, pop pending, phase 落入 POLITICS.

    相位口径与 turn.proceed 一致(round==1 直接 ACTION; 防御性分支——
    第一回合无领袖可用, 正常流程不可达)。
    """
    if option not in turn_start_options(state.pending[0]):
        msg = f"非法回合开始选项: {option!r}"
        raise IllegalActionError(msg)
    idx = acting_index(state)
    p = state.players[idx]
    state = replace(state, pending=state.pending[1:])
    if state.players[idx].leader == effects.LEADER_CHURCHILL:
        p = _apply_churchill(p, option)
    state = replace_player(state, idx, p)
    phase = Phase.ACTION if state.round == 1 else Phase.POLITICS
    return replace(state, phase=phase)


def _apply_churchill(p: PlayerState, option: str) -> PlayerState:
    """churchill 二选一结算: +3 文化; 或 +3 科技 + 本回合军事建造折扣 3."""
    if option == CHURCHILL_OPTION_CULTURE:
        return replace(p, culture=p.culture + CHURCHILL_CULTURE)
    discounts = dict(p.turn_discounts)
    key = effects.UNIT_BUILD_DISCOUNT_KEY
    discounts[key] = discounts.get(key, 0) + CHURCHILL_MILITARY_RESOURCE
    return replace(
        p, science=p.science + CHURCHILL_MILITARY_SCIENCE,
        turn_discounts=discounts)
