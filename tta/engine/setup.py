"""开局设置: new_game 官方化.

官方规则(规则书 Setup):
- 时代 A 内政堆 20 张洗匀, 发 13 张上牌列, 余 7 张为当前内政牌堆;
- 时代 I/II/III 内政堆按人数组牌洗匀, 入 future_decks;
- 每名玩家: 黄点 18 银行 + 1 池, 蓝点 16 银行; 初始科技已研发
  (initial_tableau, 含宗教), 初始工人 = db.initial_workers
  (农业 2/铜矿 2/哲学 1/武士 1, 宗教 0); 政府专制, 无领袖;
- 第一回合行动点: 座位 i -> 内政 i+1, 军事 0(官方首轮拿牌规则).
"""

from tta.engine.enums import Age
from tta.engine.model import MAX_PLAYERS, MIN_PLAYERS, CardDB
from tta.engine.rng import rng_shuffle
from tta.engine.state import ROW_SLOTS, GameState, PlayerState

FUTURE_AGES = (Age.I, Age.II, Age.III)
"""进入 future_decks 的时代."""


def new_game(db: CardDB, num_players: int, seed: int) -> GameState:
    """洗牌并发牌, 返回官方开局 GameState.

    Raises:
        ValueError: 玩家数不在 [MIN_PLAYERS, MAX_PLAYERS].
    """
    if not MIN_PLAYERS <= num_players <= MAX_PLAYERS:
        msg = f"num_players 须在 {MIN_PLAYERS}-{MAX_PLAYERS}, 收到 {num_players}"
        raise ValueError(msg)
    rng = seed
    rng, deck_a = rng_shuffle(rng, db.deck_for(Age.A, num_players))
    row = tuple(deck_a[:ROW_SLOTS])
    rest = tuple(deck_a[ROW_SLOTS:])
    future: dict[str, tuple[str, ...]] = {}
    for age in FUTURE_AGES:
        rng, shuffled = rng_shuffle(rng, db.deck_for(age, num_players))
        future[age.value] = tuple(shuffled)

    buildings: dict[str, dict[str, int]] = {}
    for card_id, count in db.initial_workers:
        category = db.get(card_id).category.value
        slots = buildings.setdefault(category, {})
        slots[card_id] = slots.get(card_id, 0) + count

    players = tuple(
        PlayerState(
            name=f"P{i}",
            yellow_bank=18,
            blue_bank=16,
            worker_pool=1,
            buildings={k: dict(v) for k, v in buildings.items()},
            developed=db.initial_tableau,
            government=db.initial_government,
            civil_actions=i + 1,
            military_actions=0,
        )
        for i in range(num_players)
    )
    return GameState(
        round=1, age=Age.A, current_player=0, card_row=row, civil_deck=rest,
        future_decks=future, discard=(), removed=(), players=players,
        rng_state=rng,
    )
