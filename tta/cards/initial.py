"""初始科技(印在玩家版图上的时代 A 科技, 不进入任何时代牌堆).

数值来源: Card Reference v1.09 第 1 页 + docs/research/tta-official-data.md §3
(两者一致)。初始科技 quantities 恒 (0,0,0); 开局布局由 INITIAL_TABLEAU /
INITIAL_WORKERS 描述, new_game(Task 13)使用。
"""

from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDefinition, GovernmentStats

INITIAL_GOVERNMENT = "despotism"
"""开局政体卡 id."""

INITIAL_TABLEAU: tuple[str, ...] = (
    "agriculture", "agriculture", "bronze", "bronze",
    "philosophy", "religion", "warriors",
)
"""每名玩家开局已研发的初始科技卡 id(含重复; religion 开局 0 工人)."""

INITIAL_WORKERS: dict[str, int] = {
    "agriculture": 2,
    "bronze": 2,
    "philosophy": 1,
    "warriors": 1,
}
"""开局各初始科技卡上的工人数(religion 为 0, 故不在列)."""

AGRICULTURE = CardDefinition(
    id="agriculture", name="农业", name_en="Agriculture", age=Age.A,
    deck=DeckType.CIVIL, category=CardCategory.FARM,
    text="每个蓝色方块 = 1 食物。", build_cost=2, token_value=1,
)

BRONZE = CardDefinition(
    id="bronze", name="青铜", name_en="Bronze", age=Age.A,
    deck=DeckType.CIVIL, category=CardCategory.MINE,
    text="每个蓝色方块 = 1 资源。", build_cost=2, token_value=1,
)

PHILOSOPHY = CardDefinition(
    id="philosophy", name="哲学", name_en="Philosophy", age=Age.A,
    deck=DeckType.CIVIL, category=CardCategory.LAB,
    text="每个实验室工人产出 1 科技。", build_cost=3,
    urban_produces={"science": 1},
)

RELIGION = CardDefinition(
    id="religion", name="宗教", name_en="Religion", age=Age.A,
    deck=DeckType.CIVIL, category=CardCategory.TEMPLE,
    text="每个寺庙工人产出 1 文化 + 1 笑脸。", build_cost=3,
    urban_produces={"culture": 1, "happiness": 1},
)

WARRIORS = CardDefinition(
    id="warriors", name="武士", name_en="Warriors", age=Age.A,
    deck=DeckType.CIVIL, category=CardCategory.INFANTRY,
    text="每个武士单位提供 1 军力。", build_cost=2, strength=1,
)

DESPOTISM = CardDefinition(
    id="despotism", name="专制", name_en="Despotism", age=Age.A,
    deck=DeckType.CIVIL, category=CardCategory.GOVERNMENT,
    text="4 内政行动 + 2 军事行动; 城市建筑上限 2。",
    government=GovernmentStats(civil_actions=4, military_actions=2,
                               urban_limit=2),
)

INITIAL_CARDS: tuple[CardDefinition, ...] = (
    AGRICULTURE, BRONZE, PHILOSOPHY, RELIGION, WARRIORS, DESPOTISM,
)
