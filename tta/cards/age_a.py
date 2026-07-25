"""时代 A 官方牌库(20 张): 6 领袖 + 4 奇迹 + 10 行动牌.

数值权威来源: Card Reference v1.09 第 1-2 页(实现者直接转录)。
- 领袖文本: PDF 第 2 页 Leaders 表 Age A 行;
- 奇迹阶段费: PDF 第 1 页 Wonder 区;
- 行动牌张数: PDF 第 2 页 Actions 表 Quantity 列 Age A 值(时代 A 牌堆
  不随人数调整, 官方规则书 Deck Setup, 故 quantities 三列相同);
- 行动牌 X 加成: PDF Bonus 列 Age A 值, 已硬编码于 effects.py 的
  Age A handler(stockpile/frugality/patriotism/rich_land/urban_growth
  X=1, engineering_genius X=2, cultural_heritage +1 科技 +4 文化)。

与 research §4 的两处冲突(以 PDF 为准): frugality ×2(research ×1)、
cultural_heritage ×1(research ×2); 两者此消彼长, 行动牌总数仍为 10。
"""

from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDefinition

_ONE = (1, 1, 1)


def _leader(
    card_id: str, name: str, name_en: str, text: str, handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.A,
        deck=DeckType.CIVIL, category=CardCategory.LEADER, text=text,
        handler=handler, quantities=_ONE,
    )


def _wonder(
    card_id: str, name: str, name_en: str, stages: tuple[int, ...],
    bonus: dict[str, int], text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.A,
        deck=DeckType.CIVIL, category=CardCategory.WONDER, text=text,
        wonder_stages=stages, wonder_bonus=bonus, quantities=_ONE,
    )


def _action(
    card_id: str, name: str, name_en: str, count: int, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.A,
        deck=DeckType.CIVIL, category=CardCategory.ACTION, text=text,
        handler=card_id, quantities=(count, count, count),
    )


# --- 领袖(PDF 第 2 页 Leaders 表; 政治行动类能力 P2-DEFERRED) -----------------

ALEXANDER_THE_GREAT = _leader(
    "alexander_the_great", "亚历山大大帝", "Alexander the Great",
    "你的每个军事单位为你提供 +1 军力。作为政治行动, 可将此牌移出游戏并"
    "从供应堆拿 1 个黄色方块放入黄色银行(政治行动 P2-DEFERRED)。",
    handler="alexander_the_great",
)

ARISTOTLE = _leader(
    "aristotle", "亚里士多德", "Aristotle",
    "每当你从卡牌列拿取一张科技牌, 你获得 1 科技分。",
)

HAMMURABI = _leader(
    "hammurabi", "汉谟拉比", "Hammurabi",
    "每回合一次, 你可以把 1 个军事行动当作内政行动使用(SIMPLIFICATION: "
    "白点不足支付白点费用时可用红点 1:1 垫付)。从卡牌列拿取领袖牌少花 "
    "1 内政行动。",
)

HOMER = _leader(
    "homer", "荷马", "Homer",
    "+1 笑脸。你的回合中, 建造/升级军事单位时额外有 1 资源可用。当你替换"
    "掉荷马时, 可将此牌滑入 1 个已完成奇迹下方(使其多 1 笑脸)而不拿回"
    "该内政行动(替换滑入 P2-DEFERRED)。",
    handler="homer",
)

JULIUS_CAESAR = _leader(
    "julius_caesar", "尤利乌斯·凯撒", "Julius Caesar",
    "+1 军力, +1 军事行动。每局游戏一次, 你打出政治行动后可以再打出 1 "
    "个政治行动(双政治行动 P2-DEFERRED)。",
    handler="julius_caesar",
)

MOSES = _leader(
    "moses", "摩西", "Moses",
    "你增加人口少花 1 食物。",
)

LEADERS: tuple[CardDefinition, ...] = (
    ALEXANDER_THE_GREAT, ARISTOTLE, HAMMURABI, HOMER, JULIUS_CAESAR, MOSES,
)

# --- 奇迹(PDF 第 1 页 Wonder 区) ---------------------------------------------

PYRAMIDS = _wonder(
    "pyramids", "金字塔", "Pyramids", (3, 2, 1),
    {"civil_actions": 1}, "+1 内政行动。",
)

COLOSSUS = _wonder(
    "colossus", "巨像", "Colossus", (3, 3),
    {"strength": 2, "colonization": 1}, "+2 军力, +1 殖民修正。",
)

HANGING_GARDENS = _wonder(
    "hanging_gardens", "空中花园", "Hanging Gardens", (2, 2, 2),
    {"culture": 1, "happiness": 2}, "+1 文化, +2 笑脸。",
)

LIBRARY_OF_ALEXANDRIA = _wonder(
    "library_of_alexandria", "亚历山大图书馆", "Library of Alexandria",
    (1, 4, 1),
    {"culture": 1, "science": 1,
     "civil_hand_extra": 1, "military_hand_extra": 1},
    "+1 文化, +1 科技; 你的内政与军事手牌上限各 +1。",
)

WONDERS: tuple[CardDefinition, ...] = (
    PYRAMIDS, COLOSSUS, HANGING_GARDENS, LIBRARY_OF_ALEXANDRIA,
)

# --- 行动牌(PDF 第 2 页 Actions 表, 张数 = Quantity 列 Age A 值) --------------

STOCKPILE = _action(
    "stockpile", "储备", "Stockpile", 1,
    "获得 1 资源和 1 食物。",
)

FRUGALITY = _action(
    "frugality", "节俭", "Frugality", 2,
    "增加你的人口(支付全部食物费), 然后获得 1 食物。",
)

ENGINEERING_GENIUS = _action(
    "engineering_genius", "工程天才", "Engineering Genius", 1,
    "建造奇迹的 1 个阶段, 少付 2 资源。",
)

PATRIOTISM = _action(
    "patriotism", "爱国主义", "Patriotism", 1,
    "本回合你多 1 个军事行动, 且建造/升级军事单位时额外有 1 资源可用。",
)

RICH_LAND = _action(
    "rich_land", "沃土", "Rich Land", 2,
    "建造或升级 1 个农场或矿场, 少付 1 资源。",
)

URBAN_GROWTH = _action(
    "urban_growth", "城市扩张", "Urban Growth", 2,
    "建造或升级 1 个城市建筑, 少付 1 资源。",
)

CULTURAL_HERITAGE = _action(
    "cultural_heritage", "文化遗产", "Cultural Heritage", 1,
    "获得 1 科技分和 4 文化分。",
)

ACTIONS: tuple[CardDefinition, ...] = (
    STOCKPILE, FRUGALITY, ENGINEERING_GENIUS, PATRIOTISM, RICH_LAND,
    URBAN_GROWTH, CULTURAL_HERITAGE,
)

AGE_A_CARDS: tuple[CardDefinition, ...] = LEADERS + WONDERS + ACTIONS
