"""动作结算测试(回合推进见 test_turn.py)."""

import copy

import pytest

from tta.engine.actions import (
    Build,
    Develop,
    IllegalActionError,
    IncreasePopulation,
    PlayActionCard,
    TakeCard,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import GameState, PlayerState

GOV = GovernmentStats(civil_actions=4, military_actions=2,
                      civil_hand_limit=4, military_hand_limit=2)


def _db() -> CardDB:
    def gov_card(cid: str, sci: int = 0) -> CardDefinition:
        return CardDefinition(id=cid, name=cid, age=Age.A, deck=DeckType.CIVIL,
                              category=CardCategory.GOVERNMENT, cost_science=sci,
                              government=GOV)

    def bld(cid: str, cat: CardCategory, sci: int, build: int,
            produces: dict | None = None) -> CardDefinition:
        return CardDefinition(id=cid, name=cid, age=Age.A, deck=DeckType.CIVIL,
                              category=cat, cost_science=sci, build_cost=build,
                              produces=produces or {})

    cards = {
        "despotism": gov_card("despotism"),
        "monarchy": gov_card("monarchy", sci=2),
        "agriculture": bld("agriculture", CardCategory.FARM, 0, 2, {"food": 2}),
        "irrigation": bld("irrigation", CardCategory.FARM, 2, 2, {"food": 2}),
        "swordsmen": bld("swordsmen", CardCategory.UNIT, 2, 2, {"strength": 2}),
        "harvest_a": CardDefinition(id="harvest_a", name="丰收", age=Age.A,
                                    deck=DeckType.CIVIL, category=CardCategory.ACTION,
                                    gains={"food": 3}),
    }
    return CardDB(cards=cards, civil_decks={Age.A: ()},
                  initial_tableau=(), initial_government="despotism")


def _state(p: PlayerState, row: tuple = (None,) * 13) -> GameState:
    return GameState(round=1, age=Age.A, current_player=0, card_row=row,
                     civil_deck=(), future_decks={}, discard=(), removed=(),
                     players=(p,), rng_state=1)


def test_illegal_action_raises() -> None:
    with pytest.raises(IllegalActionError):
        apply(_state(PlayerState(name="P0", government="despotism")),
              TakeCard(0), _db())


def test_take_card() -> None:
    row = ("irrigation",) + (None,) * 12
    p = PlayerState(name="P0", government="despotism", civil_actions=2)
    s = apply(_state(p, row), TakeCard(0), _db())
    assert s.players[0].hand_civil == ("irrigation",)
    assert s.players[0].civil_actions == 1
    assert s.card_row[0] is None


def test_develop_tech_and_government() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=2,
                    science=4, hand_civil=("irrigation", "monarchy"))
    s = apply(_state(p), Develop("irrigation"), _db())
    assert s.players[0].developed == ("irrigation",)
    assert s.players[0].science == 2 and s.players[0].civil_actions == 1
    s2 = apply(s, Develop("monarchy"), _db())
    assert s2.players[0].government == "monarchy"
    assert "despotism" in s2.discard
    assert s2.players[0].science == 0


def test_develop_unit_uses_military_action() -> None:
    p = PlayerState(name="P0", government="despotism", military_actions=1,
                    science=2, hand_civil=("swordsmen",))
    s = apply(_state(p), Develop("swordsmen"), _db())
    assert s.players[0].military_actions == 0
    assert s.players[0].developed == ("swordsmen",)


def test_build_from_pool_and_upgrade() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=2,
                    materials=4, worker_pool=1,
                    developed=("agriculture", "irrigation"))
    s = apply(_state(p), Build("agriculture"), _db())
    assert s.players[0].buildings == {"farm": {"agriculture": 1}}
    assert s.players[0].worker_pool == 0 and s.players[0].materials == 2
    # 第二次建造: 池空, 从同类型低级建筑升级(工人 agriculture -> irrigation)
    s2 = apply(s, Build("irrigation"), _db())
    assert s2.players[0].buildings == {"farm": {"irrigation": 1}}
    assert s2.players[0].materials == 0


def test_build_unit_uses_military_action() -> None:
    p = PlayerState(name="P0", government="despotism", military_actions=1,
                    materials=2, worker_pool=1, developed=("swordsmen",))
    s = apply(_state(p), Build("swordsmen"), _db())
    assert s.players[0].buildings == {"unit": {"swordsmen": 1}}
    assert s.players[0].military_actions == 0


def test_increase_population() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    food=3, yellow_bank=5)
    s = apply(_state(p), IncreasePopulation(), _db())
    assert s.players[0].food == 1
    assert s.players[0].yellow_bank == 4
    assert s.players[0].worker_pool == 1


def test_play_action_card_gains_and_discards() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    food=0, hand_civil=("harvest_a",))
    s = apply(_state(p), PlayActionCard("harvest_a"), _db())
    assert s.players[0].food == 3
    assert s.players[0].hand_civil == ()
    assert s.discard == ("harvest_a",)


def test_play_action_card_unknown_gains_key_fails() -> None:
    # gains 含未知键(如 happiness)时必须 fail-loud, 不得静默忽略
    db = _db()
    bad = CardDefinition(id="bad_action", name="坏卡", age=Age.A,
                         deck=DeckType.CIVIL, category=CardCategory.ACTION,
                         gains={"happiness": 1})
    db = CardDB(cards={**db.cards, "bad_action": bad},
                civil_decks=db.civil_decks,
                initial_tableau=db.initial_tableau,
                initial_government=db.initial_government)
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    hand_civil=("bad_action",))
    with pytest.raises(ValueError, match="bad_action"):
        apply(_state(p), PlayActionCard("bad_action"), db)


def test_apply_does_not_mutate_input() -> None:
    row = ("irrigation",) + (None,) * 12
    p = PlayerState(name="P0", government="despotism", civil_actions=2,
                    materials=4, worker_pool=1, developed=("irrigation",),
                    buildings={"farm": {"agriculture": 1}})
    state = _state(p, row)
    snapshot = copy.deepcopy(state)
    _ = apply(state, TakeCard(0), _db())
    _ = apply(state, Build("irrigation"), _db())
    assert state == snapshot
