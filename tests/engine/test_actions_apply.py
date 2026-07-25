"""动作应用测试(见 tta/engine/apply.py)."""

import copy

import pytest

from tta.engine import effects
from tta.engine.actions import (
    Build,
    BuildWonderStage,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    IllegalActionError,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    PlayLeader,
    TakeCard,
    Upgrade,
)
from tta.engine.apply import _spend_civil, apply
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import ROW_SLOTS, GameState, PlayerState, replace_player


def _card(card_id: str, category: CardCategory, **overrides: object) -> CardDefinition:
    base: dict = {
        "id": card_id,
        "name": card_id,
        "name_en": card_id,
        "age": Age.A,
        "deck": DeckType.CIVIL,
        "category": category,
    }
    base.update(overrides)
    return CardDefinition(**base)


def _db() -> CardDB:
    cards = {
        "despotism": _card(
            "despotism", CardCategory.GOVERNMENT,
            government=GovernmentStats(civil_actions=4, military_actions=2,
                                       urban_limit=2),
        ),
        "republic": _card(
            "republic", CardCategory.GOVERNMENT, age=Age.I,
            cost_science=4, cost_science_revolution=2,
            government=GovernmentStats(civil_actions=4, military_actions=3,
                                       urban_limit=3),
        ),
        "agriculture": _card("agriculture", CardCategory.FARM, cost_science=2,
                             build_cost=2, token_value=1),
        "irrigation": _card("irrigation", CardCategory.FARM, age=Age.I,
                            cost_science=3, build_cost=3, token_value=2),
        "bronze": _card("bronze", CardCategory.MINE, cost_science=2,
                        build_cost=2, token_value=1),
        "philosophy": _card("philosophy", CardCategory.LAB, cost_science=3,
                            build_cost=3, urban_produces={"science": 1}),
        "warriors": _card("warriors", CardCategory.INFANTRY, cost_science=2,
                          build_cost=2, strength=1),
        "leader_a": _card("leader_a", CardCategory.LEADER),
        "leader_b": _card("leader_b", CardCategory.LEADER, age=Age.I),
        "pyramids": _card("pyramids", CardCategory.WONDER,
                          wonder_stages=(3, 2)),
        "great_library": _card("great_library", CardCategory.WONDER,
                               wonder_stages=(2, 2)),
        "tactics_test": _card("tactics_test", CardCategory.ACTION,
                              handler="test_action"),
    }
    return CardDB(cards=cards, initial_tableau=("agriculture", "philosophy"),
                  initial_government="despotism")


def _player(**overrides: object) -> PlayerState:
    base: dict = {"name": "P0", "civil_actions": 4, "military_actions": 2}
    base.update(overrides)
    return PlayerState(**base)


def _row(*ids: str | None) -> tuple[str | None, ...]:
    row = list(ids) + [None] * (ROW_SLOTS - len(ids))
    return tuple(row)


def _state(player: PlayerState, card_row: tuple[str | None, ...] | None = None,
           **overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.A,
        "current_player": 0,
        "card_row": card_row if card_row is not None else _row(),
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (player, _player(name="P1")),
        "rng_state": 0,
    }
    base.update(overrides)
    return GameState(**base)


def test_pass_turn_advances_turn() -> None:
    # Task 8 起 PassTurn 交由 turn.advance 执行官方回合推进
    state = _state(_player(civil_actions=1, military_actions=0))
    new = apply(state, PassTurn(), _db())
    assert new.current_player == 1
    # 行动点恢复为 civ 总值
    assert new.players[0].civil_actions == 4
    assert new.players[0].military_actions == 2


def test_illegal_action_raises() -> None:
    db = _db()
    # 白点不足支付 10 号位的 3 费
    state = _state(_player(civil_actions=1),
                   card_row=_row(*([None] * 10), "bronze"))
    with pytest.raises(IllegalActionError):
        apply(state, TakeCard(10), db)
    # 终局状态一切动作非法
    with pytest.raises(IllegalActionError):
        apply(_state(_player(), terminal=True), Build("bronze"), db)


