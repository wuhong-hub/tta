"""回合结算、时代推进与游戏结束测试."""

from tta.engine.actions import PassTurn
from tta.engine.apply import apply, happiness, strength
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import GameState, PlayerState

GOV = GovernmentStats(civil_actions=4, military_actions=2,
                      civil_hand_limit=4, military_hand_limit=2)


def _db() -> CardDB:
    def bld(cid: str, cat: CardCategory, produces: dict) -> CardDefinition:
        return CardDefinition(id=cid, name=cid, age=Age.A, deck=DeckType.CIVIL,
                              category=cat, build_cost=2, produces=produces)

    cards = {
        "despotism": CardDefinition(id="despotism", name="专制", age=Age.A,
                                    deck=DeckType.CIVIL,
                                    category=CardCategory.GOVERNMENT, government=GOV),
        "agriculture": bld("agriculture", CardCategory.FARM, {"food": 2}),
        "bronze": bld("bronze", CardCategory.MINE, {"materials": 1}),
        "philosophy": bld("philosophy", CardCategory.LAB, {"science": 1}),
        "religion": bld("religion", CardCategory.TEMPLE, {"happiness": 1, "culture": 1}),
        "swordsmen": bld("swordsmen", CardCategory.UNIT, {"strength": 2}),
    }
    return CardDB(cards=cards, civil_decks={Age.A: ()},
                  initial_tableau=(), initial_government="despotism")


def _state(players: tuple, **kw) -> GameState:
    base = dict(round=1, age=Age.A, current_player=0,
                card_row=(None,) * 13, civil_deck=(), future_decks={},
                discard=(), removed=(), players=players, rng_state=1)
    base.update(kw)
    return GameState(**base)


def _farmer(**kw) -> PlayerState:
    base = dict(name="P0", government="despotism", food=0,
                buildings={"farm": {"agriculture": 2},
                           "mine": {"bronze": 1},
                           "lab": {"philosophy": 1}})
    base.update(kw)
    return PlayerState(**base)


def test_production_and_consumption() -> None:
    # 产: food+4, materials+1, science+1; 4 工人吃 4 => food 不变
    s = apply(_state((_farmer(),)), PassTurn(), _db())
    p = s.players[0]
    assert p.food == 0 and p.materials == 1 and p.science == 1


def test_starvation_penalty() -> None:
    # 产 2 食物需 4, 缺 2 => 文化 10 - 2*STARVATION_CULTURE = 2, 食物归零
    p = _farmer(culture=10, food=0,
                buildings={"farm": {"agriculture": 1}, "mine": {"bronze": 3}})
    s = apply(_state((p,)), PassTurn(), _db())
    assert s.players[0].culture == 2 and s.players[0].food == 0


def test_uprising_skips_production() -> None:
    # 空闲工人 3 > 满意容量 2 => 起义: 无生产
    p = _farmer(worker_pool=3)
    s = apply(_state((p,)), PassTurn(), _db())
    assert s.players[0].materials == 0 and s.players[0].science == 0


def test_happiness_and_strength() -> None:
    p = _farmer(buildings={"temple": {"religion": 2}, "unit": {"swordsmen": 3}})
    assert happiness(_db(), p) == 2 + 2  # BASE_HAPPINESS=2
    assert strength(_db(), p) == 6


def test_actions_refill_and_next_player() -> None:
    p0 = _farmer(civil_actions=0, military_actions=0)
    p1 = _farmer(name="P1")
    s = apply(_state((p0, p1)), PassTurn(), _db())
    assert s.current_player == 1
    assert s.players[0].civil_actions == 4 and s.players[0].military_actions == 2


def test_round_wrap_removes_leftmost_and_refills() -> None:
    row = ("religion", "swordsmen") + (None,) * 11
    deck = ("agriculture", "bronze", "philosophy")
    p0 = _farmer()
    s = apply(_state((p0,), card_row=row, civil_deck=deck), PassTurn(), _db())
    assert s.round == 2 and s.current_player == 0
    assert s.removed == ("religion",)
    assert s.card_row[0] == "swordsmen"
    assert s.card_row[1] == "agriculture" and s.card_row[3] == "philosophy"
    assert s.civil_deck == ()


def test_age_transition_on_empty_deck() -> None:
    row = ("swordsmen",) + (None,) * 12
    p0 = _farmer()
    s = apply(_state((p0,), card_row=row, civil_deck=(),
                     future_decks={"I": ("religion", "bronze")}), PassTurn(), _db())
    assert s.age is Age.I
    assert s.removed == ("swordsmen",)
    assert s.card_row[0] == "religion" and s.card_row[1] == "bronze"
    assert "I" not in s.future_decks


def test_age_skips_empty_middle_deck() -> None:
    # A 堆空、I 堆空、II 有牌: 推进后 age 跳到 II, 牌列补 II 的牌
    row = ("swordsmen",) + (None,) * 12
    p0 = _farmer()
    s = apply(_state((p0,), card_row=row, civil_deck=(),
                     future_decks={"I": (), "II": ("religion", "bronze")}),
              PassTurn(), _db())
    assert s.age is Age.II
    assert s.removed == ("swordsmen",)
    assert s.card_row[0] == "religion" and s.card_row[1] == "bronze"
    assert "I" not in s.future_decks and "II" not in s.future_decks


def test_last_round_then_terminal() -> None:
    p0 = _farmer(culture=10)
    # III 时代且牌堆已空: 本轮结束后终局
    s = apply(_state((p0,), age=Age.III), PassTurn(), _db())
    assert s.last_round is True
    s2 = apply(s, PassTurn(), _db())
    assert s2.terminal is True
    assert s2.final_scores == (10,)
