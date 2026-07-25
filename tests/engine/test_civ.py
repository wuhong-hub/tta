"""文明数值合成系统测试(见 tta/engine/civ.py 模块 docstring)."""

import pytest

from tta.engine import effects
from tta.engine.civ import (
    CivValues,
    civ_values,
    discontent,
    hand_limit_civil,
    is_uprising,
)
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import PlayerState


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
            government=GovernmentStats(civil_actions=4, military_actions=2, urban_limit=2),
        ),
        "agriculture": _card("agriculture", CardCategory.FARM, token_value=1),
        "philosophy": _card(
            "philosophy", CardCategory.LAB, urban_produces={"science": 1},
        ),
        "religion": _card(
            "religion", CardCategory.TEMPLE,
            urban_produces={"happiness": 1, "culture": 1},
        ),
        "warriors": _card("warriors", CardCategory.INFANTRY, strength=1),
        "pyramids": _card(
            "pyramids", CardCategory.WONDER, wonder_stages=(3, 2),
            wonder_bonus={"civil_actions": 1},
        ),
        "great_library": _card(
            "great_library", CardCategory.WONDER, wonder_stages=(2, 2),
            wonder_bonus={"science": 1, "culture": 1, "civil_hand_extra": 1},
        ),
        "test_leader": _card(
            "test_leader", CardCategory.LEADER, handler="test_leader_bonus",
        ),
        "no_handler_leader": _card("no_handler_leader", CardCategory.LEADER),
        "test_special": _card(
            "test_special", CardCategory.SPECIAL, handler="test_special_bonus",
        ),
    }
    return CardDB(cards=cards, initial_tableau=("agriculture", "philosophy"),
                  initial_government="despotism")


def _player(**overrides: object) -> PlayerState:
    base: dict = {"name": "P0", "yellow_bank": 18}
    base.update(overrides)
    return PlayerState(**base)


def test_despotism_with_two_farms_one_lab() -> None:
    # 专制 + 2 农业工人 + 1 哲学工人: science=1, civil=4, military=2, urban=2
    p = _player(buildings={
        "farm": {"agriculture": 2},
        "lab": {"philosophy": 1},
    })
    civ = civ_values(_db(), p)
    assert civ == CivValues(
        science_rate=1, culture_rate=0, strength=0, happiness=0,
        civil_actions=4, military_actions=2, urban_limit=2,
        civil_hand_extra=0, military_hand_extra=0, colonization=0,
    )


def test_temple_worker_adds_happiness_and_culture() -> None:
    p = _player(buildings={"temple": {"religion": 1}})
    civ = civ_values(_db(), p)
    assert civ.happiness == 1
    assert civ.culture_rate == 1


def test_urban_produces_scale_with_workers() -> None:
    p = _player(buildings={
        "lab": {"philosophy": 2},
        "temple": {"religion": 2},
    })
    civ = civ_values(_db(), p)
    assert civ.science_rate == 2
    assert civ.happiness == 2
    assert civ.culture_rate == 2


def test_military_unit_workers_add_strength() -> None:
    p = _player(buildings={"infantry": {"warriors": 2}})
    civ = civ_values(_db(), p)
    assert civ.strength == 2


def test_completed_pyramids_adds_civil_action() -> None:
    p = _player(wonders=("pyramids",))
    civ = civ_values(_db(), p)
    assert civ.civil_actions == 5


def test_wonder_bonus_hand_extra_and_rates() -> None:
    p = _player(wonders=("great_library",))
    civ = civ_values(_db(), p)
    assert civ.science_rate == 1
    assert civ.culture_rate == 1
    assert civ.civil_hand_extra == 1
    # civil_hand_extra 不计入 civil_actions
    assert civ.civil_actions == 4


def test_sources_stack() -> None:
    # 建筑 + 单位 + 双奇迹 同时叠加
    p = _player(
        buildings={
            "lab": {"philosophy": 1},
            "temple": {"religion": 1},
            "infantry": {"warriors": 1},
        },
        wonders=("pyramids", "great_library"),
    )
    civ = civ_values(_db(), p)
    assert civ.science_rate == 2
    assert civ.culture_rate == 2
    assert civ.happiness == 1
    assert civ.strength == 1
    assert civ.civil_actions == 5
    assert civ.civil_hand_extra == 1


def test_happiness_clamped_to_eight() -> None:
    p = _player(buildings={"temple": {"religion": 10}})
    assert civ_values(_db(), p).happiness == 8


