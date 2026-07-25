"""卡牌定义与卡牌数据库(纯数据, 无行为)."""

from dataclasses import dataclass, field

from tta.engine.enums import Age, CardCategory, DeckType, SpecialType

MIN_PLAYERS = 2
MAX_PLAYERS = 4


@dataclass(frozen=True)
class GovernmentStats:
    """政体数值.

    bonus 的键为静态文明加成名(如 "science" / "culture" / "strength").
    """

    civil_actions: int
    military_actions: int
    urban_limit: int
    bonus: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CardDefinition:
    """一张卡的静态定义.

    urban_produces / wonder_bonus / GovernmentStats.bonus 的键为收益名字符串:
    "food" / "materials" / "science" / "culture" / "strength" / "happiness".
    """

    id: str
    name: str                       # 中文名
    name_en: str                    # 英文名(对照 Card Reference)
    age: Age
    deck: DeckType
    category: CardCategory
    text: str = ""                  # 效果文本(人类/LLM 阅读)
    cost_science: int = 0           # 科技费(政府牌为和平演变费)
    cost_science_revolution: int = 0  # 政府牌革命费
    build_cost: int = 0             # 放置 1 工人的资源费
    token_value: int = 0            # 农场/矿场: 每蓝点的食物/资源价值
    urban_produces: dict[str, int] = field(default_factory=dict)  # 城市建筑每工人产出
    strength: int = 0               # 军事单位每工人军力
    government: GovernmentStats | None = None
    special_type: SpecialType | None = None
    wonder_stages: tuple[int, ...] = ()   # 奇迹各阶段资源费
    wonder_bonus: dict[str, int] = field(default_factory=dict)  # 奇迹完成后静态文明加成
    handler: str = ""                     # effects.py 特殊效果处理器名, 空=无
    quantities: tuple[int, int, int] = (0, 0, 0)  # (2p, 3p, 4p) 张数
    military_cost: int = 0                # 侵略/战争: 军事行动费
    defense_bonus: int = 0                # 军事奖励牌: 防御加成
    colonize_bonus: int = 0               # 军事奖励牌: 殖民加成
    tactics_units: dict[str, int] = field(default_factory=dict)
    """阵型组成 {单位类别名: 数量}, 键为 CardCategory 名(如 {"INFANTRY": 2})."""
    tactics_strength: int = 0             # 阵型军力
    tactics_strength_outdated: int = 0    # 旧式阵型军力(数值表括号内数字)
    territory_immediate: dict[str, int] = field(default_factory=dict)
    """地区即时效果(如 {"science": 3} / {"military_card": 3} / {"population": 1})."""
    territory_permanent: dict[str, int] = field(default_factory=dict)
    """地区永久效果(如 {"yellow_token": 1, "blue_token": 1} / {"strength": 2})."""


@dataclass(frozen=True)
class CardDB:
    """一套牌库: 卡牌定义 + 开局布局; 各时代牌堆由 deck_for 按 quantities 生成."""

    cards: dict[str, CardDefinition]
    initial_tableau: tuple[str, ...]   # 每名玩家开局已研发的建筑卡 id(含重复)
    initial_government: str            # 开局政体卡 id
    initial_workers: tuple[tuple[str, int], ...] = ()
    """开局各初始科技卡上的工人数((card_id, 数量) 对, 0 工人的卡不在列)."""

    def get(self, card_id: str) -> CardDefinition:
        """按 id 取卡牌定义."""
        return self.cards[card_id]

    def deck_for(self, age: Age, num_players: int,
                 deck_type: DeckType = DeckType.CIVIL) -> tuple[str, ...]:
        """按 quantities 组成指定时代、指定人数的牌堆(卡牌 id, 含重复).

        顺序为 cards 的插入序; num_players 须在 [MIN_PLAYERS, MAX_PLAYERS].
        deck_type 默认 CIVIL(P1 牌库仅内政卡; P2 军事卡入库后须显式过滤).
        """
        if not MIN_PLAYERS <= num_players <= MAX_PLAYERS:
            msg = f"num_players 须在 {MIN_PLAYERS}-{MAX_PLAYERS}, 收到 {num_players}"
            raise ValueError(msg)
        idx = num_players - MIN_PLAYERS
        ids: list[str] = []
        for card in self.cards.values():
            if card.age is age and card.deck is deck_type:
                ids.extend([card.id] * card.quantities[idx])
        return tuple(ids)
