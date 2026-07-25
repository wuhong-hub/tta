"""时代 III 官方内政牌库 + 领袖/特殊科技/奇迹/行动卡钩子测试.

数据来源: Card Reference v1.09 第 1 页(科技/政府/特殊科技/奇迹数值与
2p/3p/4p 张数)、第 2 页(领袖全表文本 + 行动牌 X 加成与张数), 300 DPI
图标核对(Einstein +3 为文化、Gandhi +2 为文化、Sid Meier -1 为科技、
Communism 为 -1 笑脸)。

时代 III 内政牌堆总数(按 PDF quantities 计算):
- 2p: 科技 14 + 特殊科技 4 + 政府 3 + 奇迹 4 + 领袖 6 + 行动 13 = 44
- 3p: 科技 19 + 特殊科技 4 + 政府 4 + 奇迹 4 + 领袖 6 + 行动 13 = 50
- 4p: 科技 21 + 特殊科技 5 + 政府 4 + 奇迹 4 + 领袖 6 + 行动 13 = 53
"""

from collections import Counter

import pytest

from tta.cards import build_card_db
from tta.engine import effects
from tta.engine.actions import (
    Build,
    DevelopTech,
    IllegalActionError,
    PlayActionCard,
    Upgrade,
)
from tta.engine.apply import apply
from tta.engine.civ import civ_values
from tta.engine.enums import Age, CardCategory, SpecialType
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB
from tta.engine.state import ROW_SLOTS, GameState, PendingEffect, PlayerState

# PDF 第 1 页 Age III 行
TECH_IDS = (
    "mechanized_agriculture", "oil", "computers", "pro_sports", "multimedia",
    "movies", "modern_infantry", "tanks", "rockets", "air_forces",
)
SPECIAL_IDS = ("military_theory", "civil_service", "satellites", "engineering")
GOVERNMENT_IDS = ("communism", "fundamentalism", "democracy")
WONDER_IDS = ("hollywood", "internet", "first_space_flight", "fast_food_chains")
LEADER_IDS = (
    "albert_einstein", "mahatma_gandhi", "charlie_chaplin",
    "bill_gates", "winston_churchill", "sid_meier",
)
# PDF 第 2 页 Actions 表 Quantity 列 Age III 值
ACTION_QUANTITIES = {
    "efficient_upgrade_iii": 2,
    "endowment_for_arts_iii": 1,
    "engineering_genius_iii": 1,
    "military_build_up_iii": 1,
    "patriotism_iii": 1,
    "reserves_iii": 3,
    "revolutionary_idea_iii": 2,
    "urban_growth_iii": 2,
}
# PDF 第 1 页 2p/3p/4p 张数
CARD_QUANTITIES = {
    "mechanized_agriculture": (1, 2, 2),
    "oil": (1, 2, 2),
    "computers": (2, 2, 2),
    "pro_sports": (1, 1, 2),
    "multimedia": (2, 2, 2),
    "movies": (2, 2, 2),
    "modern_infantry": (1, 2, 2),
    "tanks": (1, 2, 2),
    "rockets": (1, 2, 2),
    "air_forces": (2, 2, 3),
    "military_theory": (1, 1, 2),
    "civil_service": (1, 1, 1),
    "satellites": (1, 1, 1),
    "engineering": (1, 1, 1),
    "communism": (1, 1, 1),
    "fundamentalism": (1, 1, 1),
    "democracy": (1, 2, 2),
}
DECK_TOTALS = {2: 44, 3: 50, 4: 53}

ALL_AGE_III_IDS = (
    TECH_IDS + SPECIAL_IDS + GOVERNMENT_IDS + WONDER_IDS + LEADER_IDS
    + tuple(ACTION_QUANTITIES)
)


@pytest.fixture(scope="module")
def db() -> CardDB:
    return build_card_db()


def _player(**overrides: object) -> PlayerState:
    base: dict = {"name": "P0", "civil_actions": 4, "military_actions": 2}
    base.update(overrides)
    return PlayerState(**base)


def _row(*ids: str | None) -> tuple[str | None, ...]:
    row = list(ids) + [None] * (ROW_SLOTS - len(ids))
    return tuple(row)


def _state(
    player: PlayerState, *others: PlayerState, **overrides: object,
) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.III,
        "current_player": 0,
        "card_row": _row(),
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (player, *(others or (_player(name="P1"),))),
        "rng_state": 0,
    }
    base.update(overrides)
    return GameState(**base)


