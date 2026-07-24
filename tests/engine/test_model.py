"""枚举与卡牌数据模型测试."""

from tta.engine.constants import ROW_COSTS, ROW_SLOTS
from tta.engine.enums import CATEGORY_TO_BUILDING, Age, BuildingType, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats


def test_age_next() -> None:
    assert Age.A.next() is Age.I
    assert Age.I.next() is Age.II
    assert Age.II.next() is Age.III
    assert Age.III.next() is None


def test_row_costs_length() -> None:
    assert len(ROW_COSTS) == ROW_SLOTS == 13
    assert all(c in (1, 2, 3) for c in ROW_COSTS)


def test_category_to_building_covers_buildings() -> None:
    assert CATEGORY_TO_BUILDING[CardCategory.FARM] is BuildingType.FARM
    assert CATEGORY_TO_BUILDING[CardCategory.UNIT] is BuildingType.UNIT
    assert CardCategory.GOVERNMENT not in CATEGORY_TO_BUILDING
    assert CardCategory.ACTION not in CATEGORY_TO_BUILDING


def _gov() -> GovernmentStats:
    return GovernmentStats(civil_actions=4, military_actions=2,
                           civil_hand_limit=4, military_hand_limit=2)


def test_card_db_get() -> None:
    card = CardDefinition(id="despotism", name="专制", age=Age.A,
                          deck=DeckType.CIVIL, category=CardCategory.GOVERNMENT,
                          government=_gov())
    db = CardDB(cards={"despotism": card}, civil_decks={Age.A: ()},
                initial_tableau=(), initial_government="despotism")
    assert db.get("despotism") is card


def test_card_definition_defaults() -> None:
    card = CardDefinition(id="x", name="x", age=Age.A,
                          deck=DeckType.CIVIL, category=CardCategory.ACTION)
    assert card.cost_science == 0
    assert card.produces == {}
    assert card.government is None
