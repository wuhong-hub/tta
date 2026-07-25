"""回合相位化 + pending 响应者泛化测试(P2 Task 1).

覆盖: Phase 序列化往返、round==1 直接 ACTION、round>=2 的
POLITICS -> SkipPolitics -> ACTION -> PassTurn 相位流转、pending
responder 切换(测试桩)与恢复、旧 pending(responder=None)语义回归。
"""

import pytest

from tta.engine import turn
from tta.engine.actions import (
    Build,
    DeclineResponse,
    IllegalActionError,
    PassTurn,
    SkipPolitics,
    TakeCard,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType, Phase
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.setup import new_game
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
    from_dict,
    to_dict,
)


def _card(card_id: str, category: CardCategory, age: Age = Age.A,
          **overrides: object) -> CardDefinition:
    base: dict = {
        "id": card_id,
        "name": card_id,
        "name_en": card_id,
        "age": age,
        "deck": DeckType.CIVIL,
        "category": category,
    }
    base.update(overrides)
    return CardDefinition(**base)


def _db() -> CardDB:
    cards = {
        "despotism": _card(
            "despotism", CardCategory.GOVERNMENT,
            government=GovernmentStats(
                civil_actions=4, military_actions=2, urban_limit=2),
        ),
        "agriculture": _card(
            "agriculture", CardCategory.FARM, token_value=1, build_cost=2),
        "bronze": _card(
            "bronze", CardCategory.MINE, token_value=1, build_cost=2),
    }
    # 牌列/牌堆填充卡(new_game 需要 20 张时代 A 内政牌)
    for i in range(20):
        card_id = f"xa{i}"
        cards[card_id] = _card(
            card_id, CardCategory.ACTION, quantities=(20, 20, 20))
    return CardDB(cards=cards, initial_tableau=("agriculture", "bronze"),
                  initial_government="despotism")


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {"name": name}
    base.update(overrides)
    return PlayerState(**base)


def _state(**overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.A,
        "current_player": 0,
        "card_row": (None,) * ROW_SLOTS,
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (_player("P0"), _player("P1")),
        "rng_state": 0,
    }
    base.update(overrides)
    return GameState(**base)


# --- Phase 枚举与序列化 -----------------------------------------------------


def test_phase_enum_values() -> None:
    assert Phase.TURN_START.value == "turn_start"
    assert Phase.POLITICS.value == "politics"
    assert Phase.ACTION.value == "action"


def test_game_state_default_phase_is_action() -> None:
    assert _state().phase is Phase.ACTION


def test_phase_serialization_roundtrip() -> None:
    state = _state(
        phase=Phase.POLITICS,
        military_deck=("bonus_a",),
        future_military_decks={"I": ("tactics_i",)},
        military_discard=("event_a",),
        current_events=("event_x",),
        future_events=("event_y",),
        past_events=("event_z",),
    )
    data = to_dict(state)
    assert data["phase"] == "politics"
    assert data["military_deck"] == ["bonus_a"]
    assert data["future_military_decks"] == {"I": ["tactics_i"]}
    assert from_dict(data) == state


def test_from_dict_backward_compatible_without_new_fields() -> None:
    # 旧格式(无 phase / 军事字段)反序列化: 落默认值
    state = _state()
    data = to_dict(state)
    for key in ("phase", "military_deck", "future_military_decks",
                "military_discard", "current_events", "future_events",
                "past_events"):
        del data[key]
    for player in data["players"]:
        for key in ("tactics", "tactics_public", "tactics_this_turn",
                    "colonies", "declared_wars", "pacts", "caesar_used"):
            del player[key]
    assert from_dict(data) == state


def test_player_military_fields_serialization_roundtrip() -> None:
    p = _player(
        "P0",
        tactics="phalanx",
        tactics_public=True,
        tactics_this_turn=True,
        colonies=("territory_x",),
        declared_wars=("war_y",),
        pacts=("pact_z",),
        caesar_used=True,
    )
    state = _state(players=(p, _player("P1")))
    assert from_dict(to_dict(state)) == state


# --- PendingEffect 泛化序列化 ----------------------------------------------


def test_pending_responder_context_roundtrip() -> None:
    pending = PendingEffect(
        kind="aggression_defense", discount=0, responder=1,
        context={"card_id": "raid", "attacker": 0})
    data = to_dict(_state(pending=(pending,)))
    entry = data["pending"][0]
    assert entry["responder"] == 1
    assert entry["context"] == {"card_id": "raid", "attacker": 0}
    assert from_dict(data).pending == (pending,)


def test_pending_defaults_omitted_and_old_format_compatible() -> None:
    # responder=None / context={} 不落盘(旧格式逐字节兼容)
    data = to_dict(_state(pending=(PendingEffect(kind="build_farm_mine", discount=3),)))
    assert data["pending"] == [{"kind": "build_farm_mine", "discount": 3}]
    # 旧格式 dict 反序列化: responder/context 落默认值
    old = {"kind": "wonder_stage", "discount": 2, "science_gain": 0}
    state = from_dict({**to_dict(_state()), "pending": [old]})
    assert state.pending == (PendingEffect(kind="wonder_stage", discount=2),)


def test_skip_politics_action_serialization() -> None:
    assert action_from_dict(action_to_dict(SkipPolitics())) == SkipPolitics()


# --- 相位流转 ---------------------------------------------------------------


def test_new_game_round_one_starts_in_action_phase() -> None:
    db = _db()
    state = new_game(db, 2, seed=1)
    assert state.round == 1
    # 官方规则: 第一回合跳过回合开始阶段与政治阶段
    assert state.phase is Phase.ACTION


