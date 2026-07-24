"""引擎核心枚举."""

from enum import Enum


class Age(Enum):
    """时代."""

    A = "A"
    I = "I"  # noqa: E741
    II = "II"
    III = "III"

    def next(self) -> "Age | None":
        """返回下一时代, III 之后为 None."""
        order = [Age.A, Age.I, Age.II, Age.III]
        idx = order.index(self)
        return order[idx + 1] if idx + 1 < len(order) else None


class DeckType(Enum):
    """牌堆类型."""

    CIVIL = "civil"
    MILITARY = "military"


class CardCategory(Enum):
    """卡牌类别."""

    FARM = "farm"
    MINE = "mine"
    LAB = "lab"
    TEMPLE = "temple"
    UNIT = "unit"
    GOVERNMENT = "government"
    ACTION = "action"


class BuildingType(Enum):
    """建筑槽位类型(与单位共用一套工人放置机制)."""

    FARM = "farm"
    MINE = "mine"
    LAB = "lab"
    TEMPLE = "temple"
    UNIT = "unit"


CATEGORY_TO_BUILDING: dict[CardCategory, BuildingType] = {
    CardCategory.FARM: BuildingType.FARM,
    CardCategory.MINE: BuildingType.MINE,
    CardCategory.LAB: BuildingType.LAB,
    CardCategory.TEMPLE: BuildingType.TEMPLE,
    CardCategory.UNIT: BuildingType.UNIT,
}
