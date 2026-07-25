"""时代 I 官方内政牌库 + 领袖/特殊科技/奇迹/行动卡钩子测试.

数据来源: Card Reference v1.09 第 1 页(科技/政府/特殊科技/奇迹数值与
2p/3p/4p 张数)、第 2 页(领袖全表文本 + 行动牌 X 加成与张数)。
行动卡 id 带时代后缀(如 rich_land_i), handler 名 = 卡 id 全名。

时代 I 内政牌堆总数(按 PDF quantities 计算):
- 2p: 科技 15 + 特殊科技 4 + 政府 2 + 奇迹 4 + 领袖 6 + 行动 13 = 44
- 3p: 科技 18 + 特殊科技 6 + 政府 3 + 奇迹 4 + 领袖 6 + 行动 13 = 50
- 4p: 科技 21 + 特殊科技 6 + 政府 3 + 奇迹 4 + 领袖 6 + 行动 13 = 53
"""

from collections import Counter

import pytest

from tta.cards import build_card_db
from tta.engine import effects
from tta.engine.actions import (
    Build,
    BuildWonderStage,
    DevelopTech,
    IllegalActionError,
    PassTurn,
    PlayActionCard,
    PlayLeader,
    TakeCard,
)
from tta.engine.apply import apply
from tta.engine.civ import civ_values
from tta.engine.enums import Age, CardCategory, SpecialType
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB
from tta.engine.state import ROW_SLOTS, GameState, PendingEffect, PlayerState

# PDF 第 1 页 Age I 行: (科技费, 建造费, quantities)
TECH_IDS = (
    "irrigation", "iron", "alchemy", "theology", "bread_and_circuses",
    "printing_press", "drama", "swordsmen", "knights",
)
SPECIAL_IDS = ("warfare", "code_of_laws", "cartography", "masonry")
GOVERNMENT_IDS = ("theocracy", "monarchy")
WONDER_IDS = (
    "great_wall", "st_peters_basilica", "universitas_carolina", "taj_mahal",
)
LEADER_IDS = (
    "michelangelo", "joan_of_arc", "leonardo_da_vinci", "genghis_khan",
    "christopher_columbus", "frederick_barbarossa",
)
# PDF 第 2 页 Actions 表 Quantity 列 Age I 值
ACTION_QUANTITIES = {
    "breakthrough_i": 2,
    "cultural_heritage_i": 1,
    "engineering_genius_i": 1,
    "frugality_i": 2,
    "patriotism_i": 1,
    "reserves_i": 2,
    "rich_land_i": 2,
    "urban_growth_i": 2,
}
# PDF 第 1 页 2p/3p/4p 张数
TECH_QUANTITIES = {
    "irrigation": (2, 2, 2),
    "iron": (2, 2, 3),
    "alchemy": (2, 2, 3),
    "theology": (1, 2, 2),
    "bread_and_circuses": (1, 2, 2),
    "printing_press": (2, 2, 2),
    "drama": (1, 2, 2),
    "swordsmen": (2, 2, 2),
    "knights": (2, 2, 3),
    "warfare": (1, 2, 2),
    "code_of_laws": (1, 2, 2),
    "cartography": (1, 1, 1),
    "masonry": (1, 1, 1),
    "theocracy": (1, 1, 1),
    "monarchy": (1, 2, 2),
}
DECK_TOTALS = {2: 44, 3: 50, 4: 53}

