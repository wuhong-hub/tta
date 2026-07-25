"""动作类型与合法动作枚举测试(见 tta/engine/actions.py 与 legal.py)."""

import pytest

from tta.engine import effects
from tta.engine.actions import (
    Action,
    Build,
    BuildWonderStage,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    PassTurn,
    PlayActionCard,
    PlayLeader,
    TakeCard,
    Upgrade,
    action_from_dict,
    action_to_dict,
)
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.legal import ROW_COSTS, legal_actions
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
)


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
        "iron": _card("iron", CardCategory.MINE, age=Age.I, cost_science=4,
                      build_cost=4, token_value=2),
        "philosophy": _card("philosophy", CardCategory.LAB, cost_science=3,
                            build_cost=3, urban_produces={"science": 1}),
        "alchemy": _card("alchemy", CardCategory.LAB, age=Age.I,
                         cost_science=5, build_cost=5,
                         urban_produces={"science": 2}),
        "printing_press": _card("printing_press", CardCategory.LAB, age=Age.II,
                                cost_science=6, build_cost=6,
                                urban_produces={"science": 3}),
        "religion": _card("religion", CardCategory.TEMPLE, cost_science=2,
                          build_cost=3, urban_produces={"happiness": 1}),
        "warriors": _card("warriors", CardCategory.INFANTRY, cost_science=2,
                          build_cost=2, strength=1),
        "militia": _card("militia", CardCategory.INFANTRY, cost_science=3,
                         build_cost=3, strength=1),
        "legion": _card("legion", CardCategory.INFANTRY, age=Age.I,
                        cost_science=4, build_cost=4, strength=2),
        "code_of_laws": _card("code_of_laws", CardCategory.SPECIAL,
                              cost_science=2),
        "leader_a": _card("leader_a", CardCategory.LEADER),
        "leader_b": _card("leader_b", CardCategory.LEADER, age=Age.I),
        "pyramids": _card("pyramids", CardCategory.WONDER,
                          wonder_stages=(3, 2)),
        "great_library": _card("great_library", CardCategory.WONDER,
                               wonder_stages=(2, 2)),
        "engineering": _card("engineering", CardCategory.ACTION),
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


_ALL_ACTIONS: list[Action] = [
    TakeCard(0),
    DevelopTech("philosophy"),
    DevelopGovernment("republic", True),
    DevelopGovernment("republic", False),
    Build("bronze"),
    Upgrade("bronze", "iron"),
    Destroy("philosophy"),
    Disband("warriors"),
    PlayLeader("leader_a"),
    BuildWonderStage(),
    PlayActionCard("tactics_test"),
    PassTurn(),
]


def test_row_costs_shape() -> None:
    assert ROW_COSTS == (1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3)
    assert len(ROW_COSTS) == ROW_SLOTS


def test_action_serialization_roundtrip() -> None:
    for action in _ALL_ACTIONS:
        assert action_from_dict(action_to_dict(action)) == action


def test_terminal_state_has_no_actions() -> None:
    state = _state(_player(), terminal=True)
    assert legal_actions(_db(), state) == []


def test_pending_blocks_everything_but_pass() -> None:
    pending = (PendingEffect(kind="build_farm_mine", discount=1),)
    state = _state(_player(), card_row=_row("bronze"), pending=pending)
    assert legal_actions(_db(), state) == [PassTurn()]


def test_first_round_only_take_card() -> None:
    state = _state(_player(), card_row=_row(*(["bronze"] * ROW_SLOTS)), round=1)
    actions = legal_actions(_db(), state)
    assert actions
    assert all(isinstance(a, TakeCard) for a in actions)


def test_pass_turn_appended_last() -> None:
    state = _state(_player(), card_row=_row("bronze"))
    actions = legal_actions(_db(), state)
    assert actions[-1] == PassTurn()
    assert actions.count(PassTurn()) == 1


