"""动作结算: apply(state, action, db) -> 新状态."""

from dataclasses import replace

from tta.engine.actions import (
    Action,
    Build,
    Develop,
    IllegalActionError,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    TakeCard,
)
from tta.engine.constants import (
    BASE_HAPPINESS,
    FOOD_PER_WORKER,
    POP_FOOD_COST,
    ROW_COSTS,
    ROW_SLOTS,
    STARVATION_CULTURE,
)
from tta.engine.enums import CATEGORY_TO_BUILDING, Age, BuildingType, CardCategory
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB
from tta.engine.state import (
    GameState,
    PlayerState,
    replace_player,
    workers_total,
)


def apply(state: GameState, action: Action, db: CardDB) -> GameState:
    """校验并结算一个动作, 返回新状态; 非法动作抛 IllegalActionError."""
    if state.terminal:
        raise IllegalActionError("game is over")
    if action not in legal_actions(state, db):
        raise IllegalActionError(f"illegal action: {action!r}")
    idx = state.current_player
    p = state.players[idx]
    if isinstance(action, TakeCard):
        return _take_card(state, idx, p, action)
    if isinstance(action, Develop):
        return _develop(state, idx, p, action, db)
    if isinstance(action, Build):
        return _build(state, idx, p, action, db)
    if isinstance(action, IncreasePopulation):
        return _increase_population(state, idx, p)
    if isinstance(action, PlayActionCard):
        return _play_action_card(state, idx, p, action, db)
    if isinstance(action, PassTurn):
        return _end_turn(state, db)
    raise IllegalActionError(f"unknown action: {action!r}")


def _take_card(state: GameState, idx: int, p: PlayerState, a: TakeCard) -> GameState:
    card_id = state.card_row[a.row_index]
    if card_id is None:
        raise IllegalActionError("empty row slot")
    row = list(state.card_row)
    row[a.row_index] = None
    p = replace(p, civil_actions=p.civil_actions - ROW_COSTS[a.row_index],
                hand_civil=p.hand_civil + (card_id,))
    return replace_player(replace(state, card_row=tuple(row)), idx, p)


def _develop(state: GameState, idx: int, p: PlayerState, a: Develop,
             db: CardDB) -> GameState:
    card = db.get(a.card_id)
    hand = list(p.hand_civil)
    hand.remove(a.card_id)
    p = replace(p, science=p.science - card.cost_science,
                hand_civil=tuple(hand))
    if card.category is CardCategory.GOVERNMENT:
        old = p.government
        p = replace(p, civil_actions=p.civil_actions - 1, government=a.card_id)
        state = replace(state, discard=state.discard + (old,))
        return replace_player(state, idx, p)
    if card.category is CardCategory.UNIT:
        p = replace(p, military_actions=p.military_actions - 1)
    else:
        p = replace(p, civil_actions=p.civil_actions - 1)
    p = replace(p, developed=p.developed + (a.card_id,))
    return replace_player(state, idx, p)


def _build(state: GameState, idx: int, p: PlayerState, a: Build,
           db: CardDB) -> GameState:
    card = db.get(a.card_id)
    btype = CATEGORY_TO_BUILDING[card.category].value
    if card.category is CardCategory.UNIT:
        p = replace(p, military_actions=p.military_actions - 1)
    else:
        p = replace(p, civil_actions=p.civil_actions - 1)
    p = replace(p, materials=p.materials - card.build_cost)

    buildings = {k: dict(v) for k, v in p.buildings.items()}
    slots = buildings.setdefault(btype, {})
    # RULES-AUDIT: 工人来源确定性选择——同类型异名建筑中时代最小、id 最小者;
    # 无升级来源时从空闲池取(legal_actions 已保证二者必有其一)
    sources = sorted(
        (cid for cid, n in slots.items() if n > 0 and cid != a.card_id),
        key=lambda cid: (list(Age).index(db.get(cid).age), cid),
    )
    if sources:
        src = sources[0]
        slots[src] -= 1
        if slots[src] == 0:
            del slots[src]
    else:
        p = replace(p, worker_pool=p.worker_pool - 1)
    slots[a.card_id] = slots.get(a.card_id, 0) + 1
    p = replace(p, buildings=buildings)
    return replace_player(state, idx, p)


def _increase_population(state: GameState, idx: int, p: PlayerState) -> GameState:
    p = replace(p, civil_actions=p.civil_actions - 1,
                food=p.food - POP_FOOD_COST,
                yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1)
    return replace_player(state, idx, p)