# --- 牌库组成 ---------------------------------------------------------------


def test_age_iii_deck_totals(db: CardDB) -> None:
    """时代 III 牌堆总数: 2p=44, 3p=50, 4p=53(PDF quantities 求和)."""
    for num_players, total in DECK_TOTALS.items():
        assert len(db.deck_for(Age.III, num_players)) == total


def test_age_iii_deck_composition(db: CardDB) -> None:
    counts = Counter(db.deck_for(Age.III, 4))
    by_category: dict[CardCategory, dict[str, int]] = {}
    for card_id, n in counts.items():
        by_category.setdefault(db.get(card_id).category, {})[card_id] = n
    # 10 种工人科技(时代 III 无寺庙, 新增空军)
    tech_kinds = {
        CardCategory.FARM, CardCategory.MINE, CardCategory.LAB,
        CardCategory.ARENA, CardCategory.LIBRARY, CardCategory.THEATER,
        CardCategory.INFANTRY, CardCategory.CAVALRY, CardCategory.ARTILLERY,
        CardCategory.AIR,
    }
    techs = {
        cid: n for cat in tech_kinds
        for cid, n in by_category.get(cat, {}).items()
    }
    assert set(techs) == set(TECH_IDS)
    assert CardCategory.TEMPLE not in by_category
    assert set(by_category[CardCategory.SPECIAL]) == set(SPECIAL_IDS)
    assert set(by_category[CardCategory.GOVERNMENT]) == set(GOVERNMENT_IDS)
    assert set(by_category[CardCategory.WONDER]) == set(WONDER_IDS)
    assert set(by_category[CardCategory.LEADER]) == set(LEADER_IDS)
    assert by_category[CardCategory.ACTION] == ACTION_QUANTITIES
    assert sum(ACTION_QUANTITIES.values()) == 13
    # 奇迹/领袖各 1 张
    assert all(n == 1 for n in by_category[CardCategory.WONDER].values())
    assert all(n == 1 for n in by_category[CardCategory.LEADER].values())


def test_age_iii_quantities(db: CardDB) -> None:
    """科技/特殊科技/政府张数 = PDF 2p/3p/4p 列."""
    for card_id, quantities in CARD_QUANTITIES.items():
        assert db.get(card_id).quantities == quantities, card_id
    for card_id in (*WONDER_IDS, *LEADER_IDS):
        assert db.get(card_id).quantities == (1, 1, 1), card_id
    for card_id, n in ACTION_QUANTITIES.items():
        assert db.get(card_id).quantities == (n, n, n), card_id


def test_age_iii_cards_fields_nonempty(db: CardDB) -> None:
    """每张时代 III 牌 id/name/name_en/text 非空, age = Age.III."""
    for card_id in ALL_AGE_III_IDS:
        card = db.get(card_id)
        assert card.id == card_id
        assert card.age is Age.III
        assert card.name and card.name_en and card.text, card_id


# --- 科技/政府/奇迹数值 -------------------------------------------------------


def test_age_iii_tech_values(db: CardDB) -> None:
    mech = db.get("mechanized_agriculture")
    assert mech.category is CardCategory.FARM
    assert mech.cost_science == 7
    assert mech.build_cost == 8
    assert mech.token_value == 5

    oil = db.get("oil")
    assert oil.category is CardCategory.MINE
    assert oil.cost_science == 9
    assert oil.build_cost == 11
    assert oil.token_value == 5

    computers = db.get("computers")
    assert computers.category is CardCategory.LAB
    assert computers.cost_science == 8
    assert computers.build_cost == 11
    assert computers.urban_produces == {"science": 5}

    pro_sports = db.get("pro_sports")
    assert pro_sports.category is CardCategory.ARENA
    assert pro_sports.cost_science == 7
    assert pro_sports.build_cost == 8
    assert pro_sports.urban_produces == {"culture": 3, "happiness": 4}

    multimedia = db.get("multimedia")
    assert multimedia.category is CardCategory.LIBRARY
    assert multimedia.cost_science == 9
    assert multimedia.build_cost == 11
    assert multimedia.urban_produces == {"culture": 3, "science": 3}

    movies = db.get("movies")
    assert movies.category is CardCategory.THEATER
    assert movies.cost_science == 10
    assert movies.build_cost == 11
    assert movies.urban_produces == {"culture": 4, "happiness": 1}

    modern_infantry = db.get("modern_infantry")
    assert modern_infantry.category is CardCategory.INFANTRY
    assert modern_infantry.cost_science == 10
    assert modern_infantry.build_cost == 7
    assert modern_infantry.strength == 5

    tanks = db.get("tanks")
    assert tanks.category is CardCategory.CAVALRY
    assert tanks.cost_science == 9
    assert tanks.build_cost == 7
    assert tanks.strength == 5

    rockets = db.get("rockets")
    assert rockets.category is CardCategory.ARTILLERY
    assert rockets.cost_science == 8
    assert rockets.build_cost == 7
    assert rockets.strength == 5

    air_forces = db.get("air_forces")
    assert air_forces.category is CardCategory.AIR
    assert air_forces.cost_science == 12
    assert air_forces.build_cost == 7
    assert air_forces.strength == 5


