"""时代 II 官方内政牌库(43/50/53 张, 2p/3p/4p).

数值权威来源: Card Reference v1.09(实现者直接转录)。
- 科技/特殊科技/政府/奇迹数值与 2p/3p/4p 张数: PDF 第 1 页;
- 领袖文本: PDF 第 2 页 Leaders 表 Age II 行;
- 行动牌 X 加成: PDF 第 2 页 Actions 表 Bonus 列 Age II 值(X=3,
  engineering_genius X=4, revolutionary_idea X=4); 张数: Quantity 列
  Age II 值(行动牌张数不随人数调整, quantities 三列相同, 同 Age A 约定)。
  时代 II 新增行动牌: efficient_upgrade(仅升级), revolutionary_idea
  (+X 科技), wave_of_nationalism(按更强文明数给兵种建造折扣);
  cultural_heritage / stockpile 无时代 II 实例。

牌堆总数(Σ quantities): 2p = 科技 14 + 特殊 4 + 政府 2 + 奇迹 4 + 领袖 6
+ 行动 13 = 43; 3p = 50; 4p = 53。

行动卡 id 带时代后缀(如 rich_land_ii), handler 名 = 卡 id 全名,
effects.py 按时代实例注册(X 加成各异)。领袖/特殊科技/奇迹的互动能力
(殖民/剧院折扣/矿场翻倍/免费增人口)标 P2-DEFERRED, 仅保留卡文本。
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
        id=card_id, name=name, name_en=name_en, age=Age.II,
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
        id=card_id, name=name, name_en=name_en, age=Age.II,
        deck=DeckType.CIVIL, category=CardCategory.SPECIAL, text=text,
        cost_science=cost_science, special_type=special_type,
        handler=handler, quantities=quantities,
    )


def _government(
    card_id: str, name: str, name_en: str, peaceful: int, revolution: int,
    stats: GovernmentStats, quantities: tuple[int, int, int], text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.II,
        deck=DeckType.CIVIL, category=CardCategory.GOVERNMENT, text=text,
        cost_science=peaceful, cost_science_revolution=revolution,
        government=stats, quantities=quantities,
    )


def _wonder(
    card_id: str, name: str, name_en: str, stages: tuple[int, ...],
    bonus: dict[str, int], text: str, handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.II,
        deck=DeckType.CIVIL, category=CardCategory.WONDER, text=text,
        wonder_stages=stages, wonder_bonus=bonus, handler=handler,
        quantities=_ONE,
    )


def _leader(
    card_id: str, name: str, name_en: str, text: str, handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.II,
        deck=DeckType.CIVIL, category=CardCategory.LEADER, text=text,
        handler=handler, quantities=_ONE,
    )


def _action(
    card_id: str, name: str, name_en: str, count: int, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.II,
        deck=DeckType.CIVIL, category=CardCategory.ACTION, text=text,
        handler=card_id, quantities=(count, count, count),
    )


# --- 科技(PDF 第 1 页 Age II 行) ----------------------------------------------

SELECTIVE_BREEDING = _tech(
    "selective_breeding", "选择育种", "Selective Breeding", CardCategory.FARM,
    5, 6, (1, 2, 3), "每个蓝色方块 = 3 食物。", token_value=3,
)

COAL = _tech(
    "coal", "煤炭", "Coal", CardCategory.MINE,
    7, 8, (1, 2, 2), "每个蓝色方块 = 3 资源。", token_value=3,
)

SCIENTIFIC_METHOD = _tech(
    "scientific_method", "科学方法", "Scientific Method", CardCategory.LAB,
    6, 8, (2, 2, 2), "每个实验室工人产出 3 科技。",
    urban_produces={"science": 3},
)

ORGANIZED_RELIGION = _tech(
    "organized_religion", "宗教组织", "Organized Religion", CardCategory.TEMPLE,
    4, 7, (2, 2, 2), "每个寺庙工人产出 1 文化 + 3 笑脸。",
    urban_produces={"culture": 1, "happiness": 3},
)

TEAM_SPORTS = _tech(
    "team_sports", "团队运动", "Team Sports", CardCategory.ARENA,
    5, 5, (1, 1, 1), "每个竞技场工人产出 2 文化 + 3 笑脸。",
    urban_produces={"culture": 2, "happiness": 3},
)

JOURNALISM = _tech(
    "journalism", "新闻学", "Journalism", CardCategory.LIBRARY,
    6, 8, (1, 2, 2), "每个图书馆工人产出 2 科技 + 2 文化。",
    urban_produces={"science": 2, "culture": 2},
)

OPERA = _tech(
    "opera", "歌剧", "Opera", CardCategory.THEATER,
    7, 8, (1, 2, 2), "每个剧院工人产出 3 文化 + 2 笑脸。",
    urban_produces={"culture": 3, "happiness": 2},
)

RIFLEMEN = _tech(
    "riflemen", "来复枪兵", "Riflemen", CardCategory.INFANTRY,
    6, 5, (1, 2, 2), "每个来复枪兵单位提供 3 军力。", strength=3,
)

CAVALRYMEN = _tech(
    "cavalrymen", "骑兵", "Cavalrymen", CardCategory.CAVALRY,
    6, 5, (2, 2, 2), "每个骑兵单位提供 3 军力。", strength=3,
)

CANNON = _tech(
    "cannon", "加农炮", "Cannon", CardCategory.ARTILLERY,
    6, 5, (2, 2, 3), "每个加农炮单位提供 3 军力。", strength=3,
)

TECHS: tuple[CardDefinition, ...] = (
    SELECTIVE_BREEDING, COAL, SCIENTIFIC_METHOD, ORGANIZED_RELIGION,
    TEAM_SPORTS, JOURNALISM, OPERA, RIFLEMEN, CAVALRYMEN, CANNON,
)

# --- 特殊科技(PDF 第 1 页 Special 区 Age II 行) ---------------------------------

STRATEGY = _special(
    "strategy", "战略", "Strategy", SpecialType.WARFARE,
    8, _ONE, "+3 军力, +2 军事行动。", handler="strategy",
)

JUSTICE_SYSTEM = _special(
    "justice_system", "司法系统", "Justice System", SpecialType.LAW,
    7, _ONE, "+1 内政行动; 研发时立即获得 3 个蓝色方块。",
    handler="justice_system",
)

NAVIGATION = _special(
    "navigation", "航海术", "Navigation", SpecialType.EXPLORATION,
    6, _ONE, "+2 殖民修正, +3 军力(殖民 P2-DEFERRED)。",
    handler="navigation",
)

ARCHITECTURE = _special(
    "architecture", "建筑学", "Architecture", SpecialType.CONSTRUCTION,
    6, (1, 2, 2),
    "每个内政行动可建造奇迹的 3 个阶段; 建造/升级城市建筑每级少付 1 资源"
    "(最多 2)(建造折扣与三阶段 P2-DEFERRED)。",
)

SPECIALS: tuple[CardDefinition, ...] = (
    STRATEGY, JUSTICE_SYSTEM, NAVIGATION, ARCHITECTURE,
)

# --- 政府(PDF 第 1 页 Government 区; 费用格式 革命(和平)) -----------------------

REPUBLIC = _government(
    "republic", "共和制", "Republic", 13, 3,
    GovernmentStats(civil_actions=7, military_actions=2, urban_limit=3),
    (1, 1, 2), "7 内政行动 + 2 军事行动; 城市建筑上限 3。",
)

CONSTITUTIONAL_MONARCHY = _government(
    "constitutional_monarchy", "君主立宪制", "Constitutional Monarchy", 12, 6,
    GovernmentStats(civil_actions=6, military_actions=4, urban_limit=3),
    (1, 2, 2), "6 内政行动 + 4 军事行动; 城市建筑上限 3。",
)

GOVERNMENTS: tuple[CardDefinition, ...] = (REPUBLIC, CONSTITUTIONAL_MONARCHY)

# --- 奇迹(PDF 第 1 页 Wonder 区 Age II 行) --------------------------------------

TRANSCONTINENTAL_RAILROAD = _wonder(
    "transcontinental_railroad", "横贯大陆铁路", "Transcontinental Railroad",
    (3, 3, 3, 3), {"strength": 4},
    "+4 军力; 你最佳的矿场产出翻倍(产出翻倍 P2-DEFERRED)。",
)

EIFFEL_TOWER = _wonder(
    "eiffel_tower", "埃菲尔铁塔", "Eiffel Tower", (3, 7, 3),
    {"culture": 4, "happiness": 1}, "+4 文化, +1 笑脸。",
)

KREMLIN = _wonder(
    "kremlin", "克里姆林宫", "Kremlin", (4, 4, 4),
    {"culture": 2, "civil_actions": 1, "military_actions": 1, "happiness": -1},
    "+2 文化, +1 内政行动, +1 军事行动, -1 笑脸。",
)

OCEAN_LINER_SERVICE = _wonder(
    "ocean_liner_service", "远洋客轮服务", "Ocean Liner Service", (4, 2, 2, 4),
    {},
    "每回合一次, 你可增加 1 个人口, 不花内政行动也不付食物"
    "(免费增人口 P2-DEFERRED)。",
)

WONDERS: tuple[CardDefinition, ...] = (
    TRANSCONTINENTAL_RAILROAD, EIFFEL_TOWER, KREMLIN, OCEAN_LINER_SERVICE,
)

# --- 领袖(PDF 第 2 页 Leaders 表 Age II 行) -------------------------------------

WILLIAM_SHAKESPEARE = _leader(
    "william_shakespeare", "威廉·莎士比亚", "William Shakespeare",
    "+1 笑脸; 每有一对图书馆与剧院, +2 文化; 若你有图书馆, 剧院少花 "
    "1 内政行动与 1 资源, 反之亦然(配对文化已实现: 图书馆按已研发、剧院"
    "按有工人卡; 折扣 P2-DEFERRED)。",
    handler="william_shakespeare",
)

JAMES_COOK = _leader(
    "james_cook", "詹姆斯·库克", "James Cook",
    "你的第一个殖民地 +2 殖民修正, 其余 +1(殖民 P2-DEFERRED); 每回合可弃"
    "至多 2 张军事牌, 每张 +1 军力(军事牌互动 P2-DEFERRED)。",
)

NAPOLEON_BONAPARTE = _leader(
    "napoleon_bonaparte", "拿破仑·波拿巴", "Napoleon Bonaparte",
    "+2 军事行动; 你每有一种军事单位类型, +2 军力。",
    handler="napoleon_bonaparte",
)

MAXIMILIEN_ROBESPIERRE = _leader(
    "maximilien_robespierre", "马克西米连·罗伯斯庇尔",
    "Maximilien Robespierre",
    "+1 军事行动; 革命花费全部军事行动(而非全部内政行动); 革命时 "
    "+3 笑脸(一次性笑脸 P2-DEFERRED)。",
    handler="maximilien_robespierre",
)

J_S_BACH = _leader(
    "j_s_bach", "约翰·塞巴斯蒂安·巴赫", "J.S. Bach",
    "你的每个剧院 +1 文化; 剧院少花 2 内政行动; 每回合一次, 可用 1 内政"
    "行动把任一城市建筑升级为同级或高一级的剧院(剧院折扣与升级能力 "
    "P2-DEFERRED)。",
    handler="j_s_bach",
)

ISAAC_NEWTON = _leader(
    "isaac_newton", "艾萨克·牛顿", "Isaac Newton",
    "你最佳的实验室或图书馆每级 +1 科技(级 = 时代序, 时代 A 计 1 级); "
    "每当你研发一项科技, 拿回 1 内政行动。",
    handler="isaac_newton",
)

LEADERS: tuple[CardDefinition, ...] = (
    WILLIAM_SHAKESPEARE, JAMES_COOK, NAPOLEON_BONAPARTE,
    MAXIMILIEN_ROBESPIERRE, J_S_BACH, ISAAC_NEWTON,
)

# --- 行动牌(PDF 第 2 页 Actions 表; X = Bonus 列 Age II 值) ----------------------

BREAKTHROUGH_II = _action(
    "breakthrough_ii", "突破", "Breakthrough", 2,
    "以全价研发一项科技, 然后 +3 科技分。",
)

EFFICIENT_UPGRADE_II = _action(
    "efficient_upgrade_ii", "高效升级", "Efficient Upgrade", 2,
    "升级 1 个农场、矿场或城市建筑, 少付 3 资源。",
)

ENGINEERING_GENIUS_II = _action(
    "engineering_genius_ii", "工程天才", "Engineering Genius", 1,
    "建造奇迹的 1 个阶段, 少付 4 资源。",
)

FRUGALITY_II = _action(
    "frugality_ii", "节俭", "Frugality", 1,
    "增加你的人口(支付全部食物费), 然后获得 3 食物。",
)

PATRIOTISM_II = _action(
    "patriotism_ii", "爱国主义", "Patriotism", 1,
    "本回合你多 1 个军事行动, 且建造/升级军事单位时额外有 3 资源可用。",
)

RESERVES_II = _action(
    "reserves_ii", "储备物资", "Reserves", 2,
    "获得 3 资源或 3 食物。",
)

REVOLUTIONARY_IDEA_II = _action(
    "revolutionary_idea_ii", "革命思想", "Revolutionary Idea", 1,
    "获得 4 科技分。",
)

RICH_LAND_II = _action(
    "rich_land_ii", "沃土", "Rich Land", 1,
    "建造或升级 1 个农场或矿场, 少付 3 资源。",
)

URBAN_GROWTH_II = _action(
    "urban_growth_ii", "城市扩张", "Urban Growth", 1,
    "建造或升级 1 个城市建筑, 少付 3 资源。",
)

WAVE_OF_NATIONALISM_II = _action(
    "wave_of_nationalism_ii", "民族主义浪潮", "Wave of Nationalism", 1,
    "每个比你强的文明使你在本回合建造军事单位时额外有 6/3/2 资源可用"
    "(2/3/4 人局)。",
)

ACTIONS: tuple[CardDefinition, ...] = (
    BREAKTHROUGH_II, EFFICIENT_UPGRADE_II, ENGINEERING_GENIUS_II,
    FRUGALITY_II, PATRIOTISM_II, RESERVES_II, REVOLUTIONARY_IDEA_II,
    RICH_LAND_II, URBAN_GROWTH_II, WAVE_OF_NATIONALISM_II,
)

AGE_II_CARDS: tuple[CardDefinition, ...] = (
    TECHS + SPECIALS + GOVERNMENTS + WONDERS + LEADERS + ACTIONS
)
