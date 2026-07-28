"""时代 I 官方内政牌库(44/50/53 张, 2p/3p/4p).

数值权威来源: Card Reference v1.09(实现者直接转录)。
- 科技/特殊科技/政府/奇迹数值与 2p/3p/4p 张数: PDF 第 1 页;
- 领袖文本: PDF 第 2 页 Leaders 表 Age I 行;
- 行动牌 X 加成: PDF 第 2 页 Actions 表 Bonus 列 Age I 值(X=2,
  engineering_genius X=3); 张数: Quantity 列 Age I 值(行动牌张数不随
  人数调整, quantities 三列相同, 同 Age A 约定)。

牌堆总数(Σ quantities): 2p = 科技 15 + 特殊 4 + 政府 2 + 奇迹 4 + 领袖 6
+ 行动 13 = 44; 3p = 50; 4p = 53。

行动卡 id 带时代后缀(如 rich_land_i), handler 名 = 卡 id 全名,
effects.py 按时代实例注册(X 加成各异)。领袖/特殊科技/奇迹的互动能力
(殖民/阵型/政治/建造折扣)标 P2-DEFERRED, 仅保留卡文本。
"""

from tta.engine.enums import Age, CardCategory, DeckType, SpecialType
from tta.engine.model import CardDefinition, GovernmentStats

_ONE = (1, 1, 1)


def _tech(
    card_id: str, name: str, name_en: str, category: CardCategory,
    cost_science: int, build_cost: int, quantities: tuple[int, int, int],
    text: str, token_value: int = 0, strength: int = 0,
    urban_produces: dict[str, int] | None = None,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.I,
        deck=DeckType.CIVIL, category=category, text=text,
        cost_science=cost_science, build_cost=build_cost,
        token_value=token_value, strength=strength,
        urban_produces=urban_produces or {}, quantities=quantities,
    )


def _special(
    card_id: str, name: str, name_en: str, special_type: SpecialType,
    cost_science: int, quantities: tuple[int, int, int], text: str,
    handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.I,
        deck=DeckType.CIVIL, category=CardCategory.SPECIAL, text=text,
        cost_science=cost_science, special_type=special_type,
        handler=handler, quantities=quantities,
    )


def _government(
    card_id: str, name: str, name_en: str, peaceful: int, revolution: int,
    stats: GovernmentStats, quantities: tuple[int, int, int], text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.I,
        deck=DeckType.CIVIL, category=CardCategory.GOVERNMENT, text=text,
        cost_science=peaceful, cost_science_revolution=revolution,
        government=stats, quantities=quantities,
    )


def _wonder(
    card_id: str, name: str, name_en: str, stages: tuple[int, ...],
    bonus: dict[str, int], text: str, handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.I,
        deck=DeckType.CIVIL, category=CardCategory.WONDER, text=text,
        wonder_stages=stages, wonder_bonus=bonus, handler=handler,
        quantities=_ONE,
    )


def _leader(
    card_id: str, name: str, name_en: str, text: str, handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.I,
        deck=DeckType.CIVIL, category=CardCategory.LEADER, text=text,
        handler=handler, quantities=_ONE,
    )


def _action(
    card_id: str, name: str, name_en: str, count: int, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.I,
        deck=DeckType.CIVIL, category=CardCategory.ACTION, text=text,
        handler=card_id, quantities=(count, count, count),
    )


# --- 科技(PDF 第 1 页 Age I 行) ----------------------------------------------

IRRIGATION = _tech(
    "irrigation", "灌溉", "Irrigation", CardCategory.FARM,
    3, 4, (2, 2, 2), "每个蓝色方块 = 2 食物。", token_value=2,
)

IRON = _tech(
    "iron", "铁器", "Iron", CardCategory.MINE,
    5, 5, (2, 2, 3), "每个蓝色方块 = 2 资源。", token_value=2,
)

ALCHEMY = _tech(
    "alchemy", "炼金术", "Alchemy", CardCategory.LAB,
    4, 6, (2, 2, 3), "每个实验室工人产出 2 科技。",
    urban_produces={"science": 2},
)

THEOLOGY = _tech(
    "theology", "神学", "Theology", CardCategory.TEMPLE,
    2, 5, (1, 2, 2), "每个寺庙工人产出 1 文化 + 2 笑脸。",
    urban_produces={"culture": 1, "happiness": 2},
)

BREAD_AND_CIRCUSES = _tech(
    "bread_and_circuses", "面包与马戏", "Bread & Circuses", CardCategory.ARENA,
    3, 3, (1, 2, 2), "每个竞技场工人产出 1 文化 + 2 笑脸。",
    urban_produces={"culture": 1, "happiness": 2},
)