def test_take_card_apply() -> None:
    db = _db()
    state = _state(_player(), card_row=_row("philosophy", "bronze"))
    new = apply(state, TakeCard(0), db)
    p = new.players[0]
    assert p.hand_civil == ("philosophy",)
    assert p.civil_actions == 3
    assert new.card_row[0] is None
    assert new.card_row[1] == "bronze"
    assert new.players[1] == state.players[1]


def test_take_card_wonder_sets_progress() -> None:
    db = _db()
    # 位置费 1 + 已完成奇迹 1 = 2 白点
    p = _player(wonders=("great_library",))
    state = _state(p, card_row=_row(None, "pyramids"))
    new = apply(state, TakeCard(1), db)
    assert new.players[0].wonder_progress == ("pyramids", 0)
    assert new.players[0].hand_civil == ()
    assert new.players[0].civil_actions == 2
    assert new.card_row[1] is None


def test_develop_tech_apply() -> None:
    db = _db()
    p = _player(science=3, hand_civil=("philosophy",))
    new = apply(_state(p), DevelopTech("philosophy"), db)
    assert new.players[0].developed == ("philosophy",)
    assert new.players[0].hand_civil == ()
    assert new.players[0].science == 0
    assert new.players[0].civil_actions == 3
    assert new.players[0].military_actions == 2


def test_develop_unit_uses_red_point() -> None:
    db = _db()
    p = _player(science=2, hand_civil=("warriors",))
    new = apply(_state(p), DevelopTech("warriors"), db)
    assert new.players[0].developed == ("warriors",)
    assert new.players[0].military_actions == 1
    assert new.players[0].civil_actions == 4


def test_develop_government_peaceful() -> None:
    db = _db()
    p = _player(science=4, hand_civil=("republic",))
    new = apply(_state(p), DevelopGovernment("republic", False), db)
    assert new.players[0].government == "republic"
    assert new.players[0].science == 0
    assert new.players[0].civil_actions == 3
    assert new.discard == ("despotism",)


def test_develop_government_revolution() -> None:
    db = _db()
    p = _player(science=3, civil_actions=3, hand_civil=("republic",))
    new = apply(_state(p), DevelopGovernment("republic", True), db)
    # 革命: 低费 2 点 + 全部剩余白点归零
    assert new.players[0].government == "republic"
    assert new.players[0].science == 1
    assert new.players[0].civil_actions == 0
    assert new.discard == ("despotism",)


def test_build_apply() -> None:
    db = _db()
    p = _player(developed=("bronze",), card_tokens={"bronze": 5},
                worker_pool=1)
    new = apply(_state(p), Build("bronze"), db)
    assert new.players[0].buildings == {"mine": {"bronze": 1}}
    assert new.players[0].worker_pool == 0
    assert new.players[0].card_tokens == {"bronze": 3}
    assert new.players[0].civil_actions == 3


def test_upgrade_pays_difference() -> None:
    db = _db()
    # irrigation(3) - agriculture(2) = 1 资源
    p = _player(developed=("agriculture", "irrigation"),
                buildings={"farm": {"agriculture": 1}},
                card_tokens={"bronze": 3})
    new = apply(_state(p), Upgrade("agriculture", "irrigation"), db)
    assert new.players[0].buildings == {"farm": {"irrigation": 1}}
    assert new.players[0].card_tokens == {"bronze": 2}
    assert new.players[0].civil_actions == 3


def test_destroy_returns_worker_keeps_tokens() -> None:
    db = _db()
    p = _player(buildings={"farm": {"agriculture": 1}},
                card_tokens={"agriculture": 2}, worker_pool=1)
    new = apply(_state(p), Destroy("agriculture"), db)
    assert new.players[0].buildings == {"farm": {}}
    assert new.players[0].worker_pool == 2
    # SIMPLIFICATION: 卡上蓝点保留
    assert new.players[0].card_tokens == {"agriculture": 2}
    assert new.players[0].civil_actions == 3


def test_disband_returns_worker_uses_red() -> None:
    db = _db()
    p = _player(buildings={"infantry": {"warriors": 1}}, worker_pool=1)
    new = apply(_state(p), Disband("warriors"), db)
    assert new.players[0].buildings == {"infantry": {}}
    assert new.players[0].worker_pool == 2
    assert new.players[0].military_actions == 1
    assert new.players[0].civil_actions == 4


