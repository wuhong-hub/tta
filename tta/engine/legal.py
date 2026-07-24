"""合法动作生成: 引擎的规则门面."""

from tta.engine.actions import (
    Action,
    Build,
    Develop,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    TakeCard,
)
from tta.engine.constants import POP_FOOD_COST, ROW_COSTS
from tta.engine.enums import CATEGORY_TO_BUILDING, CardCategory
from tta.engine.model import CardDB
from tta.engine.state import GameState


def legal_actions(state: GameState, db: CardDB) -> list[Action]:
    """枚举当前玩家的全部合法动作; PassTurn 恒在且位于末尾."""
    if state.terminal:
        return []
    p = state.players[state.current_player]
    gov = db.get(p.government).government
    if gov is None:
        raise ValueError(f"current government {p.government} has no stats")

    actions: list[Action] = []

    # 拿牌: 白点付位置费用, 内政手牌不超上限
    if len(p.hand_civil) < gov.civil_hand_limit:
        for i, card_id in enumerate(state.card_row):
            if card_id is not None and p.civil_actions >= ROW_COSTS[i]:
                actions.append(TakeCard(i))

    # 研发 / 打行动卡
    for card_id in sorted(set(p.hand_civil)):
        card = db.get(card_id)
        if card.category is CardCategory.ACTION:
            if p.civil_actions >= 1:
                actions.append(PlayActionCard(card_id))
        elif card.category is CardCategory.GOVERNMENT:
            if p.science >= card.cost_science and p.civil_actions >= 1:
                actions.append(Develop(card_id))
        elif card.category is CardCategory.UNIT:
            if p.science >= card.cost_science and p.military_actions >= 1:
                actions.append(Develop(card_id))
        else:
            if p.science >= card.cost_science and p.civil_actions >= 1:
                actions.append(Develop(card_id))

    # 建造: 已研发副本数 > 已放置工人数; 兵种用红点
    for card_id in sorted(set(p.developed)):
        card = db.get(card_id)
        btype = CATEGORY_TO_BUILDING.get(card.category)
        if btype is None:
            continue
        placed = p.buildings.get(btype.value, {}).get(card_id, 0)
        if p.developed.count(card_id) <= placed:
            continue
        is_unit = card.category is CardCategory.UNIT
        has_action = p.military_actions >= 1 if is_unit else p.civil_actions >= 1
        slots = p.buildings.get(btype.value, {})
        # 工人来源: 空闲池, 或同类型异名建筑上的工人(升级); 同名卡互移无意义
        has_worker_source = p.worker_pool > 0 or any(
            n > 0 for cid, n in slots.items() if cid != card_id)
        if has_action and p.materials >= card.build_cost and has_worker_source:
            actions.append(Build(card_id))

    # 增加人口
    if p.civil_actions >= 1 and p.yellow_bank > 0 and p.food >= POP_FOOD_COST:
        actions.append(IncreasePopulation())

    actions.append(PassTurn())
    return actions
