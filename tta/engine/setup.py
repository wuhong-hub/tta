"""开局构造."""

from tta.engine.constants import INITIAL_FOOD, INITIAL_MATERIALS, INITIAL_YELLOW, ROW_SLOTS
from tta.engine.enums import CATEGORY_TO_BUILDING, Age
from tta.engine.model import CardDB
from tta.engine.rng import rng_shuffle
from tta.engine.state import GameState, PlayerState


def new_game(db: CardDB, num_players: int, seed: int) -> GameState:
    """洗牌并发牌, 返回初始 GameState.

    Raises:
        ValueError: 玩家数不在 2-4.
    """
    if not 2 <= num_players <= 4:
        raise ValueError(f"players must be 2-4, got {num_players}")
    rng = seed
    decks: dict[Age, tuple[str, ...]] = {}
    for age in (Age.A, Age.I, Age.II, Age.III):
        rng, shuffled = rng_shuffle(rng, db.civil_decks[age])
        decks[age] = tuple(shuffled)

    deck_a = list(decks[Age.A])
    row = tuple(deck_a[:ROW_SLOTS])
    rest = tuple(deck_a[ROW_SLOTS:])
    future = {a.value: decks[a] for a in (Age.I, Age.II, Age.III)}

    gov = db.get(db.initial_government).government
    if gov is None:
        raise ValueError("initial government has no stats")
    placed = len(db.initial_tableau)
    buildings: dict[str, dict[str, int]] = {}
    for cid in db.initial_tableau:
        btype = CATEGORY_TO_BUILDING[db.get(cid).category].value
        slots = buildings.setdefault(btype, {})
        slots[cid] = slots.get(cid, 0) + 1

    players = tuple(
        PlayerState(
            name=f"P{i}",
            food=INITIAL_FOOD,
            materials=INITIAL_MATERIALS,
            yellow_bank=INITIAL_YELLOW - placed,
            worker_pool=0,
            buildings={k: dict(v) for k, v in buildings.items()},
            developed=db.initial_tableau,
            government=db.initial_government,
            civil_actions=gov.civil_actions,
            military_actions=gov.military_actions,
        )
        for i in range(num_players)
    )
    return GameState(round=1, age=Age.A, current_player=0, card_row=row,
                     civil_deck=rest, future_decks=future, discard=(), removed=(),
                     players=players, rng_state=rng)