def test_take_card_row_costs() -> None:
    db = _db()
    row = _row(*(["bronze"] * ROW_SLOTS))
    # 1 白点: 只能拿位置费 1 的 0-4 号位
    actions = legal_actions(db, _state(_player(civil_actions=1), card_row=row))
    assert [a.row_index for a in actions if isinstance(a, TakeCard)] == [0, 1, 2, 3, 4]
    # 2 白点: 扩展到 5-9 号位
    actions = legal_actions(db, _state(_player(civil_actions=2), card_row=row))
    assert [a.row_index for a in actions if isinstance(a, TakeCard)] == list(range(10))


def test_take_card_hand_limit() -> None:
    db = _db()
    hand = ("religion", "philosophy", "code_of_laws", "engineering")
    # 手牌已达上限(专制 4 张): 普通牌不可拿, 奇迹牌不受上限限制
    state = _state(_player(hand_civil=hand), card_row=_row("pyramids", "bronze"))
    takes = [a for a in legal_actions(db, state) if isinstance(a, TakeCard)]
    assert takes == [TakeCard(0)]


def test_take_card_tech_duplicate_blocked() -> None:
    db = _db()
    # 手牌有同名科技
    state = _state(_player(hand_civil=("bronze",)), card_row=_row("bronze"))
    assert TakeCard(0) not in legal_actions(db, state)
    # 场上已研发同名科技
    state = _state(_player(developed=("bronze",)), card_row=_row("bronze"))
    assert TakeCard(0) not in legal_actions(db, state)
    # 手牌有同名政体
    state = _state(_player(hand_civil=("republic",)), card_row=_row("republic"))
    assert TakeCard(0) not in legal_actions(db, state)
    # 不同名科技不受影响
    state = _state(_player(developed=("bronze",)), card_row=_row("iron"))
    assert TakeCard(0) in legal_actions(db, state)


def test_take_card_leader_age_duplicate_blocked() -> None:
    db = _db()
    state = _state(_player(leader_ages=("A",)),
                   card_row=_row("leader_a", "leader_b"))
    takes = [a for a in legal_actions(db, state) if isinstance(a, TakeCard)]
    assert takes == [TakeCard(1)]


def test_take_card_wonder_fee_bonus() -> None:
    db = _db()
    # 奇迹拿牌费 = 位置费 + 已完成奇迹数: 0 号位 1 + 1 个已完成奇迹 = 2
    p = _player(civil_actions=1, wonders=("great_library",))
    state = _state(p, card_row=_row("pyramids"))
    assert TakeCard(0) not in legal_actions(db, state)
    p = _player(civil_actions=2, wonders=("great_library",))
    state = _state(p, card_row=_row("pyramids"))
    assert TakeCard(0) in legal_actions(db, state)


def test_take_card_wonder_blocked_by_progress() -> None:
    db = _db()
    p = _player(wonder_progress=("pyramids", 0))
    state = _state(p, card_row=_row("great_library"))
    assert TakeCard(0) not in legal_actions(db, state)


def test_develop_tech_white_and_red_points() -> None:
    db = _db()
    # 城市建筑科技: 1 白点 + 科技费
    p = _player(civil_actions=1, science=3, hand_civil=("philosophy",))
    assert DevelopTech("philosophy") in legal_actions(db, _state(p))
    p = _player(civil_actions=1, science=2, hand_civil=("philosophy",))
    assert DevelopTech("philosophy") not in legal_actions(db, _state(p))
    # 兵种: 1 红点 + 科技费(白点不能替代)
    p = _player(civil_actions=0, military_actions=1, science=2,
                hand_civil=("warriors",))
    assert DevelopTech("warriors") in legal_actions(db, _state(p))
    p = _player(civil_actions=4, military_actions=0, science=2,
                hand_civil=("warriors",))
    assert DevelopTech("warriors") not in legal_actions(db, _state(p))


