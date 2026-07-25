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
    """architecture: 建造折扣/三阶段 P2-DEFERRED, 无静态钩子."""
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
    """william_shakespeare: +1 笑脸(静态, T12 审查补登); 配对/折扣仍 P2."""
    p = _player(leader="william_shakespeare")
    assert effects.static_bonuses(db, p) == {"happiness": 1}
    civ = civ_values(db, p)
    assert civ.happiness == 1
    assert "P2-DEFERRED" in db.get("william_shakespeare").text


def test_cook_bach_deferred(db: CardDB) -> None:
    """cook/bach: 互动能力 P2-DEFERRED, 无钩子."""
    for card_id in ("james_cook", "j_s_bach"):
        card = db.get(card_id)
        assert card.handler == "", card_id
        assert "P2-DEFERRED" in card.text, card_id
        p = _player(leader=card_id)
        assert effects.static_bonuses(db, p) == {}, card_id


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