ALL_AGE_I_IDS = (
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


def _state(player: PlayerState, **overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.I,
        "current_player": 0,
        "card_row": _row(),
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (player, _player(name="P1")),
        "rng_state": 0,
    }
    base.update(overrides)
    return GameState(**base)


# --- 牌库组成 ---------------------------------------------------------------


def test_age_i_deck_totals(db: CardDB) -> None:
    """时代 I 牌堆总数: 2p=44, 3p=50, 4p=53(PDF quantities 求和)."""
    for num_players, total in DECK_TOTALS.items():
        assert len(db.deck_for(Age.I, num_players)) == total


def test_age_i_deck_composition(db: CardDB) -> None:
    counts = Counter(db.deck_for(Age.I, 4))
    by_category: dict[CardCategory, dict[str, int]] = {}
    for card_id, n in counts.items():
        by_category.setdefault(db.get(card_id).category, {})[card_id] = n
    # 9 种工人科技
    tech_kinds = {
        CardCategory.FARM, CardCategory.MINE, CardCategory.LAB,
        CardCategory.TEMPLE, CardCategory.ARENA, CardCategory.LIBRARY,
        CardCategory.THEATER, CardCategory.INFANTRY, CardCategory.CAVALRY,
    }
    techs = {
        cid: n for cat in tech_kinds
        for cid, n in by_category.get(cat, {}).items()
    }
    assert set(techs) == set(TECH_IDS)
    assert set(by_category[CardCategory.SPECIAL]) == set(SPECIAL_IDS)
    assert set(by_category[CardCategory.GOVERNMENT]) == set(GOVERNMENT_IDS)
    assert set(by_category[CardCategory.WONDER]) == set(WONDER_IDS)
    assert set(by_category[CardCategory.LEADER]) == set(LEADER_IDS)
    assert by_category[CardCategory.ACTION] == ACTION_QUANTITIES
    assert sum(ACTION_QUANTITIES.values()) == 13
    # 奇迹/领袖各 1 张
    assert all(n == 1 for n in by_category[CardCategory.WONDER].values())
    assert all(n == 1 for n in by_category[CardCategory.LEADER].values())


def test_age_i_quantities(db: CardDB) -> None:
    """科技/特殊科技/政府张数 = PDF 2p/3p/4p 列."""
    for card_id, quantities in TECH_QUANTITIES.items():
        assert db.get(card_id).quantities == quantities, card_id
    for card_id in (*WONDER_IDS, *LEADER_IDS):
        assert db.get(card_id).quantities == (1, 1, 1), card_id
    for card_id, n in ACTION_QUANTITIES.items():
        assert db.get(card_id).quantities == (n, n, n), card_id


def test_age_i_cards_fields_nonempty(db: CardDB) -> None:
    """每张时代 I 牌 id/name/name_en/text 非空, age = Age.I."""
    for card_id in ALL_AGE_I_IDS:
        card = db.get(card_id)
        assert card.id == card_id
        assert card.age is Age.I
        assert card.name and card.name_en and card.text, card_id


# --- 科技/政府/奇迹数值 -------------------------------------------------------


def test_age_i_tech_values(db: CardDB) -> None:
    irrigation = db.get("irrigation")
    assert irrigation.category is CardCategory.FARM
    assert irrigation.cost_science == 3
    assert irrigation.build_cost == 4
    assert irrigation.token_value == 2

    iron = db.get("iron")
    assert iron.category is CardCategory.MINE
    assert iron.cost_science == 5
    assert iron.build_cost == 5
    assert iron.token_value == 2

    alchemy = db.get("alchemy")
    assert alchemy.category is CardCategory.LAB
    assert alchemy.cost_science == 4
    assert alchemy.build_cost == 6
    assert alchemy.urban_produces == {"science": 2}

    theology = db.get("theology")
    assert theology.category is CardCategory.TEMPLE
    assert theology.cost_science == 2
    assert theology.build_cost == 5
    assert theology.urban_produces == {"culture": 1, "happiness": 2}

    bac = db.get("bread_and_circuses")
    assert bac.category is CardCategory.ARENA
    assert bac.cost_science == 3
    assert bac.build_cost == 3
    assert bac.urban_produces == {"culture": 1, "happiness": 2}

    press = db.get("printing_press")
    assert press.category is CardCategory.LIBRARY
    assert press.cost_science == 3
    assert press.build_cost == 3
    assert press.urban_produces == {"science": 1, "culture": 1}

    drama = db.get("drama")
    assert drama.category is CardCategory.THEATER
    assert drama.cost_science == 3
    assert drama.build_cost == 4
    assert drama.urban_produces == {"culture": 2, "happiness": 1}

    swordsmen = db.get("swordsmen")
    assert swordsmen.category is CardCategory.INFANTRY
    assert swordsmen.cost_science == 4
    assert swordsmen.build_cost == 3
    assert swordsmen.strength == 2

    knights = db.get("knights")
    assert knights.category is CardCategory.CAVALRY
    assert knights.cost_science == 5
    assert knights.build_cost == 3
    assert knights.strength == 2


def test_age_i_special_tech_values(db: CardDB) -> None:
    warfare = db.get("warfare")
    assert warfare.category is CardCategory.SPECIAL
    assert warfare.special_type is SpecialType.WARFARE
    assert warfare.cost_science == 5

    code = db.get("code_of_laws")
    assert code.special_type is SpecialType.LAW
    assert code.cost_science == 6

    cartography = db.get("cartography")
    assert cartography.special_type is SpecialType.EXPLORATION
    assert cartography.cost_science == 4

    masonry = db.get("masonry")
    assert masonry.special_type is SpecialType.CONSTRUCTION
    assert masonry.cost_science == 3


def test_age_i_government_values(db: CardDB) -> None:
    """神权政治: 和平 6 / 革命 1, 4 白 3 红 3 城, +1 文化 +1 军力 +1 笑脸."""
    theocracy = db.get("theocracy")
    assert theocracy.cost_science == 6
    assert theocracy.cost_science_revolution == 1
    gov = theocracy.government
    assert gov is not None
    assert gov.civil_actions == 4
    assert gov.military_actions == 3
    assert gov.urban_limit == 3
    assert gov.bonus == {"culture": 1, "strength": 1, "happiness": 1}

    monarchy = db.get("monarchy")
    assert monarchy.cost_science == 8
    assert monarchy.cost_science_revolution == 2
    gov = monarchy.government
    assert gov is not None
    assert gov.civil_actions == 5
    assert gov.military_actions == 3
    assert gov.urban_limit == 3
    assert gov.bonus == {}


def test_age_i_wonder_definitions(db: CardDB) -> None:
    assert db.get("great_wall").wonder_stages == (2, 2, 3, 2)
    assert db.get("great_wall").wonder_bonus == {"culture": 1, "happiness": 1}
    assert db.get("st_peters_basilica").wonder_stages == (4, 4)
    assert db.get("st_peters_basilica").wonder_bonus == {
        "culture": 2, "happiness": 1,
    }
    assert db.get("universitas_carolina").wonder_stages == (3, 3, 3)
    assert db.get("universitas_carolina").wonder_bonus == {
        "culture": 1, "science": 2,
    }
    assert db.get("taj_mahal").wonder_stages == (2, 4, 2)
    assert db.get("taj_mahal").wonder_bonus == {"culture": 3}


# --- 特殊科技与奇迹静态钩子 ---------------------------------------------------


def test_warfare_static_bonus(db: CardDB) -> None:
    """warfare: +1 军力 +1 军事行动."""
    civ = civ_values(db, _player(developed=("warfare",)))
    assert civ.strength == 1
    assert civ.military_actions == 2 + 1


def test_code_of_laws_static_bonus(db: CardDB) -> None:
    """code_of_laws: +1 内政行动."""
    civ = civ_values(db, _player(developed=("code_of_laws",)))
    assert civ.civil_actions == 4 + 1


def test_cartography_static_bonus(db: CardDB) -> None:
    """cartography: +1 殖民修正(殖民费 -2 P2-DEFERRED)."""
    civ = civ_values(db, _player(developed=("cartography",)))
    assert civ.colonization == 1


def test_masonry_no_handler(db: CardDB) -> None:
    """masonry: 建造折扣/双阶段 P2-DEFERRED, 无静态钩子."""
    assert db.get("masonry").handler == ""
    assert effects.static_bonuses(db, _player(developed=("masonry",))) == {}


def test_great_wall_strength_per_infantry_and_artillery(db: CardDB) -> None:
    """great_wall: 每个步兵/炮兵单位 +1 军力(骑兵不计)."""
    p = _player(
        wonders=("great_wall",),
        developed=("swordsmen", "knights"),
        buildings={
            "infantry": {"swordsmen": 2},
            "cavalry": {"knights": 1},
        },
    )
    civ = civ_values(db, p)
    # 单位基础 2×2 + 1×2 = 6; 长城: 2 步兵 × 1 = 2(骑兵不加)
    assert civ.strength == 6 + 2
    assert civ.culture_rate == 1
    assert civ.happiness == 1


# --- 领袖钩子 -----------------------------------------------------------------


def test_michelangelo_culture_bonus(db: CardDB) -> None:
    """michelangelo: 寺庙/剧院/奇迹每提供 1 笑脸, +1 文化."""
    p = _player(
        leader="michelangelo",
        developed=("theology", "drama"),
        buildings={"temple": {"theology": 1}, "theater": {"drama": 1}},
        wonders=("hanging_gardens",),
    )
    # 笑脸: 神学 2 + 戏剧 1 + 空中花园 2 = 5 -> 文化 +5
    civ = civ_values(db, p)
    base = civ_values(db, _player(
        developed=("theology", "drama"),
        buildings={"temple": {"theology": 1}, "theater": {"drama": 1}},
        wonders=("hanging_gardens",),
    ))
    assert civ.culture_rate == base.culture_rate + 5


def test_michelangelo_wonder_take_no_surcharge(db: CardDB) -> None:
    """michelangelo: 拿奇迹不付每已完成奇迹 +1 的额外白点."""
    row = _row(None, None, None, None, None, "taj_mahal")
    p = _player(leader="michelangelo", civil_actions=2,
                wonders=("pyramids", "colossus"))
    state = _state(p, card_row=row)
    # 5 号位 2 点; 已有 2 奇迹, 常人需 4 点, michelangelo 仍 2 点
    assert TakeCard(5) in legal_actions(db, state)
    new = apply(state, TakeCard(5), db)
    assert new.players[0].civil_actions == 0
    assert new.players[0].wonder_progress == ("taj_mahal", 0)
    # 无 michelangelo: 需 2 + 2 = 4 点, 2 白点不够
    other = _player(civil_actions=2, wonders=("pyramids", "colossus"))
    assert TakeCard(5) not in legal_actions(db, _state(other, card_row=row))


def test_joan_of_arc_static_bonus(db: CardDB) -> None:
    """joan_of_arc: +1 军事行动 +1 文化; 寺庙与政体每 1 笑脸 +1 军力."""
    p = _player(
        leader="joan_of_arc",
        government="theocracy",  # 政体 +1 笑脸
        developed=("theology",),
        buildings={"temple": {"theology": 1}},  # 神学 2 笑脸
    )
    civ = civ_values(db, p)
    base = civ_values(db, _player(
        government="theocracy",
        developed=("theology",),
        buildings={"temple": {"theology": 1}},
    ))
    assert civ.military_actions == base.military_actions + 1
    assert civ.culture_rate == base.culture_rate + 1
    # 军力加成 = 寺庙笑脸 2 + 政体笑脸 1 = 3(theocracy 自身还有 +1 军力)
    assert civ.strength == base.strength + 3


def test_leonardo_science_per_best_lab_level(db: CardDB) -> None:
    """leonardo: 最佳实验室/图书馆每级 +1 科技(级 = 时代序 A=1, I=2)."""
    # 仅 philosophy(时代 A, 1 级) -> +1
    civ = civ_values(db, _player(leader="leonardo_da_vinci",
                                 developed=("philosophy",)))
    assert civ.science_rate == 1
    # alchemy(时代 I, 2 级) + printing_press(时代 I) -> 最佳 2 级 -> +2
    p = _player(leader="leonardo_da_vinci",
                developed=("philosophy", "alchemy", "printing_press"),
                buildings={"lab": {"alchemy": 1}})
    civ = civ_values(db, p)
    base = civ_values(db, _player(
        developed=("philosophy", "alchemy", "printing_press"),
        buildings={"lab": {"alchemy": 1}}))
    assert civ.science_rate == base.science_rate + 2


def test_leonardo_develop_tech_gains_resource(db: CardDB) -> None:
    """leonardo: 研发科技 +1 资源(经 on_develop 钩子, 蓝点入最低级矿场)."""
    p = _player(leader="leonardo_da_vinci", hand_civil=("irrigation",),
                developed=("bronze",), card_tokens={"bronze": 1},
                blue_bank=16, science=3)
    new = apply(_state(p), DevelopTech("irrigation"), db)
    p0 = new.players[0]
    assert "irrigation" in p0.developed
    assert p0.science == 0                    # 全价 3 科技费
    assert p0.card_tokens == {"bronze": 2}    # +1 资源入 bronze
    assert p0.blue_bank == 15
    # 无 leonardo: 不加
    p2 = _player(hand_civil=("irrigation",), developed=("bronze",),
                 card_tokens={"bronze": 1}, blue_bank=16, science=3)
    new2 = apply(_state(p2), DevelopTech("irrigation"), db)
    assert new2.players[0].card_tokens == {"bronze": 1}


def test_genghis_columbus_barbarossa_deferred(db: CardDB) -> None:
    """genghis/columbus/barbarossa: 互动能力 P2-DEFERRED, 无钩子."""
    for card_id in ("genghis_khan", "christopher_columbus",
                    "frederick_barbarossa"):
        card = db.get(card_id)
        assert card.handler == "", card_id
        assert "P2-DEFERRED" in card.text, card_id
        p = _player(leader=card_id)
        assert effects.static_bonuses(db, p) == {}, card_id


# --- 行动卡 handler 注册与结算 --------------------------------------------------


def test_age_i_action_handlers_registered(db: CardDB) -> None:
    """每张时代 I 行动卡 handler 已注册; pending 类与 PENDING_SPECS 成对."""
    for card_id in ACTION_QUANTITIES:
        handler = db.get(card_id).handler
        assert handler in effects.ACTION_HANDLERS, handler
    for name in ("breakthrough_i", "engineering_genius_i", "rich_land_i",
                 "urban_growth_i"):
        assert name in effects.PENDING_SPECS
    assert "frugality_i" in effects.PLAY_CONDITIONS


def test_rich_land_i_pending_flow(db: CardDB) -> None:
    """rich_land_i: 下一农场/矿场 Build/Upgrade 0 行动点且折扣 2(X=2)."""
    p = _player(hand_civil=("rich_land_i",), civil_actions=1,
                developed=("agriculture", "bronze"), worker_pool=1,
                card_tokens={"bronze": 1})
    new = apply(_state(p), PlayActionCard("rich_land_i"), db)
    assert new.pending == (PendingEffect("build_farm_mine", 2),)
    assert Build("agriculture") in legal_actions(db, new)
    new2 = apply(new, Build("agriculture"), db)
    assert new2.players[0].card_tokens == {"bronze": 1}  # 造价 2 - 2 = 0, 不取蓝点
    assert new2.players[0].buildings == {"farm": {"agriculture": 1}}


def test_urban_growth_i_pending_flow(db: CardDB) -> None:
    """urban_growth_i: 下一城市建筑 Build/Upgrade 0 行动点且折扣 2."""
    p = _player(hand_civil=("urban_growth_i",), civil_actions=1,
                developed=("philosophy", "bronze"), worker_pool=1,
                card_tokens={"bronze": 2})
    new = apply(_state(p), PlayActionCard("urban_growth_i"), db)
    assert new.pending == (PendingEffect("build_urban", 2),)
    new2 = apply(new, Build("philosophy"), db)
    assert new2.players[0].card_tokens == {"bronze": 1}  # 3 - 2 = 1


def test_engineering_genius_i_pending_flow(db: CardDB) -> None:
    """engineering_genius_i: 下一奇迹阶段 0 行动点且折扣 3(X=3)."""
    p = _player(hand_civil=("engineering_genius_i",),
                wonder_progress=("taj_mahal", 0), developed=("bronze",),
                card_tokens={"bronze": 1}, blue_bank=16)
    new = apply(_state(p), PlayActionCard("engineering_genius_i"), db)
    assert new.pending == (PendingEffect("wonder_stage", 3),)
    new2 = apply(new, BuildWonderStage(), db)
    assert new2.players[0].wonder_progress == ("taj_mahal", 1)
    assert new2.players[0].card_tokens == {"bronze": 1}  # 2 - 3 -> 0, 不取蓝点


def test_frugality_i_handler(db: CardDB) -> None:
    """frugality_i: 增人口(全费 2 食物)后 +2 食物(X=2)."""
    p = _player(hand_civil=("frugality_i",), developed=("agriculture",),
                card_tokens={"agriculture": 2}, yellow_bank=18, worker_pool=1,
                blue_bank=16)
    new = apply(_state(p), PlayActionCard("frugality_i"), db)
    p0 = new.players[0]
    assert p0.yellow_bank == 17
    assert p0.worker_pool == 2
    assert p0.card_tokens == {"agriculture": 2}  # 付 2 再得 2


def test_patriotism_i_handler(db: CardDB) -> None:
    """patriotism_i: 本回合 +1 军事行动, 兵种建造折扣 2(X=2)."""
    p = _player(hand_civil=("patriotism_i",), military_actions=1,
                developed=("warriors", "bronze"), worker_pool=1,
                card_tokens={"bronze": 1})
    new = apply(_state(p), PlayActionCard("patriotism_i"), db)
    p0 = new.players[0]
    assert p0.military_actions == 2
    assert p0.turn_discounts == {"unit_build": 2}
    new2 = apply(new, Build("warriors"), db)
    assert new2.players[0].card_tokens == {"bronze": 1}  # 造价 2 - 2 = 0, 不取蓝点


def test_cultural_heritage_i_handler(db: CardDB) -> None:
    """cultural_heritage_i: +2 科技 +2 文化(时代 I 版本, 与 Age A +1/+4 不同)."""
    p = _player(hand_civil=("cultural_heritage_i",))
    new = apply(_state(p), PlayActionCard("cultural_heritage_i"), db)
    p0 = new.players[0]
    assert p0.science == 2
    assert p0.culture == 2
    assert p0.civil_actions == 3


def test_breakthrough_i_pending_flow(db: CardDB) -> None:
    """breakthrough_i: 压入 develop_tech pending; 0 行动点全价研发后 +2 科技."""
    p = _player(hand_civil=("breakthrough_i", "irrigation"), science=3)
    state = _state(p)
    assert PlayActionCard("breakthrough_i") in legal_actions(db, state)
    new = apply(state, PlayActionCard("breakthrough_i"), db)
    assert new.pending == (PendingEffect("develop_tech", 0, science_gain=2),)
    assert new.players[0].civil_actions == 3  # 打出扣 1 白点
    # pending 期间只能研发手牌科技(0 行动点)或 PassTurn
    legal = legal_actions(db, new)
    assert DevelopTech("irrigation") in legal
    new2 = apply(new, DevelopTech("irrigation"), db)
    p2 = new2.players[0]
    assert new2.pending == ()
    assert "irrigation" in p2.developed
    assert p2.science == 3 - 3 + 2            # 全价 3, 再 +2
    assert p2.civil_actions == 3              # pending 子行动 0 行动点


def test_breakthrough_i_unplayable_without_affordable_tech(db: CardDB) -> None:
    """breakthrough_i: 手牌无可负担科技时不可打出(pending 必可解)."""
    p = _player(hand_civil=("breakthrough_i", "irrigation"), science=1)
    state = _state(p)
    assert PlayActionCard("breakthrough_i") not in legal_actions(db, state)
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("breakthrough_i"), db)