def test_play_leader_apply() -> None:
    db = _db()
    p = _player(hand_civil=("leader_a",), leader="leader_b",
                leader_ages=("I",))
    new = apply(_state(p), PlayLeader("leader_a"), db)
    assert new.players[0].leader == "leader_a"
    assert new.players[0].leader_ages == ("I", "A")
    assert new.players[0].hand_civil == ()
    # 1 白点花出并拿回, 净耗 0
    assert new.players[0].civil_actions == 4
    assert new.discard == ("leader_b",)


def test_build_wonder_stage_apply() -> None:
    db = _db()
    p = _player(wonder_progress=("pyramids", 0), card_tokens={"bronze": 3},
                blue_bank=16)
    new = apply(_state(p), BuildWonderStage(), db)
    assert new.players[0].wonder_progress == ("pyramids", 1)
    assert new.players[0].card_tokens == {}
    assert new.players[0].blue_bank == 15
    assert new.players[0].civil_actions == 3


def test_build_wonder_stage_completion() -> None:
    db = _db()
    p = _player(wonder_progress=("pyramids", 1), card_tokens={"bronze": 2},
                blue_bank=16)
    new = apply(_state(p), BuildWonderStage(), db)
    assert new.players[0].wonder_progress is None
    assert new.players[0].wonders == ("pyramids",)
    assert new.players[0].card_tokens == {}
    assert new.players[0].blue_bank == 15


def test_play_action_card_framework(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()

    def handler(state: GameState, player_index: int, db: CardDB) -> GameState:
        p = state.players[player_index]
        return replace_player(state, player_index,
                              copy.replace(p, culture=p.culture + 5))

    monkeypatch.setitem(effects.ACTION_HANDLERS, "test_action", handler)
    p = _player(hand_civil=("tactics_test",))
    new = apply(_state(p), PlayActionCard("tactics_test"), db)
    assert new.players[0].culture == 5
    assert new.players[0].hand_civil == ()
    assert new.players[0].civil_actions == 3
    assert new.discard == ("tactics_test",)


def test_increase_population_apply() -> None:
    db = _db()
    # yellow_bank=18 -> 人口费 2: 扣 1 白点 + 2 食物, 银行 -1, 空闲 +1
    p = _player(developed=("agriculture",), card_tokens={"agriculture": 2},
                yellow_bank=18, worker_pool=1)
    new = apply(_state(p), IncreasePopulation(), db)
    p0 = new.players[0]
    assert p0.civil_actions == 3
    assert p0.card_tokens == {}
    assert p0.yellow_bank == 17
    assert p0.worker_pool == 2


def test_increase_population_track_cost_varies_with_bank() -> None:
    db = _db()
    # yellow_bank=16 -> 区段(13-16)人口费 3
    p = _player(developed=("agriculture",), card_tokens={"agriculture": 3},
                yellow_bank=16, worker_pool=1)
    new = apply(_state(p), IncreasePopulation(), db)
    p0 = new.players[0]
    assert p0.card_tokens == {}
    assert p0.yellow_bank == 15
    assert p0.worker_pool == 2


def test_spend_civil_red_padding_requires_hammurabi() -> None:
    db = _db()
    # 无 hammurabi: 白点不足时防御性抛错(正常流程由 legal 拦截)
    p = _player(civil_actions=1, military_actions=2)
    with pytest.raises(IllegalActionError):
        _spend_civil(db, p, 2)
    # hammurabi: 红点 1:1 垫付
    p = _player(civil_actions=1, military_actions=2, leader="hammurabi")
    new = _spend_civil(db, p, 2)
    assert new.civil_actions == 0
    assert new.military_actions == 1


def test_apply_does_not_mutate_input() -> None:
    db = _db()
    p = _player(developed=("bronze",), card_tokens={"bronze": 5},
                worker_pool=1)
    state = _state(p)
    snapshot = copy.deepcopy(state)
    apply(state, Build("bronze"), db)
    assert state == snapshot