def test_age_iii_special_tech_values(db: CardDB) -> None:
    theory = db.get("military_theory")
    assert theory.category is CardCategory.SPECIAL
    assert theory.special_type is SpecialType.WARFARE
    assert theory.cost_science == 11

    service = db.get("civil_service")
    assert service.special_type is SpecialType.LAW
    assert service.cost_science == 10

    satellites = db.get("satellites")
    assert satellites.special_type is SpecialType.EXPLORATION
    assert satellites.cost_science == 8

    engineering = db.get("engineering")
    assert engineering.special_type is SpecialType.CONSTRUCTION
    assert engineering.cost_science == 9


def test_age_iii_government_values(db: CardDB) -> None:
    """共产主义: 和平 19 / 革命 5, 7 白 5 红 4 城, -1 笑脸."""
    communism = db.get("communism")
    assert communism.cost_science == 19
    assert communism.cost_science_revolution == 5
    gov = communism.government
    assert gov is not None
    assert gov.civil_actions == 7
    assert gov.military_actions == 5
    assert gov.urban_limit == 4
    assert gov.bonus == {"happiness": -1}

    fund = db.get("fundamentalism")
    assert fund.cost_science == 18
    assert fund.cost_science_revolution == 7
    gov = fund.government
    assert gov is not None
    assert gov.civil_actions == 6
    assert gov.military_actions == 5
    assert gov.urban_limit == 4
    assert gov.bonus == {"science": -2, "strength": 5}

    democracy = db.get("democracy")
    assert democracy.cost_science == 17
    assert democracy.cost_science_revolution == 9
    gov = democracy.government
    assert gov is not None
    assert gov.civil_actions == 7
    assert gov.military_actions == 3
    assert gov.urban_limit == 4
    assert gov.bonus == {"culture": 3}


def test_age_iii_wonder_definitions(db: CardDB) -> None:
    hollywood = db.get("hollywood")
    assert hollywood.wonder_stages == (5, 6, 5)
    assert hollywood.wonder_bonus == {}

    internet = db.get("internet")
    assert internet.wonder_stages == (2, 3, 4, 3, 2)
    assert internet.wonder_bonus == {}

    flight = db.get("first_space_flight")
    assert flight.wonder_stages == (1, 2, 4, 9)
    assert flight.wonder_bonus == {}

    fast_food = db.get("fast_food_chains")
    assert fast_food.wonder_stages == (4, 4, 4, 4)
    assert fast_food.wonder_bonus == {}


# --- 特殊科技静态钩子 ---------------------------------------------------------


def test_military_theory_static_bonus(db: CardDB) -> None:
    """military_theory: +5 军力 +3 军事行动."""
    civ = civ_values(db, _player(developed=("military_theory",)))
    assert civ.strength == 5
    assert civ.military_actions == 2 + 3


def test_civil_service_static_bonus(db: CardDB) -> None:
    """civil_service: +2 内政行动."""
    civ = civ_values(db, _player(developed=("civil_service",)))
    assert civ.civil_actions == 4 + 2


def test_civil_service_develop_gains_blue_tokens(db: CardDB) -> None:
    """civil_service: 研发时立即 +3 蓝点(on_develop 钩子)."""
    p = _player(hand_civil=("civil_service",), science=10, blue_bank=13)
    new = apply(_state(p), DevelopTech("civil_service"), db)
    p0 = new.players[0]
    assert "civil_service" in p0.developed
    assert p0.blue_bank == 16


def test_satellites_static_bonus(db: CardDB) -> None:
    """satellites: +4 殖民修正 +3 军力."""
    civ = civ_values(db, _player(developed=("satellites",)))
    assert civ.colonization == 4
    assert civ.strength == 3


