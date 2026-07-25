"""引擎核心枚举与卡牌类别集合(P1 官方规则核心)."""

from enum import Enum


class Age(Enum):
    """时代. IV 为终局标记时代(无牌堆), 不参与卡牌年龄比较与 next()."""

    A = "A"
    I = "I"  # noqa: E741
    II = "II"
    III = "III"
    IV = "IV"

    def next(self) -> "Age | None":
        """返回下一时代, III 之后为 None(IV 仅为状态标记)."""
        order = (Age.A, Age.I, Age.II, Age.III)
        idx = order.index(self)
        return order[idx + 1] if idx + 1 < len(order) else None


class DeckType(Enum):
    """牌堆类型."""

    CIVIL = "civil"
    MILITARY = "military"


class Phase(Enum):
    """回合内相位.

    TURN_START 为引擎自动处理相位(回合开始阶段, 见 turn.advance,
    玩家不可行动); POLITICS 为政治阶段(第一回合跳过); ACTION 为
    行动阶段(PassTurn 仅在此相位合法)。
    """

    TURN_START = "turn_start"
    POLITICS = "politics"
    ACTION = "action"


class CardCategory(Enum):
    """卡牌类别(官方规则 16 种)."""

    FARM = "farm"
    MINE = "mine"
    LAB = "lab"
    TEMPLE = "temple"
    LIBRARY = "library"
    THEATER = "theater"
    ARENA = "arena"
    INFANTRY = "infantry"
    CAVALRY = "cavalry"
    ARTILLERY = "artillery"
    AIR = "air"
    GOVERNMENT = "government"
    LEADER = "leader"
    WONDER = "wonder"
    ACTION = "action"
    SPECIAL = "special"


URBAN_CATEGORIES = frozenset({
    CardCategory.LAB,
    CardCategory.TEMPLE,
    CardCategory.LIBRARY,
    CardCategory.THEATER,
    CardCategory.ARENA,
})
"""城市建筑类别(受政体城市建筑上限约束)."""

UNIT_CATEGORIES = frozenset({
    CardCategory.INFANTRY,
    CardCategory.CAVALRY,
    CardCategory.ARTILLERY,
    CardCategory.AIR,
})
"""军事单位类别."""

WORKER_CATEGORIES = (
    URBAN_CATEGORIES | UNIT_CATEGORIES
    | frozenset({CardCategory.FARM, CardCategory.MINE})
)
"""可放置工人的类别; 建筑槽位直接以 category.value 为键(BuildingType 已删除)."""


class SpecialType(Enum):
    """特殊科技子类."""

    LAW = "law"
    WARFARE = "warfare"
    EXPLORATION = "exploration"
    CONSTRUCTION = "construction"