def test_negative_rates_clamped_to_zero() -> None:
    # 负 science bonus(假设性减益) 截断为 0
    db = _db()
    cards = dict(db.cards)
    cards["tyranny"] = _card(
        "tyranny", CardCategory.GOVERNMENT,
        government=GovernmentStats(
            civil_actions=3, military_actions=3, urban_limit=3,
            bonus={"science": -1, "culture": -1, "strength": -1},
        ),
    )
    db = CardDB(cards=cards, initial_tableau=db.initial_tableau,
                initial_government="tyranny")
    p = _player(government="tyranny")
    civ = civ_values(db, p)
    assert civ.science_rate == 0
    assert civ.culture_rate == 0
    assert civ.strength == 0


def test_government_without_stats_raises() -> None:
    db = _db()
    cards = dict(db.cards)
    cards["broken_gov"] = _card("broken_gov", CardCategory.GOVERNMENT)
    db = CardDB(cards=cards, initial_tableau=db.initial_tableau,
                initial_government="broken_gov")
    with pytest.raises(ValueError, match="government"):
        civ_values(db, _player(government="broken_gov"))


def test_discontent_zero_at_full_yellow_bank() -> None:
    assert discontent(_db(), _player(yellow_bank=18)) == 0


def test_discontent_equals_requirement_minus_happiness() -> None:
    # yellow_bank=16 -> 需求 1; 无幸福 -> 不满 1
    p = _player(yellow_bank=16)
    assert discontent(_db(), p) == 1
    # 寺庙 1 工人提供 1 幸福 -> 不满 0
    p = _player(yellow_bank=16, buildings={"temple": {"religion": 1}})
    assert discontent(_db(), p) == 0


def test_discontent_never_negative() -> None:
    # 需求 0 且幸福充足 -> 0 而非负数
    p = _player(yellow_bank=18, buildings={"temple": {"religion": 2}})
    assert discontent(_db(), p) == 0


def test_is_uprising_when_discontent_exceeds_worker_pool() -> None:
    # yellow_bank=10 -> 需求 3, 幸福 0 -> 不满 3
    assert is_uprising(_db(), _player(yellow_bank=10, worker_pool=1))
    assert not is_uprising(_db(), _player(yellow_bank=10, worker_pool=3))


def test_hand_limit_civil_default_equals_civil_actions() -> None:
    assert hand_limit_civil(_db(), _player()) == 4


def test_hand_limit_civil_includes_wonder_extra() -> None:
    p = _player(wonders=("great_library",))
    assert hand_limit_civil(_db(), p) == 5


def test_static_bonuses_empty_without_leader_or_special(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def spy(db: CardDB, p: PlayerState) -> dict[str, int]:
        nonlocal called
        called = True
        return {"science": 99}

    monkeypatch.setitem(effects.STATIC_BONUS_HANDLERS, "test_leader_bonus", spy)
    monkeypatch.setitem(effects.STATIC_BONUS_HANDLERS, "test_special_bonus", spy)
    assert effects.static_bonuses(_db(), _player()) == {}
    assert not called


def test_static_bonuses_from_leader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        effects.STATIC_BONUS_HANDLERS, "test_leader_bonus",
        lambda db, p: {"science": 2, "strength": 1},
    )
    p = _player(leader="test_leader")
    assert effects.static_bonuses(_db(), p) == {"science": 2, "strength": 1}
    civ = civ_values(_db(), p)
    assert civ.science_rate == 2
    assert civ.strength == 1


def test_static_bonuses_from_special_tech(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        effects.STATIC_BONUS_HANDLERS, "test_special_bonus",
        lambda db, p: {"military_hand_extra": 1, "colonization": 2},
    )
    p = _player(developed=("agriculture", "test_special"))
    assert effects.static_bonuses(_db(), p) == {
        "military_hand_extra": 1, "colonization": 2,
    }
    civ = civ_values(_db(), p)
    assert civ.military_hand_extra == 1
    assert civ.colonization == 2


def test_static_bonuses_skip_cards_without_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        effects.STATIC_BONUS_HANDLERS, "test_leader_bonus",
        lambda db, p: {"culture": 1},
    )
    # 无 handler 的领袖与 handler 未注册的卡均被跳过, 仅已注册者生效
    p = _player(leader="no_handler_leader", developed=("test_special",))
    assert effects.static_bonuses(_db(), p) == {}
    p = _player(leader="test_leader", developed=("test_special",))
    assert effects.static_bonuses(_db(), p) == {"culture": 1}