def test_engineering_no_handler(db: CardDB) -> None:
    """engineering: 建造折扣/四阶段 P2-DEFERRED, 无静态钩子."""
    assert db.get("engineering").handler == ""
    assert effects.static_bonuses(db, _player(developed=("engineering",))) == {}


# --- 奇迹静态钩子 ---------------------------------------------------------------


def test_internet_static_bonus(db: CardDB) -> None:
    """internet: 城市建筑每 1 科技/文化产出 +1 文化(按工人数)."""
    # multimedia 2 工人(3 科技 + 3 文化) + movies 1 工人(4 文化)
    # = 2 × 6 + 1 × 4 = 16 文化
    p = _player(
        wonders=("internet",),
        developed=("multimedia", "movies"),
        buildings={"library": {"multimedia": 2}, "theater": {"movies": 1}},
    )
    base = civ_values(db, _player(
        developed=("multimedia", "movies"),
        buildings={"library": {"multimedia": 2}, "theater": {"movies": 1}}))
    civ = civ_values(db, p)
    assert civ.culture_rate == base.culture_rate + 16


def test_first_space_flight_static_bonus(db: CardDB) -> None:
    """first_space_flight: 每项已研发科技每级 +1 文化(政体不计)."""
    # computers(III=4 级) + irrigation(I=2 级) + warfare(I=2 级) = 8
    p = _player(
        wonders=("first_space_flight",),
        developed=("computers", "irrigation", "warfare"),
    )
    civ = civ_values(db, p)
    assert civ.culture_rate == 8


def test_fast_food_chains_static_bonus(db: CardDB) -> None:
    """fast_food_chains: 农场/矿场每卡 +2 文化, 城市建筑/兵种每卡 +1."""
    # agriculture + oil(有工人, 2×2=4) + movies + tanks(2×1=2) = 6
    p = _player(
        wonders=("fast_food_chains",),
        developed=("agriculture", "oil", "movies", "tanks"),
        buildings={
            "farm": {"agriculture": 1},
            "mine": {"oil": 2},
            "theater": {"movies": 1},
            "cavalry": {"tanks": 1},
        },
    )
    base = civ_values(db, _player(
        developed=("agriculture", "oil", "movies", "tanks"),
        buildings={
            "farm": {"agriculture": 1},
            "mine": {"oil": 2},
            "theater": {"movies": 1},
            "cavalry": {"tanks": 1},
        },
    ))
    civ = civ_values(db, p)
    assert civ.culture_rate == base.culture_rate + 6


def test_hollywood_deferred(db: CardDB) -> None:
    """hollywood: 建成时一次性得分 P2-DEFERRED, 无钩子."""
    card = db.get("hollywood")
    assert card.handler == ""
    assert "P2-DEFERRED" in card.text


# --- 领袖钩子 -----------------------------------------------------------------


def test_einstein_science_per_best_lab_level(db: CardDB) -> None:
    """albert_einstein: 最佳实验室/图书馆每级 +1 科技(同 newton 口径)."""
    # computers(时代 III, 4 级) -> +4
    p = _player(leader="albert_einstein",
                developed=("philosophy", "computers"),
                buildings={"lab": {"computers": 1}})
    civ = civ_values(db, p)
    base = civ_values(db, _player(
        developed=("philosophy", "computers"),
        buildings={"lab": {"computers": 1}}))
    assert civ.science_rate == base.science_rate + 4


def test_einstein_develop_tech_gains_culture(db: CardDB) -> None:
    """albert_einstein: 研发科技 +3 文化(每次触发, on_develop 钩子)."""
    p = _player(leader="albert_einstein", hand_civil=("irrigation",),
                science=3, culture=5)
    new = apply(_state(p), DevelopTech("irrigation"), db)
    p0 = new.players[0]
    assert "irrigation" in p0.developed
    assert p0.culture == 5 + 3
    # 无 einstein: 不加文化
    p2 = _player(hand_civil=("irrigation",), science=3, culture=5)
    new2 = apply(_state(p2), DevelopTech("irrigation"), db)
    assert new2.players[0].culture == 5


def test_gandhi_static_bonus(db: CardDB) -> None:
    """mahatma_gandhi: +2 文化(侵略/战争限制 P2-DEFERRED)."""
    civ = civ_values(db, _player(leader="mahatma_gandhi"))
    assert civ.culture_rate == 2
    assert "P2-DEFERRED" in db.get("mahatma_gandhi").text