def test_develop_government_peaceful_and_revolution() -> None:
    db = _db()
    hand = ("republic",)
    # 科技点够高费: 和平与革命均可
    p = _player(civil_actions=1, science=4, hand_civil=hand)
    actions = legal_actions(db, _state(p))
    assert DevelopGovernment("republic", False) in actions
    assert DevelopGovernment("republic", True) in actions
    # 只够低费: 仅革命
    p = _player(civil_actions=1, science=3, hand_civil=hand)
    actions = legal_actions(db, _state(p))
    assert DevelopGovernment("republic", False) not in actions
    assert DevelopGovernment("republic", True) in actions
    # 低费也不够 / 无白点: 均不可
    p = _player(civil_actions=1, science=1, hand_civil=hand)
    assert not [a for a in legal_actions(db, _state(p))
                if isinstance(a, DevelopGovernment)]
    p = _player(civil_actions=0, science=4, hand_civil=hand)
    assert not [a for a in legal_actions(db, _state(p))
                if isinstance(a, DevelopGovernment)]


def test_build_copy_limit_and_pool_and_resources() -> None:
    db = _db()
    base = dict(developed=("bronze", "bronze"), card_tokens={"bronze": 10},
                worker_pool=2)
    # 已放 1 < 持有 2: 可建
    p = _player(buildings={"mine": {"bronze": 1}}, **base)
    assert Build("bronze") in legal_actions(db, _state(p))
    # 已放 2 = 持有 2: 不可建
    p = _player(buildings={"mine": {"bronze": 2}}, **base)
    assert Build("bronze") not in legal_actions(db, _state(p))
    # 空闲池空: 不可建
    p = _player(worker_pool=0, **{k: v for k, v in base.items()
                                  if k != "worker_pool"})
    assert Build("bronze") not in legal_actions(db, _state(p))
    # 资源不足: 不可建
    p = _player(developed=("iron",), card_tokens={"bronze": 3}, worker_pool=1)
    assert Build("iron") not in legal_actions(db, _state(p))


def test_build_unit_uses_red_point() -> None:
    db = _db()
    base = dict(developed=("warriors",), card_tokens={"bronze": 5},
                worker_pool=1)
    p = _player(civil_actions=0, military_actions=1, **base)
    assert Build("warriors") in legal_actions(db, _state(p))
    p = _player(civil_actions=4, military_actions=0, **base)
    assert Build("warriors") not in legal_actions(db, _state(p))


def test_build_urban_limit_per_category() -> None:
    db = _db()
    # 专制 urban_limit=2; lab 已有哲学+炼金两座 -> 第三座 lab 不可建,
    # 已有建筑的第二份与其他类别不受影响
    developed = ("philosophy", "philosophy", "alchemy", "printing_press",
                 "religion")
    buildings = {"lab": {"philosophy": 1, "alchemy": 1}}
    p = _player(developed=developed, buildings=buildings,
                card_tokens={"bronze": 20}, worker_pool=3)
    actions = legal_actions(db, _state(p))
    assert Build("philosophy") in actions          # 已有建筑的第二份
    assert Build("printing_press") not in actions  # 超出 lab 类别上限
    assert Build("religion") in actions            # temple 类别未满


def test_upgrade_level_order() -> None:
    db = _db()
    base = dict(card_tokens={"bronze": 20})
    # 时代高者可升; 反向与同卡不可
    p = _player(developed=("agriculture", "irrigation"),
                buildings={"farm": {"agriculture": 1}}, **base)
    actions = legal_actions(db, _state(p))
    assert Upgrade("agriculture", "irrigation") in actions
    assert Upgrade("irrigation", "agriculture") not in actions
    assert Upgrade("agriculture", "agriculture") not in actions
    # 同时代按造价: 战士(2) -> 民兵(3) 可升, 反向不可
    p = _player(developed=("warriors", "militia"),
                buildings={"infantry": {"warriors": 1}}, **base)
    actions = legal_actions(db, _state(p))
    assert Upgrade("warriors", "militia") in actions
    assert Upgrade("militia", "warriors") not in actions


def test_upgrade_cross_category_rejected() -> None:
    db = _db()
    p = _player(developed=("agriculture", "bronze"),
                buildings={"farm": {"agriculture": 1}},
                card_tokens={"bronze": 20})
    assert not [a for a in legal_actions(db, _state(p))
                if isinstance(a, Upgrade)]