PRINTING_PRESS = _tech(
    "printing_press", "印刷术", "Printing Press", CardCategory.LIBRARY,
    3, 3, (2, 2, 2), "每个图书馆工人产出 1 科技 + 1 文化。",
    urban_produces={"science": 1, "culture": 1},
)

DRAMA = _tech(
    "drama", "戏剧", "Drama", CardCategory.THEATER,
    3, 4, (1, 2, 2), "每个剧院工人产出 2 文化 + 1 笑脸。",
    urban_produces={"culture": 2, "happiness": 1},
)

SWORDSMEN = _tech(
    "swordsmen", "剑士", "Swordsmen", CardCategory.INFANTRY,
    4, 3, (2, 2, 2), "每个剑士单位提供 2 军力。", strength=2,
)

KNIGHTS = _tech(
    "knights", "骑士", "Knights", CardCategory.CAVALRY,
    5, 3, (2, 2, 3), "每个骑士单位提供 2 军力。", strength=2,
)

TECHS: tuple[CardDefinition, ...] = (
    IRRIGATION, IRON, ALCHEMY, THEOLOGY, BREAD_AND_CIRCUSES, PRINTING_PRESS,
    DRAMA, SWORDSMEN, KNIGHTS,
)

# --- 特殊科技(PDF 第 1 页 Special 区 Age I 行) ---------------------------------

WARFARE = _special(
    "warfare", "战法", "Warfare", SpecialType.WARFARE,
    5, (1, 2, 2), "+1 军力, +1 军事行动。", handler="warfare",
)

CODE_OF_LAWS = _special(
    "code_of_laws", "法典", "Code of Laws", SpecialType.LAW,
    6, (1, 2, 2), "+1 内政行动。", handler="code_of_laws",
)

CARTOGRAPHY = _special(
    "cartography", "制图学", "Cartography", SpecialType.EXPLORATION,
    4, _ONE, "+1 殖民修正; 殖民少花 2(殖民 P2-DEFERRED)。",
    handler="cartography",
)

MASONRY = _special(
    "masonry", "石匠术", "Masonry", SpecialType.CONSTRUCTION,
    3, _ONE,
    "每个内政行动可建造奇迹的至多 2 个阶段; 建造/升级城市建筑每级少付 "
    "1 资源(最多 1; 级 = 时代序, 时代 A 计 0 级, 升级按双边折后差价)。",
)

SPECIALS: tuple[CardDefinition, ...] = (
    WARFARE, CODE_OF_LAWS, CARTOGRAPHY, MASONRY,
)

# --- 政府(PDF 第 1 页 Government 区; 费用格式 革命(和平)) -----------------------

THEOCRACY = _government(
    "theocracy", "神权政治", "Theocracy", 6, 1,
    GovernmentStats(civil_actions=4, military_actions=3, urban_limit=3,
                    bonus={"culture": 1, "strength": 1, "happiness": 1}),
    _ONE, "4 内政行动 + 3 军事行动; 城市建筑上限 3; +1 文化, +1 军力, +1 笑脸。",
)

MONARCHY = _government(
    "monarchy", "君主制", "Monarchy", 8, 2,
    GovernmentStats(civil_actions=5, military_actions=3, urban_limit=3),
    (1, 2, 2), "5 内政行动 + 3 军事行动; 城市建筑上限 3。",
)

GOVERNMENTS: tuple[CardDefinition, ...] = (THEOCRACY, MONARCHY)

# --- 奇迹(PDF 第 1 页 Wonder 区 Age I 行) --------------------------------------

GREAT_WALL = _wonder(
    "great_wall", "长城", "Great Wall", (2, 2, 3, 2),
    {"culture": 1, "happiness": 1},
    "+1 文化, +1 笑脸; 你的每个步兵与炮兵单位 +1 军力。",
    handler="great_wall",
)

ST_PETERS_BASILICA = _wonder(
    "st_peters_basilica", "圣彼得大教堂", "St. Peter's Basilica", (4, 4),
    {"culture": 2, "happiness": 1},
    "+2 文化, +1 笑脸; 其他每个有笑脸的文明 +1 笑脸(互动效果 P2-DEFERRED)。",
)

UNIVERSITAS_CAROLINA = _wonder(
    "universitas_carolina", "卡罗琳娜大学", "Universitas Carolina", (3, 3, 3),
    {"culture": 1, "science": 2}, "+1 文化, +2 科技。",
)

TAJ_MAHAL = _wonder(
    "taj_mahal", "泰姬陵", "Taj Mahal", (2, 4, 2),
    {"culture": 3},
    "+3 文化; 完成时获得 1 个蓝色标记(P2-DEFERRED); 领袖被替换时, 新领袖"
    "少花 2 内政行动(P2-DEFERRED)。",
)

