"""时代 III 官方内政牌库(44/50/53 张, 2p/3p/4p).

数值权威来源: Card Reference v1.09(实现者直接转录, 高分辨率图标核对)。
- 科技/特殊科技/政府/奇迹数值与 2p/3p/4p 张数: PDF 第 1 页;
- 领袖文本: PDF 第 2 页 Leaders 表 Age III 行;
- 行动牌 X 加成: PDF 第 2 页 Actions 表 Bonus 列 Age III 值(X=4,
  engineering_genius X=5, revolutionary_idea X=6); 张数: Quantity 列
  Age III 值(行动牌张数不随人数调整, quantities 三列相同, 同 Age A 约定)。
  时代 III 新增行动牌: endowment_for_arts(按文化分更高文明数得分),
  military_build_up(按更强文明数给兵种建造折扣); breakthrough /
  cultural_heritage / frugality / rich_land / stockpile /
  wave_of_nationalism 无时代 III 实例。

牌堆总数(Σ quantities): 2p = 科技 14 + 特殊 4 + 政府 3 + 奇迹 4 + 领袖 6
+ 行动 13 = 44; 3p = 19 + 4 + 4 + 4 + 6 + 13 = 50;
4p = 21 + 5 + 4 + 4 + 6 + 13 = 53。

转录勘正(相对 T12 brief, 以 300 DPI 图标核对为准):
- albert_einstein: 研发科技 +3 为文化(竖琴图标)而非笑脸;
- mahatma_gandhi: 静态 +2 为文化而非笑脸;
- sid_meier: 实验室 -1 为科技(灯泡图标)而非食物;
- pro_sports: 3 文化 + 4 笑脸; multimedia: 3 文化 + 3 科技。
- winston_churchill: 每回合二选一为 +3 文化(PDF 竖琴图标正确,
  官方卡面即 +3 文化)而非 +3 军力。

行动卡 id 带时代后缀(如 reserves_iii), handler 名 = 卡 id 全名,
effects.py 按时代实例注册(X 加成各异)。bill_gates 实验室产资源与被替换
离场奖励、winston_churchill 每回合二选一已于 P3-T4 实现(见
tta/engine/economy.py 与 tta/engine/choices.py)。
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
        id=card_id, name=name, name_en=name_en, age=Age.III,
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
        id=card_id, name=name, name_en=name_en, age=Age.III,
        deck=DeckType.CIVIL, category=CardCategory.SPECIAL, text=text,
        cost_science=cost_science, special_type=special_type,
        handler=handler, quantities=quantities,
    )


def _government(
    card_id: str, name: str, name_en: str, peaceful: int, revolution: int,
    stats: GovernmentStats, quantities: tuple[int, int, int], text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.III,
        deck=DeckType.CIVIL, category=CardCategory.GOVERNMENT, text=text,
        cost_science=peaceful, cost_science_revolution=revolution,
        government=stats, quantities=quantities,
    )


def _wonder(
    card_id: str, name: str, name_en: str, stages: tuple[int, ...],
    bonus: dict[str, int], text: str, handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.III,
        deck=DeckType.CIVIL, category=CardCategory.WONDER, text=text,
        wonder_stages=stages, wonder_bonus=bonus, handler=handler,
        quantities=_ONE,
    )


def _leader(
    card_id: str, name: str, name_en: str, text: str, handler: str = "",
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.III,
        deck=DeckType.CIVIL, category=CardCategory.LEADER, text=text,
        handler=handler, quantities=_ONE,
    )


def _action(
    card_id: str, name: str, name_en: str, count: int, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=Age.III,
        deck=DeckType.CIVIL, category=CardCategory.ACTION, text=text,
        handler=card_id, quantities=(count, count, count),
    )


# --- 科技(PDF 第 1 页 Age III 行) ---------------------------------------------

MECHANIZED_AGRICULTURE = _tech(
    "mechanized_agriculture", "机械化农业", "Mechanized Agriculture",
    CardCategory.FARM, 7, 8, (1, 2, 2), "每个蓝色方块 = 5 食物。",
    token_value=5,
)

OIL = _tech(
    "oil", "石油", "Oil", CardCategory.MINE,
    9, 11, (1, 2, 2), "每个蓝色方块 = 5 资源。", token_value=5,
)

COMPUTERS = _tech(
    "computers", "计算机", "Computers", CardCategory.LAB,
    8, 11, (2, 2, 2), "每个实验室工人产出 5 科技。",
    urban_produces={"science": 5},
)

PRO_SPORTS = _tech(
    "pro_sports", "职业体育", "Pro. Sports", CardCategory.ARENA,
    7, 8, (1, 1, 2), "每个竞技场工人产出 3 文化 + 4 笑脸。",
    urban_produces={"culture": 3, "happiness": 4},
)

MULTIMEDIA = _tech(
    "multimedia", "多媒体", "Multimedia", CardCategory.LIBRARY,
    9, 11, (2, 2, 2), "每个图书馆工人产出 3 科技 + 3 文化。",
    urban_produces={"culture": 3, "science": 3},
)

MOVIES = _tech(
    "movies", "电影", "Movies", CardCategory.THEATER,
    10, 11, (2, 2, 2), "每个剧院工人产出 4 文化 + 1 笑脸。",
    urban_produces={"culture": 4, "happiness": 1},
)

MODERN_INFANTRY = _tech(
    "modern_infantry", "现代化步兵", "Modern Infantry", CardCategory.INFANTRY,
    10, 7, (1, 2, 2), "每个现代化步兵单位提供 5 军力。", strength=5,
)

TANKS = _tech(
    "tanks", "坦克", "Tanks", CardCategory.CAVALRY,
    9, 7, (1, 2, 2), "每个坦克单位提供 5 军力。", strength=5,
)

ROCKETS = _tech(
    "rockets", "火箭", "Rockets", CardCategory.ARTILLERY,
    8, 7, (1, 2, 2), "每个火箭单位提供 5 军力。", strength=5,
)

AIR_FORCES = _tech(
    "air_forces", "空军", "Air Forces", CardCategory.AIR,
    12, 7, (2, 2, 3),
    "每个空军单位提供 5 军力。",
    strength=5,
)

TECHS: tuple[CardDefinition, ...] = (
    MECHANIZED_AGRICULTURE, OIL, COMPUTERS, PRO_SPORTS, MULTIMEDIA, MOVIES,
    MODERN_INFANTRY, TANKS, ROCKETS, AIR_FORCES,
)

# --- 特殊科技(PDF 第 1 页 Special 区 Age III 行) --------------------------------

MILITARY_THEORY = _special(
    "military_theory", "军事理论", "Military Theory", SpecialType.WARFARE,
    11, (1, 1, 2), "+5 军力, +3 军事行动。", handler="military_theory",
)

CIVIL_SERVICE = _special(
    "civil_service", "文官制度", "Civil Service", SpecialType.LAW,
    10, _ONE, "+2 内政行动; 研发时立即获得 3 个蓝色方块。",
    handler="civil_service",
)

SATELLITES = _special(
    "satellites", "卫星", "Satellites", SpecialType.EXPLORATION,
    8, _ONE, "+3 军力, +4 殖民修正(殖民 P2-DEFERRED)。",
    handler="satellites",
)

ENGINEERING = _special(
    "engineering", "工程学", "Engineering", SpecialType.CONSTRUCTION,
    9, _ONE,
    "每个内政行动可建造奇迹的 4 个阶段; 建造/升级城市建筑每级少付 1 资源"
    "(最多 3)(建造折扣与四阶段 P2-DEFERRED)。",
)

SPECIALS: tuple[CardDefinition, ...] = (
    MILITARY_THEORY, CIVIL_SERVICE, SATELLITES, ENGINEERING,
)

# --- 政府(PDF 第 1 页 Government 区; 费用格式 革命(和平)) -----------------------

COMMUNISM = _government(
    "communism", "共产主义", "Communism", 19, 5,
    GovernmentStats(civil_actions=7, military_actions=5, urban_limit=4,
                    bonus={"happiness": -1}),
    _ONE, "7 内政行动 + 5 军事行动; 城市建筑上限 4; -1 笑脸。",
)

FUNDAMENTALISM = _government(
    "fundamentalism", "原教旨主义", "Fundamentalism", 18, 7,
    GovernmentStats(civil_actions=6, military_actions=5, urban_limit=4,
                    bonus={"science": -2, "strength": 5}),
    _ONE, "6 内政行动 + 5 军事行动; 城市建筑上限 4; +5 军力, -2 科技。",
)

DEMOCRACY = _government(
    "democracy", "民主制", "Democracy", 17, 9,
    GovernmentStats(civil_actions=7, military_actions=3, urban_limit=4,
                    bonus={"culture": 3}),
    (1, 2, 2), "7 内政行动 + 3 军事行动; 城市建筑上限 4; +3 文化。",
)

GOVERNMENTS: tuple[CardDefinition, ...] = (COMMUNISM, FUNDAMENTALISM, DEMOCRACY)

# --- 奇迹(PDF 第 1 页 Wonder 区 Age III 行) -------------------------------------

HOLLYWOOD = _wonder(
    "hollywood", "好莱坞", "Hollywood", (5, 6, 5), {},
    "建成时立即得分: 你的每个剧院与图书馆每 1 点文化产出计 2 文化"
    "(一次性得分, 奇迹建成触发 P2-DEFERRED)。",
)

INTERNET = _wonder(
    "internet", "互联网", "Internet", (2, 3, 4, 3, 2), {},
    "你的每个城市建筑每产出 1 科技或文化, 额外 +1 文化。",
    handler="internet",
)

FIRST_SPACE_FLIGHT = _wonder(
    "first_space_flight", "首次太空飞行", "First Space Flight", (1, 2, 4, 9),
    {}, "你的每项科技每级 +1 文化。", handler="first_space_flight",
)

FAST_FOOD_CHAINS = _wonder(
    "fast_food_chains", "快餐连锁", "Fast Food Chains", (4, 4, 4, 4), {},
    "你的每个农场与矿场 +2 文化; 每个城市建筑与军事单位 +1 文化。",
    handler="fast_food_chains",
)

WONDERS: tuple[CardDefinition, ...] = (
    HOLLYWOOD, INTERNET, FIRST_SPACE_FLIGHT, FAST_FOOD_CHAINS,
)

# --- 领袖(PDF 第 2 页 Leaders 表 Age III 行) ------------------------------------

ALBERT_EINSTEIN = _leader(
    "albert_einstein", "阿尔伯特·爱因斯坦", "Albert Einstein",
    "你最佳的实验室或图书馆每级 +1 科技(级 = 时代序, 时代 A 计 1 级); "
    "每当你研发一项科技, +3 文化。",
    handler="albert_einstein",
)

MAHATMA_GANDHI = _leader(
    "mahatma_gandhi", "圣雄甘地", "Mahatma Gandhi",
    "+2 文化; 你不能打出侵略或战争牌; 针对你的侵略与战争花费双倍军事行动"
    "(军事互动 P2-DEFERRED)。",
    handler="mahatma_gandhi",
)

CHARLIE_CHAPLIN = _leader(
    "charlie_chaplin", "查理·卓别林", "Charlie Chaplin",
    "+2 笑脸; 你最佳的剧院产出双倍文化。",
    handler="charlie_chaplin",
)

BILL_GATES = _leader(
    "bill_gates", "比尔·盖茨", "Bill Gates",
    "你的实验室每级产出 1 资源; 当他离场或游戏结束时, +文化等于该额外产出"
    "(产资源见 economy; 被替换离场即时结算见 effects.gates_lab_bonus_culture; "
    "终局见 events._bill_gates_endgame)。",
)

WINSTON_CHURCHILL = _leader(
    "winston_churchill", "温斯顿·丘吉尔", "Winston Churchill",
    "你的回合开始时二选一: +3 文化; 或本回合军事用途有 3 科技与 3 资源"
    "(回合开始选择机制见 choices)。",
)

SID_MEIER = _leader(
    "sid_meier", "席德·梅尔", "Sid Meier",
    "你的实验室每级 +1 文化, 且每个实验室 -1 科技。",
    handler="sid_meier",
)

LEADERS: tuple[CardDefinition, ...] = (
    ALBERT_EINSTEIN, MAHATMA_GANDHI, CHARLIE_CHAPLIN,
    BILL_GATES, WINSTON_CHURCHILL, SID_MEIER,
)

# --- 行动牌(PDF 第 2 页 Actions 表; X = Bonus 列 Age III 值) ---------------------

EFFICIENT_UPGRADE_III = _action(
    "efficient_upgrade_iii", "高效升级", "Efficient Upgrade", 2,
    "升级 1 个农场、矿场或城市建筑, 少付 4 资源。",
)

ENDOWMENT_FOR_ARTS_III = _action(
    "endowment_for_arts_iii", "艺术捐赠", "Endowment for Arts", 1,
    "每个文化分比你高的文明使你 +6/3/2 文化(2/3/4 人局)。",
)

ENGINEERING_GENIUS_III = _action(
    "engineering_genius_iii", "工程天才", "Engineering Genius", 1,
    "建造奇迹的 1 个阶段, 少付 5 资源。",
)

MILITARY_BUILD_UP_III = _action(
    "military_build_up_iii", "军事扩充", "Military Build-Up", 1,
    "每个比你强的文明使你在本回合建造军事单位时额外有 8/5/3 资源可用"
    "(2/3/4 人局)。",
)

PATRIOTISM_III = _action(
    "patriotism_iii", "爱国主义", "Patriotism", 1,
    "本回合你多 1 个军事行动, 且建造/升级军事单位时额外有 4 资源可用。",
)

RESERVES_III = _action(
    "reserves_iii", "储备物资", "Reserves", 3,
    "获得 4 资源或 4 食物。",
)

REVOLUTIONARY_IDEA_III = _action(
    "revolutionary_idea_iii", "革命思想", "Revolutionary Idea", 2,
    "获得 6 科技分。",
)

URBAN_GROWTH_III = _action(
    "urban_growth_iii", "城市扩张", "Urban Growth", 2,
    "建造或升级 1 个城市建筑, 少付 4 资源。",
)

ACTIONS: tuple[CardDefinition, ...] = (
    EFFICIENT_UPGRADE_III, ENDOWMENT_FOR_ARTS_III, ENGINEERING_GENIUS_III,
    MILITARY_BUILD_UP_III, PATRIOTISM_III, RESERVES_III,
    REVOLUTIONARY_IDEA_III, URBAN_GROWTH_III,
)

AGE_III_CARDS: tuple[CardDefinition, ...] = (
    TECHS + SPECIALS + GOVERNMENTS + WONDERS + LEADERS + ACTIONS
)
