"""卡牌定义与卡牌数据库(纯数据, 无行为)."""

from dataclasses import dataclass, field

from tta.engine.enums import Age, CardCategory, DeckType


@dataclass(frozen=True)
class GovernmentStats:
    """政体数值."""

    civil_actions: int
    military_actions: int
    civil_hand_limit: int
    military_hand_limit: int


@dataclass(frozen=True)
class CardDefinition:
    """一张卡的静态定义.

    produces/gains 的键为资源名字符串:
    "food" / "materials" / "science" / "culture" / "strength" / "happiness".
    """

    id: str
    name: str
    age: Age
    deck: DeckType
    category: CardCategory
    text: str = ""
    cost_science: int = 0        # 研发所需科技点(政体/科技类)
    build_cost: int = 0          # 在其上放置 1 个工人所需资源
    produces: dict[str, int] = field(default_factory=dict)   # 每工人产出
    government: GovernmentStats | None = None                # 政体卡专有
    gains: dict[str, int] = field(default_factory=dict)      # 行动卡一次性收益


@dataclass(frozen=True)
class CardDB:
    """一套牌库: 卡牌定义 + 各时代牌堆(卡牌 id, 可重复表示多张)."""

    cards: dict[str, CardDefinition]
    civil_decks: dict[Age, tuple[str, ...]]
    initial_tableau: tuple[str, ...]   # 每名玩家开局已研发的建筑卡 id(含重复)
    initial_government: str            # 开局政体卡 id

    def get(self, card_id: str) -> CardDefinition:
        """按 id 取卡牌定义."""
        return self.cards[card_id]