WONDERS: tuple[CardDefinition, ...] = (
    GREAT_WALL, ST_PETERS_BASILICA, UNIVERSITAS_CAROLINA, TAJ_MAHAL,
)

# --- 领袖(PDF 第 2 页 Leaders 表 Age I 行) -------------------------------------

MICHELANGELO = _leader(
    "michelangelo", "米开朗基罗", "Michelangelo",
    "你的寺庙、剧院和奇迹每提供 1 笑脸, +1 文化; 拿奇迹牌时不付每已完成"
    "奇迹 +1 的额外内政行动。",
    handler="michelangelo",
)

JOAN_OF_ARC = _leader(
    "joan_of_arc", "圣女贞德", "Joan of Arc",
    "+1 军事行动, +1 文化; 你的寺庙与政体每提供 1 笑脸, +1 军力。政治"
    "阶段开始时, 可查看下一事件牌(政治行动 P2-DEFERRED)。",
    handler="joan_of_arc",
)

LEONARDO_DA_VINCI = _leader(
    "leonardo_da_vinci", "达芬奇", "Leonardo Da Vinci",
    "你最佳的实验室或图书馆每级 +1 科技(级 = 时代序, 时代 A 计 1 级); "
    "每当你研发一项科技, 获得 1 资源。",
    handler="leonardo_da_vinci",
)

GENGHIS_KHAN = _leader(
    "genghis_khan", "成吉思汗", "Genghis Khan",
    "组阵型时可将步兵视为骑兵(阵型 P2-DEFERRED); 若你为最强的两个文明"
    "之一, +3 军力(强弱判定需全玩家信息, P2-DEFERRED)。",
)

CHRISTOPHER_COLUMBUS = _leader(
    "christopher_columbus", "哥伦布", "Christopher Columbus",
    "作为政治行动, 可将此牌移出游戏并直接从手牌殖民一个地区, 无需牺牲"
    "(殖民 P2-DEFERRED)。",
)

FREDERICK_BARBAROSSA = _leader(
    "frederick_barbarossa", "巴巴罗萨", "Frederick Barbarossa",
    "花 1 个军事行动, 直接从人口银行建造 1 个军事单位, 少付 1 食物与 "
    "1 资源(互动效果 P2-DEFERRED)。",
)

LEADERS: tuple[CardDefinition, ...] = (
    MICHELANGELO, JOAN_OF_ARC, LEONARDO_DA_VINCI, GENGHIS_KHAN,
    CHRISTOPHER_COLUMBUS, FREDERICK_BARBAROSSA,
)

# --- 行动牌(PDF 第 2 页 Actions 表; X = Bonus 列 Age I 值) ----------------------

BREAKTHROUGH_I = _action(
    "breakthrough_i", "突破", "Breakthrough", 2,
    "以全价研发一项科技, 然后 +2 科技分。",
)

CULTURAL_HERITAGE_I = _action(
    "cultural_heritage_i", "文化遗产", "Cultural Heritage", 1,
    "获得 2 科技分和 2 文化分。",
)

ENGINEERING_GENIUS_I = _action(
    "engineering_genius_i", "工程天才", "Engineering Genius", 1,
    "建造奇迹的 1 个阶段, 少付 3 资源。",
)

FRUGALITY_I = _action(
    "frugality_i", "节俭", "Frugality", 2,
    "增加你的人口(支付全部食物费), 然后获得 2 食物。",
)

PATRIOTISM_I = _action(
    "patriotism_i", "爱国主义", "Patriotism", 1,
    "本回合你多 1 个军事行动, 且建造/升级军事单位时额外有 2 资源可用。",
)

RESERVES_I = _action(
    "reserves_i", "储备物资", "Reserves", 2,
    "获得 2 资源或 2 食物。",
)

RICH_LAND_I = _action(
    "rich_land_i", "沃土", "Rich Land", 2,
    "建造或升级 1 个农场或矿场, 少付 2 资源。",
)

URBAN_GROWTH_I = _action(
    "urban_growth_i", "城市扩张", "Urban Growth", 2,
    "建造或升级 1 个城市建筑, 少付 2 资源。",
)

ACTIONS: tuple[CardDefinition, ...] = (
    BREAKTHROUGH_I, CULTURAL_HERITAGE_I, ENGINEERING_GENIUS_I, FRUGALITY_I,
    PATRIOTISM_I, RESERVES_I, RICH_LAND_I, URBAN_GROWTH_I,
)

AGE_I_CARDS: tuple[CardDefinition, ...] = (
    TECHS + SPECIALS + GOVERNMENTS + WONDERS + LEADERS + ACTIONS
)