def test_chaplin_static_bonus(db: CardDB) -> None:
    """charlie_chaplin: +2 笑脸; 最佳剧院双倍文化."""
    # movies 1 工人 4 文化 -> 额外 +4; drama 1 工人 2 文化(非最佳, 不加)
    p = _player(leader="charlie_chaplin",
                developed=("movies", "drama"),
                buildings={"theater": {"movies": 1, "drama": 1}})
    base = civ_values(db, _player(
        developed=("movies", "drama"),
        buildings={"theater": {"movies": 1, "drama": 1}}))
    civ = civ_values(db, p)
    assert civ.happiness == base.happiness + 2
    assert civ.culture_rate == base.culture_rate + 4


def test_chaplin_best_theater_by_total_production(db: CardDB) -> None:
    """charlie_chaplin: 最佳剧院按工人数 × 卡面文化计."""
    # drama 2 工人 = 4 > movies 1 工人 = 4? 并列取 max = 4
    p = _player(leader="charlie_chaplin",
                developed=("movies", "drama"),
                buildings={"theater": {"movies": 1, "drama": 2}})
    assert effects.static_bonuses(db, p)["culture"] == 4


def test_bill_gates_churchill_deferred(db: CardDB) -> None:
    """bill_gates / winston_churchill: 能力 P2-DEFERRED, 无钩子."""
    for card_id in ("bill_gates", "winston_churchill"):
        card = db.get(card_id)
        assert card.handler == "", card_id
        assert "P2-DEFERRED" in card.text, card_id
        p = _player(leader=card_id)
        assert effects.static_bonuses(db, p) == {}, card_id


def test_sid_meier_static_bonus(db: CardDB) -> None:
    """sid_meier: 实验室每级 +1 文化, 每个实验室 -1 科技."""
    # computers(4 级) + alchemy(2 级): 文化 +6, 科技 -2
    p = _player(leader="sid_meier",
                developed=("computers", "alchemy"),
                buildings={"lab": {"computers": 1, "alchemy": 1}})
    base = civ_values(db, _player(
        developed=("computers", "alchemy"),
        buildings={"lab": {"computers": 1, "alchemy": 1}}))
    civ = civ_values(db, p)
    assert civ.culture_rate == base.culture_rate + 6
    assert civ.science_rate == base.science_rate - 2


# --- 行动卡 handler 注册与结算 --------------------------------------------------


def test_age_iii_action_handlers_registered(db: CardDB) -> None:
    """每张时代 III 行动卡 handler 已注册; pending 类与 PENDING_SPECS 成对."""
    for card_id in ACTION_QUANTITIES:
        handler = db.get(card_id).handler
        assert handler in effects.ACTION_HANDLERS, handler
    for name in ("efficient_upgrade_iii", "engineering_genius_iii",
                 "urban_growth_iii"):
        assert name in effects.PENDING_SPECS
    assert "reserves_iii" in effects.ACTION_OPTIONS


def test_efficient_upgrade_iii_x4(db: CardDB) -> None:
    """efficient_upgrade_iii: 下一农场/矿场/城市建筑 Upgrade 0 行动点折扣 4."""
    p = _player(hand_civil=("efficient_upgrade_iii",), civil_actions=1,
                developed=("coal", "oil"), buildings={"mine": {"coal": 1}},
                worker_pool=1, card_tokens={"coal": 2}, blue_bank=16)
    new = apply(_state(p), PlayActionCard("efficient_upgrade_iii"), db)
    assert new.pending == (PendingEffect("upgrade_farm_mine_urban", 4),)
    legal = legal_actions(db, new)
    assert Upgrade("coal", "oil") in legal


def test_endowment_for_arts_iii_two_players(db: CardDB) -> None:
    """endowment_for_arts_iii: 每个文化分更高文明 +6(2p)."""
    p0 = _player(hand_civil=("endowment_for_arts_iii",), culture=3)
    p1 = _player(name="P1", culture=10)
    new = apply(_state(p0, p1), PlayActionCard("endowment_for_arts_iii"), db)
    assert new.players[0].culture == 3 + 6
    # 文化分最高者打出: 无人更高 -> 不加
    rich = _player(name="P1", hand_civil=("endowment_for_arts_iii",),
                   culture=10)
    new2 = apply(_state(rich, p0), PlayActionCard("endowment_for_arts_iii"),
                 db)
    assert new2.players[0].culture == 10


