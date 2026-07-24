"""游戏状态模型与序列化测试."""

from tta.engine.enums import Age
from tta.engine.state import (
    GameState,
    PlayerState,
    from_dict,
    replace_player,
    state_hash,
    to_dict,
    workers_total,
)


def _player(name: str = "P0") -> PlayerState:
    return PlayerState(
        name=name,
        culture=3,
        science=5,
        materials=2,
        food=4,
        yellow_bank=21,
        worker_pool=1,
        buildings={"farm": {"agriculture": 2}, "mine": {"bronze": 1}},
        developed=("agriculture", "agriculture", "bronze"),
        hand_civil=("irrigation",),
        government="despotism",
        civil_actions=4,
        military_actions=2,
    )


def _state() -> GameState:
    return GameState(
        round=2,
        age=Age.A,
        current_player=1,
        card_row=("irrigation", None, "iron") + (None,) * 10,
        civil_deck=("alchemy", "monarchy"),
        future_decks={"I": ("coal",), "II": (), "III": ("oil",)},
        discard=("harvest_a",),
        removed=(),
        players=(_player("P0"), _player("P1")),
        rng_state=12345,
    )


def test_workers_total() -> None:
    # pool 1 + farm 2 + mine 1 = 4
    assert workers_total(_player()) == 4


def test_serialization_roundtrip() -> None:
    state = _state()
    assert from_dict(to_dict(state)) == state


def test_state_hash_stable_and_sensitive() -> None:
    state = _state()
    assert state_hash(state) == state_hash(state)
    other = replace_player(state, 0, PlayerState(name="P0", culture=99))
    assert state_hash(state) != state_hash(other)


def test_terminal_fields_roundtrip() -> None:
    state = _state()
    done = GameState(**{**state.__dict__, "terminal": True, "final_scores": (10, 20)})
    assert from_dict(to_dict(done)) == done


def test_replace_player_does_not_mutate() -> None:
    state = _state()
    before = state.players[0]
    _ = replace_player(state, 0, PlayerState(name="X"))
    assert state.players[0] is before
