"""政治阶段动作与 SeedEvent 结算(P2-T5).

每回合限 1 政治行动: POLITICS 相位 legal = 政治动作 + SkipPolitics(见
legal.py), 任一政治动作结算后置 phase=ACTION(Julius Caesar 一次性双政治
T10)。侵略/战争/条约/退出动作类型已建(actions.py), 结算见 T8/T9/T10。

SeedEvent 结算(规则书 p4/p7):
1. 军事手牌中的 EVENT 卡面朝下压入 future_events 顶;
2. 揭示 current_events 顶牌(空 -> 无事发生):
   - TERRITORY -> 触发殖民竞拍(T7; 本任务占位 = 直接入 past_events);
   - 其余 -> events.resolve_event 查 EVENT_HANDLERS 结算;
3. 结算后该卡入 past_events;
4. 若揭示的是 current_events 最后一张: 重洗 future_events(按时代分组,
   早时代在上, 组内 rng_shuffle)成为新 current_events。
"""

from dataclasses import replace

from tta.engine import events
from tta.engine.actions import SeedEvent
from tta.engine.enums import Age, CardCategory, Phase
from tta.engine.model import CardDB
from tta.engine.rng import rng_shuffle
from tta.engine.state import GameState, replace_player

_AGE_ORDER = (Age.A, Age.I, Age.II, Age.III, Age.IV)
"""事件重洗分组的时代序(早时代在上)."""


def politics_actions(db: CardDB, state: GameState) -> list[SeedEvent]:
    """POLITICS 相位可用政治动作(不含 SkipPolitics, 由 legal 追加).

    当前仅 SeedEvent(军事手牌中的 EVENT 卡); 侵略/战争/条约动作 T8/T9/T10
    加入。RULES-CHECK(规则书 p4 未禁止): 时代 IV 无军事牌可抽, 但手牌中
    已有的事件牌仍可筹划。
    """
    p = state.players[state.current_player]
    return [
        SeedEvent(card_id)
        for card_id in dict.fromkeys(p.hand_military)
        if db.get(card_id).category is CardCategory.EVENT
    ]


def seed_event(db: CardDB, state: GameState, action: SeedEvent) -> GameState:
    """SeedEvent 结算: 筹划 -> 揭示 -> past_events -> (当前堆尽)重洗.

    结算后 phase=ACTION(每回合限 1 政治行动); 事件 handler 压入的 pending
    链在 ACTION 相位由 legal 的 pending 分支逐座位结算。
    """
    idx = state.current_player
    p = state.players[idx]
    hand = list(p.hand_military)
    hand.remove(action.card_id)
    state = replace_player(state, idx, replace(p, hand_military=tuple(hand)))
    # 1. 筹划卡面朝下压入 future_events 顶
    state = replace(
        state, future_events=(action.card_id,) + state.future_events)
    # 2. 揭示 current_events 顶牌; 空 -> 无事发生
    if not state.current_events:
        return replace(state, phase=Phase.ACTION)
    revealed = state.current_events[0]
    state = replace(state, current_events=state.current_events[1:])
    card = db.get(revealed)
    if card.category is not CardCategory.TERRITORY:
        state = events.resolve_event(state, db, revealed)
    # TERRITORY -> TODO(T7) 殖民竞拍; 占位 = 直接入 past_events
    # 3. 结算后该卡入 past_events
    state = replace(state, past_events=state.past_events + (revealed,))
    # 4. 揭示的是 current_events 最后一张 -> 重洗 future 成为新 current
    if not state.current_events and state.future_events:
        state = _reshuffle_future_events(db, state)
    return replace(state, phase=Phase.ACTION)


def _reshuffle_future_events(db: CardDB, state: GameState) -> GameState:
    """重洗 future_events 成为新 current_events: 按时代分组, 早时代在上,
    组内 rng_shuffle(消费 GameState.rng_state)."""
    groups: dict[Age, list[str]] = {}
    for card_id in state.future_events:
        groups.setdefault(db.get(card_id).age, []).append(card_id)
    rng = state.rng_state
    cards: list[str] = []
    for age in sorted(groups, key=_AGE_ORDER.index):
        rng, shuffled = rng_shuffle(rng, groups[age])
        cards.extend(shuffled)
    return replace(
        state, current_events=tuple(cards), future_events=(), rng_state=rng)