def test_reserves_i_choice(db: CardDB) -> None:
    """reserves_i: +2 资源或 +2 食物, 打出时以 option 二选一(X=2)."""
    p = _player(hand_civil=("reserves_i",),
                developed=("agriculture", "bronze"), blue_bank=16)
    state = _state(p)
    legal = legal_actions(db, state)
    assert PlayActionCard("reserves_i", "resource") in legal
    assert PlayActionCard("reserves_i", "food") in legal
    assert PlayActionCard("reserves_i") not in legal  # 必须选择
    new = apply(state, PlayActionCard("reserves_i", "resource"), db)
    assert new.players[0].card_tokens == {"bronze": 2}
    assert new.players[0].blue_bank == 14
    new2 = apply(state, PlayActionCard("reserves_i", "food"), db)
    assert new2.players[0].card_tokens == {"agriculture": 2}
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("reserves_i", "gold"), db)


# --- 端到端: 领袖经 PlayLeader 生效 --------------------------------------------


def test_michelangelo_end_to_end_via_play_leader(db: CardDB) -> None:
    """集成: PlayLeader(michelangelo) 后文化加成经 civ_values 生效."""
    p = _player(hand_civil=("michelangelo",), civil_actions=1,
                developed=("religion",),
                buildings={"temple": {"religion": 1}})
    new = apply(_state(p), PlayLeader("michelangelo"), db)
    civ = civ_values(db, new.players[0])
    base = civ_values(db, _player(developed=("religion",),
                                  buildings={"temple": {"religion": 1}}))
    # religion: 1 文化 1 笑脸; michelangelo 因 1 笑脸再 +1 文化
    assert civ.culture_rate == base.culture_rate + 1


def test_pass_turn_discards_breakthrough_pending(db: CardDB) -> None:
    """SIMPLIFICATION 沿用: PassTurn 可放弃 breakthrough pending."""
    p = _player(hand_civil=("breakthrough_i", "irrigation"), science=3)
    new = apply(_state(p), PlayActionCard("breakthrough_i"), db)
    assert new.pending
    new2 = apply(new, PassTurn(), db)
    assert new2.pending == ()