def test_round_one_all_players_stay_in_action_phase() -> None:
    db = _db()
    state = new_game(db, 2, seed=1)
    state = apply(state, PassTurn(), db)  # P0 过 -> P1, 仍 round 1
    assert state.round == 1
    assert state.phase is Phase.ACTION
    state = apply(state, PassTurn(), db)  # P1 过 -> round 2, P0 政治阶段
    assert state.round == 2
    assert state.current_player == 0
    assert state.phase is Phase.POLITICS


def test_advance_round_two_enters_politics_phase() -> None:
    new = turn.advance(_state(round=1, current_player=1), _db())
    assert new.round == 2
    assert new.phase is Phase.POLITICS


def test_politics_phase_legal_is_only_skip_politics() -> None:
    state = _state(phase=Phase.POLITICS)
    assert legal_actions(_db(), state) == [SkipPolitics()]
    with pytest.raises(IllegalActionError):
        apply(state, PassTurn(), _db())


def test_skip_politics_enters_action_phase() -> None:
    db = _db()
    state = _state(phase=Phase.POLITICS)
    new = apply(state, SkipPolitics(), db)
    assert new.phase is Phase.ACTION
    # ACTION 相位恢复正常动作枚举(PassTurn 在末尾)
    legal = legal_actions(db, new)
    assert legal[-1] == PassTurn()
    assert SkipPolitics() not in legal


def test_pass_turn_only_legal_in_action_phase() -> None:
    db = _db()
    state = _state(phase=Phase.POLITICS)
    assert PassTurn() not in legal_actions(db, state)
    new = apply(state, SkipPolitics(), db)
    assert PassTurn() in legal_actions(db, new)
    after = apply(new, PassTurn(), db)
    assert after.current_player == 1
    assert after.phase is Phase.POLITICS


def test_full_phase_cycle_round_two() -> None:
    # POLITICS -> SkipPolitics -> ACTION -> PassTurn -> 下一位 POLITICS
    db = _db()
    state = _state(phase=Phase.POLITICS, current_player=0)
    state = apply(state, SkipPolitics(), db)
    assert state.phase is Phase.ACTION
    state = apply(state, PassTurn(), db)
    assert state.current_player == 1
    assert state.phase is Phase.POLITICS


def test_skip_politics_illegal_in_action_phase() -> None:
    state = _state(phase=Phase.ACTION)
    with pytest.raises(IllegalActionError):
        apply(state, SkipPolitics(), _db())


# --- pending responder 切换(测试桩) ----------------------------------------


def _responder_pending_state() -> GameState:
    """current_player=0, pending 要求 1 号位响应(build_farm_mine 折扣 3)."""
    p1 = _player(
        "P1",
        developed=("agriculture",),
        worker_pool=1,
        card_tokens={"bronze": 1},
    )
    return _state(
        players=(_player("P0"), p1),
        pending=(PendingEffect(kind="build_farm_mine", discount=3,
                               responder=1),),
    )


def test_pending_responder_generates_actions_for_responder() -> None:
    db = _db()
    state = _responder_pending_state()
    legal = legal_actions(db, state)
    # 为 responder(1 号位)生成结算动作; 响应期间无 PassTurn 兜底;
    # 可放弃白名单 kind 附带 DeclineResponse 兜底(P2-T5)
    assert Build("agriculture") in legal
    assert DeclineResponse() in legal
    assert PassTurn() not in legal
    assert all(isinstance(a, (Build, DeclineResponse)) for a in legal)


def test_pending_responder_settlement_pops_and_restores_control() -> None:
    db = _db()
    state = _responder_pending_state()
    new = apply(state, Build("agriculture"), db)
    # 结算落在 responder(1 号位)身上
    assert new.pending == ()
    assert new.players[1].buildings == {"farm": {"agriculture": 1}}
    assert new.players[1].worker_pool == 0
    assert new.players[1].card_tokens == {"bronze": 1}  # 费用 max(0, 2-3) = 0
    # current_player 与 0 号位不受影响, 控制权恢复
    assert new.current_player == 0
    assert new.players[0].buildings == {}
    legal = legal_actions(db, new)
    assert legal[-1] == PassTurn()


def test_pending_responder_blocks_current_player_actions() -> None:
    db = _db()
    state = _responder_pending_state()
    # 响应期间 current_player 的普通动作不合法
    assert TakeCard(0) not in legal_actions(db, state)
    with pytest.raises(IllegalActionError):
        apply(state, PassTurn(), db)


def test_pending_responder_equal_current_player_keeps_pass_fallback() -> None:
    # responder 显式等于 current_player: 视同本人 pending, PassTurn 兜底仍在
    p0 = _player("P0", developed=("agriculture",), worker_pool=1)
    state = _state(
        players=(p0, _player("P1")),
        pending=(PendingEffect(kind="build_farm_mine", discount=3,
                               responder=0),),
    )
    legal = legal_actions(_db(), state)
    assert Build("agriculture") in legal
    assert legal[-1] == PassTurn()


def test_pending_unknown_responder_kind_yields_no_actions() -> None:
    state = _state(pending=(PendingEffect(
        kind="test_response", discount=0, responder=1),))
    assert legal_actions(_db(), state) == []


def test_pending_without_responder_settled_by_current_player() -> None:
    # P1 旧语义回归: responder=None 由 current_player 结算 + PassTurn 兜底
    p0 = _player("P0", developed=("agriculture",), worker_pool=1)
    state = _state(
        players=(p0, _player("P1")),
        pending=(PendingEffect(kind="build_farm_mine", discount=3),),
    )
    db = _db()
    legal = legal_actions(db, state)
    assert Build("agriculture") in legal
    assert legal[-1] == PassTurn()
    new = apply(state, Build("agriculture"), db)
    assert new.pending == ()
    assert new.players[0].buildings == {"farm": {"agriculture": 1}}