def test_endowment_for_arts_iii_four_players(db: CardDB) -> None:
    """endowment_for_arts_iii: 4p 每个文化分更高文明 +2; 平局不算更高."""
    p0 = _player(hand_civil=("endowment_for_arts_iii",), culture=5)
    p1 = _player(name="P1", culture=9)
    p2 = _player(name="P2", culture=5)
    p3 = _player(name="P3", culture=12)
    new = apply(_state(p0, p1, p2, p3),
                PlayActionCard("endowment_for_arts_iii"), db)
    # p1、p3 更高(平局 p2 不计) -> 2 × 2 = 4
    assert new.players[0].culture == 5 + 4


def test_engineering_genius_iii_x5(db: CardDB) -> None:
    """engineering_genius_iii: 奇迹阶段折扣 5(X=5)."""
    p = _player(hand_civil=("engineering_genius_iii",),
                wonder_progress=("hollywood", 0), developed=("bronze",),
                card_tokens={"bronze": 2}, blue_bank=16)
    new = apply(_state(p), PlayActionCard("engineering_genius_iii"), db)
    assert new.pending == (PendingEffect("wonder_stage", 5),)


def test_military_build_up_iii_three_players(db: CardDB) -> None:
    """military_build_up_iii: 3p 每个更强文明 +5 本回合兵种建造折扣."""
    p0 = _player(hand_civil=("military_build_up_iii",))
    p1 = _player(name="P1", developed=("warriors",),
                 buildings={"infantry": {"warriors": 1}})
    p2 = _player(name="P2", developed=("swordsmen",),
                 buildings={"infantry": {"swordsmen": 1}})
    new = apply(_state(p0, p1, p2),
                PlayActionCard("military_build_up_iii"), db)
    # p1 军力 1、p2 军力 2, 均 > 0 -> 2 × 5 = 10
    assert new.players[0].turn_discounts == {"unit_build": 10}
    # 最强者打出: 无人更强 -> 无折扣
    strong = _player(hand_civil=("military_build_up_iii",),
                     developed=("swordsmen",),
                     buildings={"infantry": {"swordsmen": 2}})
    new2 = apply(_state(strong, p1, p2),
                 PlayActionCard("military_build_up_iii"), db)
    assert new2.players[0].turn_discounts == {}


def test_patriotism_iii_x4(db: CardDB) -> None:
    """patriotism_iii: 本回合 +1 军事行动, 兵种建造折扣 4(X=4)."""
    p = _player(hand_civil=("patriotism_iii",), military_actions=1,
                developed=("warriors", "bronze"), worker_pool=1,
                card_tokens={"bronze": 1})
    new = apply(_state(p), PlayActionCard("patriotism_iii"), db)
    p0 = new.players[0]
    assert p0.military_actions == 2
    assert p0.turn_discounts == {"unit_build": 4}


def test_reserves_iii_x4_choice(db: CardDB) -> None:
    """reserves_iii: +4 资源或 +4 食物, option 二选一(X=4)."""
    p = _player(hand_civil=("reserves_iii",),
                developed=("agriculture", "bronze"), blue_bank=16)
    state = _state(p)
    legal = legal_actions(db, state)
    assert PlayActionCard("reserves_iii", "resource") in legal
    assert PlayActionCard("reserves_iii", "food") in legal
    new = apply(state, PlayActionCard("reserves_iii", "resource"), db)
    assert new.players[0].card_tokens == {"bronze": 4}
    new2 = apply(state, PlayActionCard("reserves_iii", "food"), db)
    assert new2.players[0].card_tokens == {"agriculture": 4}
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("reserves_iii", "gold"), db)


def test_revolutionary_idea_iii_x6(db: CardDB) -> None:
    """revolutionary_idea_iii: +6 科技(X=6)."""
    p = _player(hand_civil=("revolutionary_idea_iii",), science=1)
    new = apply(_state(p), PlayActionCard("revolutionary_idea_iii"), db)
    p0 = new.players[0]
    assert p0.science == 1 + 6
    assert p0.civil_actions == 3


def test_urban_growth_iii_x4(db: CardDB) -> None:
    """urban_growth_iii: 下一城市建筑 Build/Upgrade 0 行动点折扣 4(X=4)."""
    p = _player(hand_civil=("urban_growth_iii",), civil_actions=1,
                developed=("philosophy", "bronze"), worker_pool=1,
                card_tokens={"bronze": 2})
    new = apply(_state(p), PlayActionCard("urban_growth_iii"), db)
    assert new.pending == (PendingEffect("build_urban", 4),)
    new2 = apply(new, Build("philosophy"), db)
    assert new2.players[0].card_tokens == {"bronze": 2}  # 3 - 4 = 0