def _play_action_card(state: GameState, idx: int, p: PlayerState,
                      a: PlayActionCard, db: CardDB) -> GameState:
    card = db.get(a.card_id)
    hand = list(p.hand_civil)
    hand.remove(a.card_id)
    p = replace(p, civil_actions=p.civil_actions - 1, hand_civil=tuple(hand),
                food=p.food + card.gains.get("food", 0),
                materials=p.materials + card.gains.get("materials", 0),
                science=p.science + card.gains.get("science", 0),
                culture=p.culture + card.gains.get("culture", 0))
    return replace_player(replace(state, discard=state.discard + (a.card_id,)), idx, p)


def happiness(db: CardDB, p: PlayerState) -> int:
    """满意容量 = 基础值 + 神庙类建筑产出."""
    total = BASE_HAPPINESS
    for cid, n in p.buildings.get(BuildingType.TEMPLE.value, {}).items():
        total += db.get(cid).produces.get("happiness", 0) * n
    return total


def strength(db: CardDB, p: PlayerState) -> int:
    """军力 = 兵种建筑产出之和(P0 无战术/领袖加成)."""
    total = 0
    for cid, n in p.buildings.get(BuildingType.UNIT.value, {}).items():
        total += db.get(cid).produces.get("strength", 0) * n
    return total


def _produce(p: PlayerState, db: CardDB, btype: BuildingType, key: str) -> int:
    return sum(db.get(cid).produces.get(key, 0) * n
               for cid, n in p.buildings.get(btype.value, {}).items())


def _settle(p: PlayerState, db: CardDB) -> PlayerState:
    """回合末: 起义判定 -> 生产 -> 食物消耗/饥荒."""
    if p.worker_pool > happiness(db, p):
        return p  # RULES-AUDIT: 起义则本回合无生产
    p = replace(p,
                food=p.food + _produce(p, db, BuildingType.FARM, "food"),
                materials=p.materials + _produce(p, db, BuildingType.MINE, "materials"),
                science=p.science + _produce(p, db, BuildingType.LAB, "science"),
                culture=p.culture + _produce(p, db, BuildingType.TEMPLE, "culture"))
    need = FOOD_PER_WORKER * workers_total(p)
    if p.food >= need:
        return replace(p, food=p.food - need)
    deficit = need - p.food
    return replace(p, food=0,
                   culture=max(0, p.culture - STARVATION_CULTURE * deficit))


def _refill_row(state: GameState) -> GameState:
    """用当前牌堆补满卡牌列空格; 牌堆空则切时代; III 空则 last_round."""
    row = list(state.card_row)
    deck = list(state.civil_deck)
    future = dict(state.future_decks)
    age = state.age
    last_round = state.last_round
    cursor = age
    for i in range(ROW_SLOTS):
        if row[i] is not None:
            continue
        while not deck and not last_round:
            nxt = cursor.next()
            if nxt is None:
                last_round = True
                break
            cursor = nxt
            deck = list(future.pop(nxt.value, ()))
            if deck:
                age = nxt  # 仅在启用非空牌堆时推进时代
        if deck:
            row[i] = deck.pop(0)
    return replace(state, card_row=tuple(row), civil_deck=tuple(deck),
                   future_decks=future, age=age, last_round=last_round)


def _end_turn(state: GameState, db: CardDB) -> GameState:
    idx = state.current_player
    p = _settle(state.players[idx], db)
    gov = db.get(p.government).government
    if gov is None:
        raise ValueError(f"government {p.government} has no stats")
    p = replace(p, civil_actions=gov.civil_actions,
                military_actions=gov.military_actions)
    state = replace_player(state, idx, p)

    nxt = (idx + 1) % len(state.players)
    state = replace(state, current_player=nxt)
    if nxt != 0:
        return _refill_row(state)
    # 新一轮
    if state.last_round:
        scores = tuple(pl.culture for pl in state.players)
        return replace(state, terminal=True, final_scores=scores)
    row = [c for c in state.card_row if c is not None]
    removed = state.removed
    if row:
        removed = removed + (row.pop(0),)     # RULES-AUDIT: 每轮移除最左 1 张
    row += [None] * (ROW_SLOTS - len(row))
    state = replace(state, round=state.round + 1, card_row=tuple(row),
                    removed=removed)
    return _refill_row(state)