def test_upgrade_requires_unoccupied_copy() -> None:
    db = _db()
    base = dict(card_tokens={"bronze": 20},
                buildings={"farm": {"agriculture": 1, "irrigation": 1}})
    # 唯一 irrigation 副本已被占用: 不可升
    p = _player(developed=("agriculture", "irrigation"), **base)
    assert Upgrade("agriculture", "irrigation") not in legal_actions(db, _state(p))
    # 有空闲副本: 可升
    p = _player(developed=("agriculture", "irrigation", "irrigation"), **base)
    assert Upgrade("agriculture", "irrigation") in legal_actions(db, _state(p))


def test_upgrade_unit_uses_red_point() -> None:
    db = _db()
    base = dict(developed=("warriors", "legion"),
                buildings={"infantry": {"warriors": 1}},
                card_tokens={"bronze": 20})
    p = _player(civil_actions=0, military_actions=1, **base)
    assert Upgrade("warriors", "legion") in legal_actions(db, _state(p))
    p = _player(civil_actions=4, military_actions=0, **base)
    assert Upgrade("warriors", "legion") not in legal_actions(db, _state(p))


def test_destroy_disband_action_colors() -> None:
    db = _db()
    buildings = {"lab": {"philosophy": 1}, "infantry": {"warriors": 1}}
    p = _player(civil_actions=1, military_actions=0, buildings=buildings)
    actions = legal_actions(db, _state(p))
    assert Destroy("philosophy") in actions
    assert Disband("warriors") not in actions
    p = _player(civil_actions=0, military_actions=1, buildings=buildings)
    actions = legal_actions(db, _state(p))
    assert Destroy("philosophy") not in actions
    assert Disband("warriors") in actions


def test_play_leader_legality() -> None:
    db = _db()
    p = _player(civil_actions=1, hand_civil=("leader_a",))
    assert PlayLeader("leader_a") in legal_actions(db, _state(p))
    p = _player(civil_actions=0, hand_civil=("leader_a",))
    assert PlayLeader("leader_a") not in legal_actions(db, _state(p))
    p = _player(civil_actions=1, hand_civil=("leader_a",), leader_ages=("A",))
    assert PlayLeader("leader_a") not in legal_actions(db, _state(p))


def test_build_wonder_stage_legality() -> None:
    db = _db()
    base = dict(wonder_progress=("pyramids", 0), civil_actions=1)
    p = _player(card_tokens={"bronze": 3}, **base)
    assert BuildWonderStage() in legal_actions(db, _state(p))
    # 资源不足
    p = _player(card_tokens={"bronze": 2}, **base)
    assert BuildWonderStage() not in legal_actions(db, _state(p))
    # SIMPLIFICATION: 蓝点供给区为空时不可建阶段
    p = _player(card_tokens={"bronze": 3}, blue_bank=0, **base)
    assert BuildWonderStage() not in legal_actions(db, _state(p))
    # 无白点
    p = _player(card_tokens={"bronze": 3}, civil_actions=0,
                wonder_progress=("pyramids", 0))
    assert BuildWonderStage() not in legal_actions(db, _state(p))
    # 无在建奇迹
    p = _player(card_tokens={"bronze": 3}, civil_actions=1)
    assert BuildWonderStage() not in legal_actions(db, _state(p))


def test_play_action_card_requires_registered_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db()
    hand = ("engineering", "tactics_test")
    # 注册表为空: 均不可打出
    p = _player(civil_actions=1, hand_civil=hand)
    assert not [a for a in legal_actions(db, _state(p))
                if isinstance(a, PlayActionCard)]
    # 注册后: 仅已注册者可打出
    monkeypatch.setitem(effects.ACTION_HANDLERS, "test_action",
                        lambda db, state: state)
    p = _player(civil_actions=1, hand_civil=hand)
    actions = [a for a in legal_actions(db, _state(p))
               if isinstance(a, PlayActionCard)]
    assert actions == [PlayActionCard("tactics_test")]
