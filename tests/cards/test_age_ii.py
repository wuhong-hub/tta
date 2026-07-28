"""时代 II 官方内政牌库 + 领袖/特殊科技/行动卡钩子测试.

数据来源: Card Reference v1.09 第 1 页(科技/政府/特殊科技/奇迹数值与
2p/3p/4p 张数)、第 2 页(领袖全表文本 + 行动牌 X 加成与张数)。
行动卡 id 带时代后缀(如 rich_land_ii), handler 名 = 卡 id 全名。

时代 II 内政牌堆总数(按 PDF quantities 计算):
- 2p: 科技 14 + 特殊科技 4 + 政府 2 + 奇迹 4 + 领袖 6 + 行动 13 = 43
- 3p: 科技 19 + 特殊科技 5 + 政府 3 + 奇迹 4 + 领袖 6 + 行动 13 = 50
- 4p: 科技 21 + 特殊科技 5 + 政府 4 + 奇迹 4 + 领袖 6 + 行动 13 = 53
"""

from collections import Counter

import pytest

from tta.cards import build_card_db
from tta.engine import effects
from tta.engine.actions import (
    Build,
    BuildWonderStage,
    DevelopGovernment,
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

# PDF 第 1 页 Age II 行
TECH_IDS = (
    "selective_breeding", "coal", "scientific_method", "organized_religion",
    "team_sports", "journalism", "opera", "riflemen", "cavalrymen", "cannon",
)
SPECIAL_IDS = ("strategy", "justice_system", "navigation", "architecture")
GOVERNMENT_IDS = ("republic", "constitutional_monarchy")
WONDER_IDS = (
    "transcontinental_railroad", "eiffel_tower", "kremlin",
    "ocean_liner_service",
)
LEADER_IDS = (
    "william_shakespeare", "james_cook", "napoleon_bonaparte",
    "maximilien_robespierre", "j_s_bach", "isaac_newton",
)
# PDF 第 2 页 Actions 表 Quantity 列 Age II 值
ACTION_QUANTITIES = {
    "breakthrough_ii": 2,
    "efficient_upgrade_ii": 2,
    "engineering_genius_ii": 1,
    "frugality_ii": 1,
    "patriotism_ii": 1,
    "reserves_ii": 2,
    "revolutionary_idea_ii": 1,
    "rich_land_ii": 1,
    "urban_growth_ii": 1,
    "wave_of_nationalism_ii": 1,
}
# PDF 第 1 页 2p/3p/4p 张数
CARD_QUANTITIES = {
    "selective_breeding": (1, 2, 3),
    "coal": (1, 2, 2),
    "scientific_method": (2, 2, 2),
    "organized_religion": (2, 2, 2),
    "team_sports": (1, 1, 1),
    "journalism": (1, 2, 2),
    "opera": (1, 2, 2),
    "riflemen": (1, 2, 2),
    "cavalrymen": (2, 2, 2),
    "cannon": (2, 2, 3),
    "strategy": (1, 1, 1),
    "justice_system": (1, 1, 1),
    "navigation": (1, 1, 1),
    "architecture": (1, 2, 2),
    "republic": (1, 1, 2),
    "constitutional_monarchy": (1, 2, 2),
}
DECK_TOTALS = {2: 43, 3: 50, 4: 53}

ALL_AGE_II_IDS = (
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
        "age": Age.II,
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


def test_age_ii_deck_totals(db: CardDB) -> None:
    """时代 II 牌堆总数: 2p=43, 3p=50, 4p=53(PDF quantities 求和)."""
    for num_players, total in DECK_TOTALS.items():
        assert len(db.deck_for(Age.II, num_players)) == total


def test_age_ii_deck_composition(db: CardDB) -> None:
    counts = Counter(db.deck_for(Age.II, 4))
    by_category: dict[CardCategory, dict[str, int]] = {}
    for card_id, n in counts.items():
        by_category.setdefault(db.get(card_id).category, {})[card_id] = n
    # 10 种工人科技
    tech_kinds = {
        CardCategory.FARM, CardCategory.MINE, CardCategory.LAB,
        CardCategory.TEMPLE, CardCategory.ARENA, CardCategory.LIBRARY,
        CardCategory.THEATER, CardCategory.INFANTRY, CardCategory.CAVALRY,
        CardCategory.ARTILLERY,
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


def test_age_ii_quantities(db: CardDB) -> None:
    """科技/特殊科技/政府张数 = PDF 2p/3p/4p 列."""
    for card_id, quantities in CARD_QUANTITIES.items():
        assert db.get(card_id).quantities == quantities, card_id
    for card_id in (*WONDER_IDS, *LEADER_IDS):
        assert db.get(card_id).quantities == (1, 1, 1), card_id
    for card_id, n in ACTION_QUANTITIES.items():
        assert db.get(card_id).quantities == (n, n, n), card_id


def test_age_ii_cards_fields_nonempty(db: CardDB) -> None:
    """每张时代 II 牌 id/name/name_en/text 非空, age = Age.II."""
    for card_id in ALL_AGE_II_IDS:
        card = db.get(card_id)
        assert card.id == card_id
        assert card.age is Age.II
        assert card.name and card.name_en and card.text, card_id


# --- 科技/政府/奇迹数值 -------------------------------------------------------


def test_age_ii_tech_values(db: CardDB) -> None:
    selective = db.get("selective_breeding")
    assert selective.category is CardCategory.FARM
    assert selective.cost_science == 5
    assert selective.build_cost == 6
    assert selective.token_value == 3

    coal = db.get("coal")
    assert coal.category is CardCategory.MINE
    assert coal.cost_science == 7
    assert coal.build_cost == 8
    assert coal.token_value == 3

    method = db.get("scientific_method")
    assert method.category is CardCategory.LAB
    assert method.cost_science == 6
    assert method.build_cost == 8
    assert method.urban_produces == {"science": 3}

    org_rel = db.get("organized_religion")
    assert org_rel.category is CardCategory.TEMPLE
    assert org_rel.cost_science == 4
    assert org_rel.build_cost == 7
    assert org_rel.urban_produces == {"culture": 1, "happiness": 3}

    team_sports = db.get("team_sports")
    assert team_sports.category is CardCategory.ARENA
    assert team_sports.cost_science == 5
    assert team_sports.build_cost == 5
    assert team_sports.urban_produces == {"culture": 2, "happiness": 3}

    journalism = db.get("journalism")
    assert journalism.category is CardCategory.LIBRARY
    assert journalism.cost_science == 6
    assert journalism.build_cost == 8
    assert journalism.urban_produces == {"culture": 2, "science": 2}

    opera = db.get("opera")
    assert opera.category is CardCategory.THEATER
    assert opera.cost_science == 7
    assert opera.build_cost == 8
    assert opera.urban_produces == {"culture": 3, "happiness": 2}

    riflemen = db.get("riflemen")
    assert riflemen.category is CardCategory.INFANTRY
    assert riflemen.cost_science == 6
    assert riflemen.build_cost == 5
    assert riflemen.strength == 3

    cavalrymen = db.get("cavalrymen")
    assert cavalrymen.category is CardCategory.CAVALRY
    assert cavalrymen.cost_science == 6
    assert cavalrymen.build_cost == 5
    assert cavalrymen.strength == 3

    cannon = db.get("cannon")
    assert cannon.category is CardCategory.ARTILLERY
    assert cannon.cost_science == 6
    assert cannon.build_cost == 5
    assert cannon.strength == 3


def test_age_ii_special_tech_values(db: CardDB) -> None:
    strategy = db.get("strategy")
    assert strategy.category is CardCategory.SPECIAL
    assert strategy.special_type is SpecialType.WARFARE
    assert strategy.cost_science == 8

    justice = db.get("justice_system")
    assert justice.special_type is SpecialType.LAW
    assert justice.cost_science == 7

    navigation = db.get("navigation")
    assert navigation.special_type is SpecialType.EXPLORATION
    assert navigation.cost_science == 6

    architecture = db.get("architecture")
    assert architecture.special_type is SpecialType.CONSTRUCTION
    assert architecture.cost_science == 6


def test_age_ii_government_values(db: CardDB) -> None:
    """共和制: 和平 13 / 革命 3, 7 白 2 红 3 城."""
    republic = db.get("republic")
    assert republic.cost_science == 13
    assert republic.cost_science_revolution == 3
    gov = republic.government
    assert gov is not None
    assert gov.civil_actions == 7
    assert gov.military_actions == 2
    assert gov.urban_limit == 3
    assert gov.bonus == {}

    monarchy = db.get("constitutional_monarchy")
    assert monarchy.cost_science == 12
    assert monarchy.cost_science_revolution == 6
    gov = monarchy.government
    assert gov is not None
    assert gov.civil_actions == 6
    assert gov.military_actions == 4
    assert gov.urban_limit == 3
    assert gov.bonus == {}


def test_age_ii_wonder_definitions(db: CardDB) -> None:
    railroad = db.get("transcontinental_railroad")
    assert railroad.wonder_stages == (3, 3, 3, 3)
    assert railroad.wonder_bonus == {"strength": 4}

    eiffel = db.get("eiffel_tower")
    assert eiffel.wonder_stages == (3, 7, 3)
    assert eiffel.wonder_bonus == {"culture": 4, "happiness": 1}

    kremlin = db.get("kremlin")
    assert kremlin.wonder_stages == (4, 4, 4)
    assert kremlin.wonder_bonus == {
        "culture": 2, "civil_actions": 1, "military_actions": 1,
        "happiness": -1,
    }

    liner = db.get("ocean_liner_service")
    assert liner.wonder_stages == (4, 2, 2, 4)
    assert liner.wonder_bonus == {}


# --- 特殊科技静态钩子 ---------------------------------------------------------


def test_strategy_static_bonus(db: CardDB) -> None:
    """strategy: +3 军力 +2 军事行动."""
    civ = civ_values(db, _player(developed=("strategy",)))
    assert civ.strength == 3
    assert civ.military_actions == 2 + 2


def test_justice_system_static_bonus(db: CardDB) -> None:
    """justice_system: +1 内政行动."""
    civ = civ_values(db, _player(developed=("justice_system",)))
    assert civ.civil_actions == 4 + 1


def test_justice_system_develop_gains_blue_tokens(db: CardDB) -> None:
    """justice_system: 研发时立即 +3 蓝点(on_develop 钩子)."""
    p = _player(hand_civil=("justice_system",), science=7, blue_bank=13)
    new = apply(_state(p), DevelopTech("justice_system"), db)
    p0 = new.players[0]
    assert "justice_system" in p0.developed
    assert p0.blue_bank == 16
    # 非 justice_system 研发不加
    p2 = _player(hand_civil=("irrigation",), science=3, blue_bank=13)
    new2 = apply(_state(p2), DevelopTech("irrigation"), db)
    assert new2.players[0].blue_bank == 13


def test_justice_system_replaces_code_of_laws(db: CardDB) -> None:
    """官方规则: 同类型(LAW)特殊科技两张并存时, 等级较低者立即入 removed.

    code_of_laws(时代 I) + justice_system(时代 II) -> 只留后者,
    前者入 removed(保持卡牌守恒)。
    """
    p = _player(hand_civil=("justice_system",), science=7,
                developed=("code_of_laws",))
    new = apply(_state(p), DevelopTech("justice_system"), db)
    p0 = new.players[0]
    assert p0.developed == ("justice_system",)
    assert new.removed == ("code_of_laws",)
    # code_of_laws 静态加成随移除失效
    civ = civ_values(db, p0)
    assert civ.civil_actions == 4 + 1


def test_navigation_static_bonus(db: CardDB) -> None:
    """navigation: +2 殖民修正 +3 军力."""
    civ = civ_values(db, _player(developed=("navigation",)))
    assert civ.colonization == 2
    assert civ.strength == 3


def test_architecture_no_handler(db: CardDB) -> None:
    """architecture: 建造折扣/三阶段经 effects 费用钩子生效(P3-T6), 无静态钩子."""
    assert db.get("architecture").handler == ""
    assert effects.static_bonuses(db, _player(developed=("architecture",))) == {}


# --- 领袖钩子 -----------------------------------------------------------------


def test_napoleon_static_bonus(db: CardDB) -> None:
    """napoleon: +2 军事行动; 每种军事单位类型 +2 军力."""
    p = _player(
        leader="napoleon_bonaparte",
        developed=("swordsmen", "knights", "cannon"),
        buildings={
            "infantry": {"swordsmen": 2},
            "cavalry": {"knights": 1},
            "artillery": {"cannon": 1},
        },
    )
    civ = civ_values(db, p)
    base = civ_values(db, _player(
        developed=("swordsmen", "knights", "cannon"),
        buildings={
            "infantry": {"swordsmen": 2},
            "cavalry": {"knights": 1},
            "artillery": {"cannon": 1},
        },
    ))
    assert civ.military_actions == base.military_actions + 2
    # 3 种单位类型 × 2 = 6 军力(同种多工人只计 1 种)
    assert civ.strength == base.strength + 6


def test_robespierre_static_bonus(db: CardDB) -> None:
    """robespierre: +1 军事行动(革命费与革命笑脸见专项测试/P2-DEFERRED)."""
    civ = civ_values(db, _player(leader="maximilien_robespierre"))
    assert civ.military_actions == 2 + 1


def test_robespierre_revolution_costs_military(db: CardDB) -> None:
    """robespierre: 革命花全部红点(而非全部白点)."""
    p = _player(leader="maximilien_robespierre",
                civil_actions=0, military_actions=3,
                hand_civil=("republic",), science=3)
    state = _state(p)
    # 白点 0 仍可革命(耗红点)
    assert DevelopGovernment("republic", True) in legal_actions(db, state)
    # 和平演变仍需白点
    assert DevelopGovernment("republic", False) not in legal_actions(db, state)
    new = apply(state, DevelopGovernment("republic", True), db)
    p0 = new.players[0]
    assert p0.government == "republic"
    assert p0.military_actions == 0
    assert p0.civil_actions == 0
    assert p0.science == 0
    # 无 robespierre: 白点 0 不可革命
    p2 = _player(civil_actions=0, military_actions=3,
                 hand_civil=("republic",), science=3)
    assert DevelopGovernment("republic", True) not in legal_actions(
        db, _state(p2))


def test_revolution_without_robespierre_unchanged(db: CardDB) -> None:
    """常规革命仍花全部白点(回归)."""
    p = _player(civil_actions=3, military_actions=2,
                hand_civil=("republic",), science=3)
    new = apply(_state(p), DevelopGovernment("republic", True), db)
    assert new.players[0].civil_actions == 0
    assert new.players[0].military_actions == 2


def test_newton_science_per_best_lab_level(db: CardDB) -> None:
    """isaac_newton: 最佳实验室/图书馆每级 +1 科技(同 leonardo 口径)."""
    # scientific_method(时代 II, 3 级) -> +3
    p = _player(leader="isaac_newton",
                developed=("philosophy", "scientific_method"),
                buildings={"lab": {"scientific_method": 1}})
    civ = civ_values(db, p)
    base = civ_values(db, _player(
        developed=("philosophy", "scientific_method"),
        buildings={"lab": {"scientific_method": 1}}))
    assert civ.science_rate == base.science_rate + 3


def test_newton_develop_tech_gets_civil_action_back(db: CardDB) -> None:
    """isaac_newton: 研发科技拿回 1 白点(on_develop 钩子)."""
    p = _player(leader="isaac_newton", hand_civil=("irrigation",),
                science=3, civil_actions=3)
    new = apply(_state(p), DevelopTech("irrigation"), db)
    p0 = new.players[0]
    assert "irrigation" in p0.developed
    assert p0.science == 0
    assert p0.civil_actions == 3  # 研发花 1 白点, 拿回 1 白点
    # 无 newton: 白点净 -1
    p2 = _player(hand_civil=("irrigation",), science=3, civil_actions=3)
    new2 = apply(_state(p2), DevelopTech("irrigation"), db)
    assert new2.players[0].civil_actions == 2


def test_shakespeare_static_happiness(db: CardDB) -> None:
    """william_shakespeare: +1 笑脸(静态, T12 审查补登); 研发 -1 白点仍 P2."""
    p = _player(leader="william_shakespeare")
    assert effects.static_bonuses(db, p) == {"happiness": 1}
    civ = civ_values(db, p)
    assert civ.happiness == 1
    assert "P2-DEFERRED" in db.get("william_shakespeare").text


def test_shakespeare_pair_culture(db: CardDB) -> None:
    """william_shakespeare: 每对图书馆-剧院 +2 文化(T13, PDF 第 2 页).

    配对口径(SIMPLIFICATION): 图书馆按已研发卡计(同 leonardo 口径), 剧院
    按有工人的卡计(同 chaplin 口径); 对数 = min(图书馆数, 剧院数)。
    """
    # 2 图书馆 + 1 剧院 -> 1 对 -> +2 文化
    p = _player(
        leader="william_shakespeare",
        developed=("printing_press", "journalism"),
        buildings={"theater": {"drama": 1}})
    assert effects.static_bonuses(db, p) == {"happiness": 1, "culture": 2}
    # 1 图书馆 + 2 剧院(工人分布两张卡) -> 1 对 -> +2 文化
    p2 = _player(
        leader="william_shakespeare",
        developed=("printing_press",),
        buildings={"theater": {"drama": 1, "opera": 1}})
    assert effects.static_bonuses(db, p2) == {"happiness": 1, "culture": 2}
    # 2 图书馆 + 2 剧院 -> 2 对 -> +4 文化
    p3 = _player(
        leader="william_shakespeare",
        developed=("printing_press", "journalism"),
        buildings={"theater": {"drama": 1, "opera": 1}})
    assert effects.static_bonuses(db, p3) == {"happiness": 1, "culture": 4}
    # 剧院无工人不配对
    p4 = _player(
        leader="william_shakespeare",
        developed=("printing_press",),
        buildings={"theater": {}})
    assert effects.static_bonuses(db, p4) == {"happiness": 1}


def test_bach_static_culture_per_theater(db: CardDB) -> None:
    """j_s_bach: 每个剧院 +1 文化(T13, PDF 第 2 页); 折扣/升级见专项测试.

    剧院按有工人的卡计(同 chaplin 口径, 每卡 1 次与工人数无关)。
    """
    p = _player(
        leader="j_s_bach",
        buildings={"theater": {"drama": 2, "opera": 1}})
    assert effects.static_bonuses(db, p) == {"culture": 2}
    civ = civ_values(db, p)
    # 剧院自身文化(drama 2×2 + opera 3×1) + bach 2
    assert civ.culture_rate == (2 * 2 + 3 * 1) + 2
    assert "P2-DEFERRED" not in db.get("j_s_bach").text


def test_cook_deferred(db: CardDB) -> None:
    """cook: 互动能力 P2-DEFERRED, 无钩子."""
    card = db.get("james_cook")
    assert card.handler == ""
    assert "P2-DEFERRED" in card.text
    p = _player(leader="james_cook")
    assert effects.static_bonuses(db, p) == {}


def test_deferred_wonders_no_handler(db: CardDB) -> None:
    """横贯大陆铁路/远洋客轮服务的互动效果 P2-DEFERRED, 无钩子."""
    for card_id in ("transcontinental_railroad", "ocean_liner_service"):
        card = db.get(card_id)
        assert card.handler == "", card_id
        assert "P2-DEFERRED" in card.text, card_id


# --- 行动卡 handler 注册与结算 --------------------------------------------------


def test_age_ii_action_handlers_registered(db: CardDB) -> None:
    """每张时代 II 行动卡 handler 已注册; pending 类与 PENDING_SPECS 成对."""
    for card_id in ACTION_QUANTITIES:
        handler = db.get(card_id).handler
        assert handler in effects.ACTION_HANDLERS, handler
    for name in ("breakthrough_ii", "efficient_upgrade_ii",
                 "engineering_genius_ii", "rich_land_ii", "urban_growth_ii"):
        assert name in effects.PENDING_SPECS
    assert "frugality_ii" in effects.PLAY_CONDITIONS
    assert "reserves_ii" in effects.ACTION_OPTIONS


def test_breakthrough_ii_x3(db: CardDB) -> None:
    """breakthrough_ii: 全价研发后 +3 科技(X=3)."""
    p = _player(hand_civil=("breakthrough_ii", "irrigation"), science=3)
    new = apply(_state(p), PlayActionCard("breakthrough_ii"), db)
    assert new.pending == (PendingEffect("develop_tech", 0, science_gain=3),)
    new2 = apply(new, DevelopTech("irrigation"), db)
    assert new2.players[0].science == 3 - 3 + 3


def test_efficient_upgrade_ii_pending_flow(db: CardDB) -> None:
    """efficient_upgrade_ii: 下一农场/矿场/城市建筑 Upgrade 0 行动点折扣 3.

    仅 Upgrade(不含 Build), 军事单位升级不在其列。
    """
    p = _player(
        hand_civil=("efficient_upgrade_ii",), civil_actions=1,
        developed=("agriculture", "irrigation", "warriors", "swordsmen",
                   "bronze"),
        buildings={"farm": {"agriculture": 1}, "infantry": {"warriors": 1}},
        worker_pool=1, card_tokens={"bronze": 2}, blue_bank=16,
    )
    new = apply(_state(p), PlayActionCard("efficient_upgrade_ii"), db)
    assert new.pending == (PendingEffect("upgrade_farm_mine_urban", 3),)
    legal = legal_actions(db, new)
    assert Upgrade("agriculture", "irrigation") in legal
    # 兵种升级不属于 efficient_upgrade
    assert Upgrade("warriors", "swordsmen") not in legal
    # pending 期间不生成 Build(仅 pending 子行动 + PassTurn)
    assert not [a for a in legal if isinstance(a, Build)]
    new2 = apply(new, Upgrade("agriculture", "irrigation"), db)
    # 差价 4 - 2 = 2, 折扣 3 -> 0, 不取蓝点
    assert new2.players[0].card_tokens == {"bronze": 2}
    assert new2.players[0].buildings["farm"] == {"irrigation": 1}


def test_engineering_genius_ii_x4(db: CardDB) -> None:
    """engineering_genius_ii: 奇迹阶段折扣 4(X=4)."""
    p = _player(hand_civil=("engineering_genius_ii",),
                wonder_progress=("eiffel_tower", 0), developed=("bronze",),
                card_tokens={"bronze": 1}, blue_bank=16)
    new = apply(_state(p), PlayActionCard("engineering_genius_ii"), db)
    assert new.pending == (PendingEffect("wonder_stage", 4),)


def test_frugality_ii_x3(db: CardDB) -> None:
    """frugality_ii: 增人口(全费 2 食物)后 +3 食物(X=3)."""
    p = _player(hand_civil=("frugality_ii",), developed=("agriculture",),
                card_tokens={"agriculture": 2}, yellow_bank=18, worker_pool=1,
                blue_bank=16)
    new = apply(_state(p), PlayActionCard("frugality_ii"), db)
    p0 = new.players[0]
    assert p0.yellow_bank == 17
    assert p0.worker_pool == 2
    assert p0.card_tokens == {"agriculture": 3}  # 付 2 再得 3


def test_patriotism_ii_x3(db: CardDB) -> None:
    """patriotism_ii: 本回合 +1 军事行动, 兵种建造折扣 3(X=3)."""
    p = _player(hand_civil=("patriotism_ii",), military_actions=1,
                developed=("warriors", "bronze"), worker_pool=1,
                card_tokens={"bronze": 1})
    new = apply(_state(p), PlayActionCard("patriotism_ii"), db)
    p0 = new.players[0]
    assert p0.military_actions == 2
    assert p0.turn_discounts == {"unit_build": 3}


def test_reserves_ii_x3_choice(db: CardDB) -> None:
    """reserves_ii: +3 资源或 +3 食物, option 二选一(X=3)."""
    p = _player(hand_civil=("reserves_ii",),
                developed=("agriculture", "bronze"), blue_bank=16)
    state = _state(p)
    legal = legal_actions(db, state)
    assert PlayActionCard("reserves_ii", "resource") in legal
    assert PlayActionCard("reserves_ii", "food") in legal
    new = apply(state, PlayActionCard("reserves_ii", "resource"), db)
    assert new.players[0].card_tokens == {"bronze": 3}
    new2 = apply(state, PlayActionCard("reserves_ii", "food"), db)
    assert new2.players[0].card_tokens == {"agriculture": 3}
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("reserves_ii", "gold"), db)


def test_revolutionary_idea_ii_x4(db: CardDB) -> None:
    """revolutionary_idea_ii: +4 科技(X=4)."""
    p = _player(hand_civil=("revolutionary_idea_ii",), science=1)
    new = apply(_state(p), PlayActionCard("revolutionary_idea_ii"), db)
    p0 = new.players[0]
    assert p0.science == 1 + 4
    assert p0.civil_actions == 3


def test_rich_land_ii_x3(db: CardDB) -> None:
    """rich_land_ii: 下一农场/矿场 Build/Upgrade 0 行动点折扣 3(X=3)."""
    p = _player(hand_civil=("rich_land_ii",), civil_actions=1,
                developed=("agriculture", "bronze"), worker_pool=1,
                card_tokens={"bronze": 1})
    new = apply(_state(p), PlayActionCard("rich_land_ii"), db)
    assert new.pending == (PendingEffect("build_farm_mine", 3),)
    new2 = apply(new, Build("agriculture"), db)
    assert new2.players[0].card_tokens == {"bronze": 1}  # 造价 2 - 3 = 0


def test_urban_growth_ii_x3(db: CardDB) -> None:
    """urban_growth_ii: 下一城市建筑 Build/Upgrade 0 行动点折扣 3(X=3)."""
    p = _player(hand_civil=("urban_growth_ii",), civil_actions=1,
                developed=("philosophy", "bronze"), worker_pool=1,
                card_tokens={"bronze": 2})
    new = apply(_state(p), PlayActionCard("urban_growth_ii"), db)
    assert new.pending == (PendingEffect("build_urban", 3),)
    new2 = apply(new, Build("philosophy"), db)
    assert new2.players[0].card_tokens == {"bronze": 2}  # 3 - 3 = 0


def test_wave_of_nationalism_ii_two_players(db: CardDB) -> None:
    """wave_of_nationalism_ii: 每个更强文明 +6(2p) 本回合兵种建造折扣."""
    p0 = _player(hand_civil=("wave_of_nationalism_ii",),
                 developed=("warriors", "bronze"), worker_pool=1,
                 card_tokens={"bronze": 1})
    p1 = _player(name="P1", developed=("swordsmen",),
                 buildings={"infantry": {"swordsmen": 2}})
    new = apply(_state(p0, p1), PlayActionCard("wave_of_nationalism_ii"), db)
    # p1 军力 2×2=4 > p0 的 0 -> 折扣 1 × 6 = 6
    assert new.players[0].turn_discounts == {"unit_build": 6}
    new2 = apply(new, Build("warriors"), db)
    assert new2.players[0].card_tokens == {"bronze": 1}  # 造价 2 - 6 = 0


def test_wave_of_nationalism_ii_three_players(db: CardDB) -> None:
    """wave_of_nationalism_ii: 3p 每个更强文明 +3; 无人更强时无折扣."""
    p0 = _player(hand_civil=("wave_of_nationalism_ii",))
    p1 = _player(name="P1", developed=("warriors",),
                 buildings={"infantry": {"warriors": 1}})
    p2 = _player(name="P2", developed=("swordsmen",),
                 buildings={"infantry": {"swordsmen": 1}})
    new = apply(_state(p0, p1, p2),
                PlayActionCard("wave_of_nationalism_ii"), db)
    # p1 军力 1、p2 军力 2, 均 > 0 -> 2 × 3 = 6
    assert new.players[0].turn_discounts == {"unit_build": 6}
    # 最强者打出: 无人更强 -> 无折扣
    strong = _player(hand_civil=("wave_of_nationalism_ii",),
                     developed=("swordsmen",),
                     buildings={"infantry": {"swordsmen": 2}})
    new2 = apply(_state(strong, p1, p2),
                 PlayActionCard("wave_of_nationalism_ii"), db)
    assert new2.players[0].turn_discounts == {}


# --- shakespeare 图书馆/剧院配对折扣(P3-T6) -------------------------------------


def test_shakespeare_theater_discount_with_library(db: CardDB) -> None:
    """shakespeare: 有已研发图书馆时, 建造剧院 -1 资源(PDF 第 2 页).

    drama 造价 4 -> 付 3; 多张图书馆不叠加(一次 -1)。
    """
    p = _player(leader="william_shakespeare",
                developed=("printing_press", "journalism", "drama", "bronze"),
                worker_pool=1, card_tokens={"bronze": 5}, blue_bank=16)
    state = _state(p)
    assert Build("drama") in legal_actions(db, state)
    new = apply(state, Build("drama"), db)
    assert new.players[0].card_tokens == {"bronze": 2}


def test_shakespeare_library_discount_with_theater(db: CardDB) -> None:
    """shakespeare: 有已研发剧院时, 建造图书馆 -1 资源(vice versa)."""
    p = _player(leader="william_shakespeare",
                developed=("drama", "printing_press", "bronze"),
                worker_pool=1, card_tokens={"bronze": 3}, blue_bank=16)
    # printing_press 造价 3 - 1 = 2
    new = apply(_state(p), Build("printing_press"), db)
    assert new.players[0].card_tokens == {"bronze": 1}


def test_shakespeare_upgrade_discount(db: CardDB) -> None:
    """shakespeare: 升级剧院(有图书馆)差价 -1; drama->opera 差 4 -> 付 3."""
    p = _player(leader="william_shakespeare",
                developed=("printing_press", "drama", "opera", "bronze"),
                buildings={"theater": {"drama": 1}},
                card_tokens={"bronze": 3}, blue_bank=16)
    state = _state(p)
    assert Upgrade("drama", "opera") in legal_actions(db, state)
    new = apply(state, Upgrade("drama", "opera"), db)
    assert new.players[0].card_tokens == {}
    assert new.players[0].buildings["theater"] == {"opera": 1}


def test_shakespeare_no_discount_without_pair(db: CardDB) -> None:
    """shakespeare: 无配对类别(图书馆未研发)时无折扣; 非 shakespeare 无折扣."""
    p = _player(leader="william_shakespeare",
                developed=("drama", "bronze"),
                worker_pool=1, card_tokens={"bronze": 4}, blue_bank=16)
    new = apply(_state(p), Build("drama"), db)
    assert new.players[0].card_tokens == {}  # 全价 4
    p2 = _player(developed=("printing_press", "drama", "bronze"),
                 worker_pool=1, card_tokens={"bronze": 4}, blue_bank=16)
    new2 = apply(_state(p2), Build("drama"), db)
    assert new2.players[0].card_tokens == {}  # 无领袖, 全价 4


# --- j_s_bach 剧院研发折扣与每回合升级(P3-T6) ------------------------------------


def test_bach_theater_science_discount(db: CardDB) -> None:
    """j_s_bach: 研发剧院科技 -2 科技(PDF 第 2 页图标为科技).

    drama 研发费 3 -> 付 1; 非剧院科技无折扣。
    """
    p = _player(leader="j_s_bach", hand_civil=("drama", "irrigation"),
                science=3)
    state = _state(p)
    assert DevelopTech("drama") in legal_actions(db, state)
    new = apply(state, DevelopTech("drama"), db)
    assert new.players[0].science == 2  # 3 - (3 - 2)
    # 折扣后科技不足也可研发: science=1 即可研发 drama
    p2 = _player(leader="j_s_bach", hand_civil=("drama",), science=1)
    assert DevelopTech("drama") in legal_actions(db, _state(p2))
    # 非剧院科技(irrigation 3 科技)无折扣: science=2 不可研发
    p3 = _player(leader="j_s_bach", hand_civil=("irrigation",), science=2)
    assert DevelopTech("irrigation") not in legal_actions(db, _state(p3))


def test_bach_upgrade_same_level(db: CardDB) -> None:
    """j_s_bach: 1 白点把城市建筑升级为同级剧院(每回合一次).

    organized_religion(时代 II 寺庙, 造价 7) -> opera(时代 II 剧院, 造价 8):
    差价 1; 结算后 turn_discounts 记 bach_upgrade。
    """
    p = _player(leader="j_s_bach",
                developed=("religion", "organized_religion", "drama", "opera",
                           "bronze"),
                buildings={"temple": {"religion": 1, "organized_religion": 1}},
                card_tokens={"bronze": 2}, blue_bank=16)
    state = _state(p)
    action = Upgrade("organized_religion", "opera")
    assert action in legal_actions(db, state)
    new = apply(state, action, db)
    p0 = new.players[0]
    assert p0.buildings["temple"] == {"religion": 1}
    assert p0.buildings["theater"] == {"opera": 1}
    assert p0.card_tokens == {"bronze": 1}  # 差价 8 - 7 = 1
    assert p0.civil_actions == 3  # 1 白点
    assert p0.turn_discounts == {effects.BACH_UPGRADE_KEY: 1}
    # 每回合一次: 本回合另一城市建筑不可再 bach 升级为剧院
    assert Upgrade("religion", "drama") not in legal_actions(db, new)


def test_bach_upgrade_one_level_higher(db: CardDB) -> None:
    """j_s_bach: 可升级为高一级剧院(religion A -> drama I); +2 级不可."""
    p = _player(leader="j_s_bach",
                developed=("religion", "drama", "opera", "bronze"),
                buildings={"temple": {"religion": 1}},
                card_tokens={"bronze": 5}, blue_bank=16)
    legal = legal_actions(db, _state(p))
    # religion(时代 A) -> drama(时代 I): +1 级, 合法
    assert Upgrade("religion", "drama") in legal
    # religion(时代 A) -> opera(时代 II): +2 级, 不合法
    assert Upgrade("religion", "opera") not in legal
    new = apply(_state(p), Upgrade("religion", "drama"), db)
    assert new.players[0].card_tokens == {"bronze": 4}  # 差价 4 - 3 = 1


def test_bach_upgrade_requires_bach_and_target_slot(db: CardDB) -> None:
    """跨类别升级为剧院仅 bach 可用; 目标剧院须已研发且有空槽."""
    # 无 bach: religion -> drama 不合法(跨类别)
    p = _player(developed=("religion", "drama", "bronze"),
                buildings={"temple": {"religion": 1}},
                card_tokens={"bronze": 5}, blue_bank=16)
    assert Upgrade("religion", "drama") not in legal_actions(db, _state(p))
    # bach 但剧院未研发: 不合法
    p2 = _player(leader="j_s_bach",
                 developed=("religion", "bronze"),
                 buildings={"temple": {"religion": 1}},
                 card_tokens={"bronze": 5}, blue_bank=16)
    assert Upgrade("religion", "drama") not in legal_actions(db, _state(p2))


# --- masonry 系列: 奇迹多阶段 + 城市建筑折扣(P3-T6) -------------------------------


def test_masonry_wonder_two_stages(db: CardDB) -> None:
    """masonry: 1 白点可建最多 2 个奇迹阶段(费用求和, 蓝点逐阶段盖).

    pyramids 阶段 (3, 2, 1): BuildWonderStage(2) 付 3+2=5, 盖 2 蓝点。
    """
    p = _player(developed=("masonry", "bronze"),
                wonder_progress=("pyramids", 0),
                card_tokens={"bronze": 6}, blue_bank=16)
    state = _state(p)
    legal = legal_actions(db, state)
    assert BuildWonderStage(2) in legal
    assert BuildWonderStage(1) in legal
    assert BuildWonderStage() == BuildWonderStage(1)
    # masonry 每白点最多 2 阶段
    assert BuildWonderStage(3) not in legal
    new = apply(state, BuildWonderStage(2), db)
    p0 = new.players[0]
    assert p0.card_tokens == {"bronze": 1}
    # 付 5 资源(蓝点回银行 +5), 盖 2 阶段(-2)
    assert p0.blue_bank == 16 + 5 - 2
    assert p0.wonder_progress == ("pyramids", 2)
    assert p0.civil_actions == 3  # 整次动作仅 1 白点


def test_architecture_wonder_three_stages_completes(db: CardDB) -> None:
    """architecture: 1 白点最多 3 阶段; 完成时阶段蓝点全部放回."""
    p = _player(developed=("architecture", "bronze"),
                wonder_progress=("kremlin", 0),
                card_tokens={"bronze": 12}, blue_bank=16)
    state = _state(p)
    legal = legal_actions(db, state)
    assert BuildWonderStage(3) in legal
    assert BuildWonderStage(4) not in legal  # kremlin 仅 3 阶段
    new = apply(state, BuildWonderStage(3), db)
    p0 = new.players[0]
    assert p0.card_tokens == {}  # 4+4+4 = 12
    assert p0.wonder_progress is None
    assert p0.wonders == ("kremlin",)
    # 付 12 资源(蓝点回银行 +12), 盖 3 放 3
    assert p0.blue_bank == 16 + 12


def test_engineering_wonder_four_stages(db: CardDB) -> None:
    """engineering: 1 白点最多 4 阶段; 无 construction 卡时仅 1 阶段."""
    p = _player(developed=("engineering", "bronze"),
                wonder_progress=("transcontinental_railroad", 0),
                card_tokens={"bronze": 12}, blue_bank=16)
    legal = legal_actions(db, _state(p))
    assert BuildWonderStage(4) in legal
    assert BuildWonderStage(5) not in legal
    # 无 construction 卡: 仅单阶段(回归)
    p2 = _player(developed=("bronze",),
                 wonder_progress=("transcontinental_railroad", 0),
                 card_tokens={"bronze": 12}, blue_bank=16)
    legal2 = legal_actions(db, _state(p2))
    assert BuildWonderStage(1) in legal2
    assert BuildWonderStage(2) not in legal2


def test_wonder_multi_stage_blue_bank_limit(db: CardDB) -> None:
    """多阶段建造: 蓝点不足 count 时该 count 不合法(逐阶段盖蓝点)."""
    p = _player(developed=("masonry", "bronze"),
                wonder_progress=("pyramids", 0),
                card_tokens={"bronze": 6}, blue_bank=1)
    legal = legal_actions(db, _state(p))
    assert BuildWonderStage(1) in legal
    assert BuildWonderStage(2) not in legal
    # 资源不足两阶段时同样只枚举 1 阶段
    p2 = _player(developed=("masonry", "bronze"),
                 wonder_progress=("pyramids", 0),
                 card_tokens={"bronze": 4}, blue_bank=16)
    legal2 = legal_actions(db, _state(p2))
    assert BuildWonderStage(1) in legal2
    assert BuildWonderStage(2) not in legal2


def test_masonry_urban_build_discount(db: CardDB) -> None:
    """masonry: 建造城市建筑每级 -1 资源(最多 1; 级 = 时代序 A=0/I=1/II=2).

    drama(时代 I, 1 级) -1; philosophy(时代 A, 0 级) 无折扣(官方规则书例:
    时代 A 建筑不享折扣)。
    """
    p = _player(developed=("masonry", "drama", "philosophy", "bronze"),
                worker_pool=2, card_tokens={"bronze": 6}, blue_bank=16)
    state = _state(p)
    new = apply(state, Build("drama"), db)
    assert new.players[0].card_tokens == {"bronze": 3}  # 4 - 1
    new2 = apply(new, Build("philosophy"), db)
    assert new2.players[0].card_tokens == {}  # 全价 3


def test_architecture_urban_build_discount(db: CardDB) -> None:
    """architecture: 建造城市建筑每级 -1 资源(最多 2); opera(II, 2 级) -2."""
    p = _player(developed=("architecture", "opera", "bronze"),
                worker_pool=1, card_tokens={"bronze": 6}, blue_bank=16)
    new = apply(_state(p), Build("opera"), db)
    assert new.players[0].card_tokens == {}  # 8 - 2 = 6


def test_masonry_urban_upgrade_discount(db: CardDB) -> None:
    """masonry: 升级城市建筑按双边折后差价(官方规则书例).

    philosophy(A 实验室 3, 无折扣) -> alchemy(I 实验室 6, -1): 付 2(比无
    masonry 的 3 便宜 1); alchemy(I, -1) -> scientific_method(II, -1):
    付 2(与无 masonry 相同, 两级同折扣抵消)。
    """
    p = _player(developed=("masonry", "philosophy", "alchemy", "bronze"),
                buildings={"lab": {"philosophy": 1}},
                card_tokens={"bronze": 2}, blue_bank=16)
    state = _state(p)
    assert Upgrade("philosophy", "alchemy") in legal_actions(db, state)
    new = apply(state, Upgrade("philosophy", "alchemy"), db)
    assert new.players[0].card_tokens == {}  # (6-1) - 3 = 2
    p2 = _player(developed=("masonry", "alchemy", "scientific_method", "bronze"),
                 buildings={"lab": {"alchemy": 1}},
                 card_tokens={"bronze": 2}, blue_bank=16)
    new2 = apply(_state(p2), Upgrade("alchemy", "scientific_method"), db)
    assert new2.players[0].card_tokens == {}  # (8-1) - (6-1) = 2


def test_urban_discount_without_construction_card(db: CardDB) -> None:
    """无 construction 卡时建造城市建筑全价(回归)."""
    p = _player(developed=("drama", "bronze"),
                worker_pool=1, card_tokens={"bronze": 4}, blue_bank=16)
    new = apply(_state(p), Build("drama"), db)
    assert new.players[0].card_tokens == {}
