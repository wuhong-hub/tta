"""P0 最小牌库: 仅供引擎骨架验证, 非官方数值(全部 RULES-AUDIT).

每时代 17 张: 农场×3 矿场×3 实验室×2 神庙×2 兵种×2 政体×1 行动卡×4.
P1 将被正式牌库与效果原语框架取代; P2 对照规则书核对全部数值.
"""

from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats

_C = DeckType.CIVIL


def _gov(cid: str, name: str, age: Age, sci: int,
         ca: int, ma: int, hc: int, hm: int) -> CardDefinition:
    # RULES-AUDIT: 政体数值
    return CardDefinition(id=cid, name=name, age=age, deck=_C,
                          category=CardCategory.GOVERNMENT, cost_science=sci,
                          government=GovernmentStats(ca, ma, hc, hm))


def _bld(cid: str, name: str, age: Age, cat: CardCategory,
         sci: int, build: int, **produces: int) -> CardDefinition:
    # RULES-AUDIT: 造价/产出数值
    return CardDefinition(id=cid, name=name, age=age, deck=_C, category=cat,
                          cost_science=sci, build_cost=build, produces=produces)


def _act(cid: str, name: str, age: Age, **gains: int) -> CardDefinition:
    # RULES-AUDIT: 行动卡收益
    return CardDefinition(id=cid, name=name, age=age, deck=_C,
                          category=CardCategory.ACTION, gains=gains)


_CARDS: list[CardDefinition] = [
    # 起始台面(不入牌堆)
    _bld("agriculture", "农业", Age.A, CardCategory.FARM, 0, 2, food=2),
    _bld("bronze", "青铜", Age.A, CardCategory.MINE, 0, 2, materials=1),
    _bld("philosophy", "哲学", Age.A, CardCategory.LAB, 0, 3, science=1),
    _gov("despotism", "专制", Age.A, 0, 4, 2, 4, 2),
    # 时代 A
    _bld("irrigation", "灌溉", Age.A, CardCategory.FARM, 2, 2, food=2),
    _bld("iron", "铁器", Age.A, CardCategory.MINE, 2, 2, materials=2),
    _bld("alchemy", "炼金术", Age.A, CardCategory.LAB, 2, 3, science=2),
    _bld("religion", "宗教", Age.A, CardCategory.TEMPLE, 2, 3, happiness=1),
    _bld("swordsmen", "剑士", Age.A, CardCategory.UNIT, 2, 2, strength=2),
    _gov("monarchy", "君主制", Age.A, 2, 5, 3, 5, 3),
    _act("harvest_a", "丰收", Age.A, food=3),
    _act("quarry_a", "采石", Age.A, materials=3),
    # 时代 I
    _bld("selective_breeding", "选育", Age.I, CardCategory.FARM, 4, 3, food=3),
    _bld("coal", "煤炭", Age.I, CardCategory.MINE, 4, 3, materials=3),
    _bld("printing_press", "印刷术", Age.I, CardCategory.LAB, 4, 4, science=3),
    _bld("theology", "神学", Age.I, CardCategory.TEMPLE, 4, 4, happiness=1, culture=1),
    _bld("knights", "骑士", Age.I, CardCategory.UNIT, 4, 3, strength=3),
    _gov("constitutional", "君主立宪", Age.I, 4, 6, 3, 6, 3),
    _act("inspiration_i", "灵感", Age.I, science=3),
    _act("festival_i", "文化节", Age.I, culture=3),
    # 时代 II
    _bld("mechanized_agri", "机械化农业", Age.II, CardCategory.FARM, 7, 4, food=4),
    _bld("oil", "石油", Age.II, CardCategory.MINE, 7, 4, materials=4),
    _bld("scientific_method", "科学方法", Age.II, CardCategory.LAB, 7, 5, science=4),
    _bld("organized_religion", "建制宗教", Age.II, CardCategory.TEMPLE, 7, 5,
         happiness=2, culture=1),
    _bld("riflemen", "步枪兵", Age.II, CardCategory.UNIT, 7, 4, strength=5),
    _gov("republic", "共和制", Age.II, 7, 7, 2, 7, 2),
    _act("harvest_ii", "大丰收", Age.II, food=5),
    _act("industry_ii", "工业化", Age.II, materials=5),
    # 时代 III
    _bld("gmo_food", "基因作物", Age.III, CardCategory.FARM, 10, 5, food=6),
    _bld("synthetics", "合成材料", Age.III, CardCategory.MINE, 10, 5, materials=6),
    _bld("computers", "计算机", Age.III, CardCategory.LAB, 10, 6, science=6),
    _bld("mass_media", "大众传媒", Age.III, CardCategory.TEMPLE, 10, 6,
         happiness=2, culture=2),
    _bld("modern_army", "现代军队", Age.III, CardCategory.UNIT, 10, 5, strength=8),
    _gov("democracy", "民主制", Age.III, 10, 8, 3, 8, 4),
    _act("breakthrough_iii", "科技突破", Age.III, science=6),
    _act("olympics_iii", "奥林匹克", Age.III, culture=6),
]


def _deck(age: Age) -> tuple[str, ...]:
    farm = {Age.A: "irrigation", Age.I: "selective_breeding",
            Age.II: "mechanized_agri", Age.III: "gmo_food"}[age]
    mine = {Age.A: "iron", Age.I: "coal", Age.II: "oil", Age.III: "synthetics"}[age]
    lab = {Age.A: "alchemy", Age.I: "printing_press",
           Age.II: "scientific_method", Age.III: "computers"}[age]
    temple = {Age.A: "religion", Age.I: "theology",
              Age.II: "organized_religion", Age.III: "mass_media"}[age]
    unit = {Age.A: "swordsmen", Age.I: "knights",
            Age.II: "riflemen", Age.III: "modern_army"}[age]
    gov = {Age.A: "monarchy", Age.I: "constitutional",
           Age.II: "republic", Age.III: "democracy"}[age]
    acts = {Age.A: ("harvest_a", "quarry_a"), Age.I: ("inspiration_i", "festival_i"),
            Age.II: ("harvest_ii", "industry_ii"),
            Age.III: ("breakthrough_iii", "olympics_iii")}[age]
    return ((farm,) * 3 + (mine,) * 3 + (lab,) * 2 + (temple,) * 2
            + (unit,) * 2 + (gov,) + (acts[0],) * 2 + (acts[1],) * 2)


MINIMAL_DB = CardDB(
    cards={c.id: c for c in _CARDS},
    civil_decks={age: _deck(age) for age in (Age.A, Age.I, Age.II, Age.III)},
    initial_tableau=("agriculture", "agriculture", "bronze", "philosophy"),
    initial_government="despotism",
)
