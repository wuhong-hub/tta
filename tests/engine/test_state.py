"""游戏状态模型与序列化测试."""

import pytest

from tta.engine.enums import Age
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
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
        yellow_bank=18,
        blue_bank=16,
        worker_pool=1,
        buildings={"farm": {"agriculture": 2}, "mine": {"bronze": 1}},
        card_tokens={"bronze": 3},
        developed=("agriculture", "bronze"),
        hand_civil=("irrigation",),
        hand_military=(),
        government="despotism",
        leader="alexander",
        leader_ages=("A",),
        wonder_progress=("pyramids", 2),
        wonders=("colossus",),
        civil_actions=4,
        military_actions=2,
        turn_discounts={"unit_build": 1},
    )


def _state() -> GameState:
    return GameState(
        round=2,
        age=Age.A,
        current_player=1,
        card_row=("irrigation", None, "iron") + (None,) * (ROW_SLOTS - 3),
        civil_deck=("alchemy", "monarchy"),
        future_decks={"I": ("coal",), "II": (), "III": ("oil",)},
        discard=("harvest_a",),
        removed=("wonder_x",),
        players=(_player("P0"), _player("P1")),
        rng_state=12345,
        pending=(
            PendingEffect(kind="build_farm_mine", discount=2),
            PendingEffect(kind="wonder_stage", discount=0),
        ),
        last_round=True,
        terminal=True,
        final_scores=(10, 20),
    )


def test_workers_total() -> None:
    # pool 1 + farm 2 + mine 1 = 4
    assert workers_total(_player()) == 4


def test_serialization_roundtrip_full() -> None:
    # 非空 pending / turn_discounts / wonder_progress / terminal 字段全往返
    state = _state()
    assert from_dict(to_dict(state)) == state


def test_serialization_roundtrip_none_optionals() -> None:
    # wonder_progress / leader / final_scores 为 None 的往返
    state = _state()
    plain_players = tuple(
        PlayerState(name=p.name) for p in state.players
    )
    bare = GameState(
        round=1,
        age=Age.I,
        current_player=0,
        card_row=(None,) * ROW_SLOTS,
        civil_deck=(),
        future_decks={},
        discard=(),
        removed=(),
        players=plain_players,
        rng_state=7,
    )
    assert bare.players[0].wonder_progress is None
    assert bare.players[0].leader is None
    assert bare.final_scores is None
    assert from_dict(to_dict(bare)) == bare


def test_to_dict_json_encodable() -> None:
    import json

    blob = json.dumps(to_dict(_state()), sort_keys=True)
    assert isinstance(blob, str)


def test_state_hash_stable_and_sensitive() -> None:
    state = _state()
    assert state_hash(state) == state_hash(state)
    other = replace_player(state, 0, PlayerState(name="P0", culture=99))
    assert state_hash(state) != state_hash(other)
    changed_pending = GameState(
        **{**state.__dict__, "pending": (PendingEffect(kind="build_urban", discount=1),)}
    )
    assert state_hash(state) != state_hash(changed_pending)


def test_replace_player_does_not_mutate() -> None:
    state = _state()
    before = state.players[0]
    new_state = replace_player(state, 0, PlayerState(name="X"))
    assert state.players[0] is before
    assert new_state.players[0].name == "X"
    assert new_state.players[1] is state.players[1]


def test_card_row_length_validation() -> None:
    with pytest.raises(ValueError, match="card_row"):
        GameState(
            round=1,
            age=Age.A,
            current_player=0,
            card_row=(None,) * (ROW_SLOTS - 1),
            civil_deck=(),
            future_decks={},
            discard=(),
            removed=(),
            players=(PlayerState(name="P0"),),
            rng_state=0,
        )
