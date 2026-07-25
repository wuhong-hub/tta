"""初始科技与时代 A 官方牌库 + 领袖/奇迹/行动卡钩子测试.

数据来源: Card Reference v1.09 第 1-2 页(权威) + research §3/§4(交叉核对)。
行动卡 X 加成取 PDF Bonus 列的 Age A 值; 张数取 PDF Quantity 列 Age A 值
(时代 A 牌堆不随人数调整, 故 quantities 三列相同)。
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
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    PlayLeader,
    TakeCard,
)
from tta.engine.apply import apply
from tta.engine.civ import civ_values, hand_limit_civil
from tta.engine.enums import Age, CardCategory
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB
from tta.engine.state import ROW_SLOTS, GameState, PendingEffect, PlayerState

INITIAL_TECH_IDS = (
    "agriculture", "bronze", "philosophy", "religion", "warriors", "despotism",
)
LEADER_IDS = (
    "alexander_the_great", "aristotle", "hammurabi", "homer",
    "julius_caesar", "moses",
)
WONDER_IDS = ("pyramids", "colossus", "hanging_gardens", "library_of_alexandria")
# PDF 第 2 页 Actions 表 Quantity 列 Age A 值
ACTION_QUANTITIES = {
    "stockpile": 1,
    "frugality": 2,
    "engineering_genius": 1,
    "patriotism": 1,
    "rich_land": 2,
    "urban_growth": 2,
    "cultural_heritage": 1,
}


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
        "age": Age.A,
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


def test_age_a_deck_composition(db: CardDB) -> None:
    """时代 A 牌堆 20 张 = 6 领袖 + 4 奇迹 + 10 行动牌, 各人数相同."""
    for num_players in (2, 3, 4):
        deck = db.deck_for(Age.A, num_players)
        assert len(deck) == 20
    counts = Counter(db.deck_for(Age.A, 3))
    by_category: dict[CardCategory, dict[str, int]] = {}
    for card_id, n in counts.items():
        by_category.setdefault(db.get(card_id).category, {})[card_id] = n
    assert set(by_category[CardCategory.LEADER]) == set(LEADER_IDS)
    assert all(n == 1 for n in by_category[CardCategory.LEADER].values())
    assert set(by_category[CardCategory.WONDER]) == set(WONDER_IDS)
    assert all(n == 1 for n in by_category[CardCategory.WONDER].values())
    assert by_category[CardCategory.ACTION] == ACTION_QUANTITIES
    assert sum(ACTION_QUANTITIES.values()) == 10


def test_age_a_deck_contains_no_tech(db: CardDB) -> None:
    """时代 A 牌堆无科技牌(初始科技印在版图上, 不入牌堆)."""
    deck = db.deck_for(Age.A, 3)
    assert not any(db.get(c).category in (
        CardCategory.FARM, CardCategory.MINE, CardCategory.LAB,
        CardCategory.TEMPLE, CardCategory.INFANTRY, CardCategory.GOVERNMENT,
    ) for c in deck)


# --- 初始科技 ---------------------------------------------------------------


def test_initial_tech_values(db: CardDB) -> None:
    agriculture = db.get("agriculture")
    assert agriculture.category is CardCategory.FARM
    assert agriculture.build_cost == 2
    assert agriculture.token_value == 1

    bronze = db.get("bronze")
    assert bronze.category is CardCategory.MINE
    assert bronze.build_cost == 2
    assert bronze.token_value == 1

    philosophy = db.get("philosophy")
    assert philosophy.category is CardCategory.LAB
    assert philosophy.build_cost == 3
    assert philosophy.urban_produces == {"science": 1}

    religion = db.get("religion")
    assert religion.category is CardCategory.TEMPLE
    assert religion.build_cost == 3
    assert religion.urban_produces == {"culture": 1, "happiness": 1}

    warriors = db.get("warriors")
    assert warriors.category is CardCategory.INFANTRY
    assert warriors.build_cost == 2
    assert warriors.strength == 1

    despotism = db.get("despotism").government
    assert despotism is not None
    assert despotism.civil_actions == 4
    assert despotism.military_actions == 2
    assert despotism.urban_limit == 2


def test_initial_techs_not_in_deck(db: CardDB) -> None:
    """初始科技 quantities 恒 (0,0,0), 不进入任何时代牌堆."""
    for card_id in INITIAL_TECH_IDS:
        assert db.get(card_id).quantities == (0, 0, 0)


def test_initial_tableau(db: CardDB) -> None:
    """初始台面: agriculture×2/bronze×2/philosophy/religion/warriors, 政体专制."""
    assert db.initial_tableau == (
        "agriculture", "agriculture", "bronze", "bronze",
        "philosophy", "religion", "warriors",
    )
    assert db.initial_government == "despotism"


# --- 奇迹数值与 bonus 入 civ -------------------------------------------------


def test_age_a_wonder_definitions(db: CardDB) -> None:
    assert db.get("pyramids").wonder_stages == (3, 2, 1)
    assert db.get("pyramids").wonder_bonus == {"civil_actions": 1}
    assert db.get("colossus").wonder_stages == (3, 3)
    assert db.get("colossus").wonder_bonus == {"strength": 2, "colonization": 1}
    assert db.get("hanging_gardens").wonder_stages == (2, 2, 2)
    assert db.get("hanging_gardens").wonder_bonus == {"culture": 1, "happiness": 2}
    assert db.get("library_of_alexandria").wonder_stages == (1, 4, 1)
    assert db.get("library_of_alexandria").wonder_bonus == {
        "culture": 1, "science": 1,
        "civil_hand_extra": 1, "military_hand_extra": 1,
    }


def test_wonder_bonuses_in_civ(db: CardDB) -> None:
    p = _player(wonders=WONDER_IDS)
    civ = civ_values(db, p)
    assert civ.culture_rate == 2          # hanging_gardens + library_of_alexandria
    assert civ.science_rate == 1          # library_of_alexandria
    assert civ.happiness == 2             # hanging_gardens
    assert civ.civil_actions == 4 + 1     # pyramids
    assert civ.strength == 2              # colossus
    assert civ.colonization == 1          # colossus
    assert civ.military_hand_extra == 1   # library_of_alexandria
    assert hand_limit_civil(db, p) == 5 + 1  # 内政手牌上限 +1


def test_library_of_alexandria_produces_after_completion(db: CardDB) -> None:
    """端到端: 建完 3 阶段(1/4/1)后文化/科技增速各 +1."""
    p = _player(wonder_progress=("library_of_alexandria", 0),
                developed=("bronze",), card_tokens={"bronze": 6},
                blue_bank=16)
    state = _state(p)
    for _ in range(3):
        state = apply(state, BuildWonderStage(), db)
    p0 = state.players[0]
    assert p0.wonders == ("library_of_alexandria",)
    assert p0.wonder_progress is None
    civ = civ_values(db, p0)
    assert civ.culture_rate == 1
    assert civ.science_rate == 1


# --- 行动卡 handler 注册 ------------------------------------------------------


def test_action_handlers_and_pending_specs_registered(db: CardDB) -> None:
    """每张时代 A 行动卡的 handler 均已注册; pending 类与 PENDING_SPECS 成对."""
    for card_id in ACTION_QUANTITIES:
        handler = db.get(card_id).handler
        assert handler in effects.ACTION_HANDLERS, handler
    for name in ("engineering_genius", "rich_land", "urban_growth"):
        assert name in effects.ACTION_HANDLERS
        assert name in effects.PENDING_SPECS


def test_stockpile_handler(db: CardDB) -> None:
    p = _player(hand_civil=("stockpile",), developed=("agriculture", "bronze"),
                blue_bank=16)
    new = apply(_state(p), PlayActionCard("stockpile"), db)
    p0 = new.players[0]
    assert p0.card_tokens == {"agriculture": 1, "bronze": 1}
    assert p0.blue_bank == 14
    assert p0.civil_actions == 3
    assert new.discard == ("stockpile",)


def test_frugality_handler_increase_population(db: CardDB) -> None:
    """增人口(全费 2 食物)后 +1 食物."""
    p = _player(hand_civil=("frugality",), developed=("agriculture",),
                card_tokens={"agriculture": 2}, yellow_bank=18, worker_pool=1,
                blue_bank=16)
    new = apply(_state(p), PlayActionCard("frugality"), db)
    p0 = new.players[0]
    assert p0.yellow_bank == 17
    assert p0.worker_pool == 2
    assert p0.card_tokens == {"agriculture": 1}  # 付 2 再得 1
    assert p0.civil_actions == 3


def test_frugality_unplayable_when_cannot_increase_population(db: CardDB) -> None:
    p = _player(hand_civil=("frugality",), developed=("agriculture",),
                card_tokens={})
    state = _state(p)
    assert PlayActionCard("frugality") not in legal_actions(db, state)
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("frugality"), db)


def test_engineering_genius_pending_flow(db: CardDB) -> None:
    p = _player(hand_civil=("engineering_genius",),
                wonder_progress=("pyramids", 0), developed=("bronze",),
                card_tokens={"bronze": 1}, blue_bank=16)
    new = apply(_state(p), PlayActionCard("engineering_genius"), db)
    assert new.pending == (PendingEffect("wonder_stage", 2),)
    assert legal_actions(db, new) == [BuildWonderStage(), PassTurn()]
    new2 = apply(new, BuildWonderStage(), db)
    p2 = new2.players[0]
    assert p2.wonder_progress == ("pyramids", 1)
    assert p2.card_tokens == {}      # 阶段费 3 - 折扣 2 = 1
    # 支付 1 蓝点放回供给区 (16+1), 再从供给区盖 1 蓝点上奇迹 (-1)
    assert p2.blue_bank == 16


def test_patriotism_handler(db: CardDB) -> None:
    p = _player(hand_civil=("patriotism",), military_actions=1,
                developed=("warriors", "bronze"), worker_pool=1,
                card_tokens={"bronze": 1})
    new = apply(_state(p), PlayActionCard("patriotism"), db)
    p0 = new.players[0]
    assert p0.military_actions == 2
    assert p0.turn_discounts == {"unit_build": 1}
    # 本回合兵种建造折扣 1: 造价 2 - 1 = 1
    assert Build("warriors") in legal_actions(db, new)
    new2 = apply(new, Build("warriors"), db)
    assert new2.players[0].card_tokens == {}
    assert new2.players[0].military_actions == 1


def test_rich_land_pending_flow(db: CardDB) -> None:
    p = _player(hand_civil=("rich_land",), civil_actions=1,
                developed=("agriculture", "bronze"), worker_pool=1,
                card_tokens={"bronze": 1})
    new = apply(_state(p), PlayActionCard("rich_land"), db)
    assert new.pending == (PendingEffect("build_farm_mine", 1),)
    assert new.players[0].civil_actions == 0
    legal = legal_actions(db, new)
    assert Build("agriculture") in legal
    new2 = apply(new, Build("agriculture"), db)
    p2 = new2.players[0]
    assert new2.pending == ()
    assert p2.civil_actions == 0          # 子行动 0 行动点
    assert p2.card_tokens == {}           # 造价 2 - 折扣 1 = 1
    assert p2.buildings == {"farm": {"agriculture": 1}}


def test_urban_growth_pending_flow(db: CardDB) -> None:
    p = _player(hand_civil=("urban_growth",), civil_actions=1,
                developed=("philosophy", "bronze"), worker_pool=1,
                card_tokens={"bronze": 2})
    new = apply(_state(p), PlayActionCard("urban_growth"), db)
    assert new.pending == (PendingEffect("build_urban", 1),)
    assert Build("philosophy") in legal_actions(db, new)
    new2 = apply(new, Build("philosophy"), db)
    p2 = new2.players[0]
    assert p2.card_tokens == {}           # 造价 3 - 折扣 1 = 2
    assert p2.buildings == {"lab": {"philosophy": 1}}


def test_cultural_heritage_handler(db: CardDB) -> None:
    p = _player(hand_civil=("cultural_heritage",))
    new = apply(_state(p), PlayActionCard("cultural_heritage"), db)
    p0 = new.players[0]
    assert p0.science == 1
    assert p0.culture == 4
    assert p0.civil_actions == 3


# --- 领袖钩子 -----------------------------------------------------------------


def test_alexander_strength_per_military_unit(db: CardDB) -> None:
    p = _player(leader="alexander_the_great", developed=("warriors",),
                buildings={"infantry": {"warriors": 2}})
    # 2 武士 × (1 基础 + 1 领袖) = 4
    assert civ_values(db, p).strength == 4


def test_julius_caesar_static_bonus(db: CardDB) -> None:
    civ = civ_values(db, _player(leader="julius_caesar"))
    assert civ.strength == 1
    assert civ.military_actions == 2 + 1


def test_homer_happiness_static_bonus(db: CardDB) -> None:
    assert civ_values(db, _player(leader="homer")).happiness == 1


def test_homer_military_discount_injected_at_turn_end(db: CardDB) -> None:
    """homer 每回合军事建造折扣 1 经 turn_discounts 在回合开始注入."""
    p = _player(leader="homer")
    new = apply(_state(p), PassTurn(), db)
    p0 = new.players[0]
    assert p0.turn_discounts == {"unit_build": 1}
    assert p0.civil_actions == 4  # 行动点已恢复, 折扣供下回合使用


def test_moses_population_food_discount(db: CardDB) -> None:
    assert effects.population_food_discount(db, _player(leader="moses")) == 1
    assert effects.population_food_discount(db, _player()) == 0
    # yellow_bank=18 时人口费 2, moses 减至 1
    assert effects.increase_population_cost(db, _player(yellow_bank=18)) == 2
    assert effects.increase_population_cost(
        db, _player(leader="moses", yellow_bank=18)) == 1


def test_moses_discount_in_frugality(db: CardDB) -> None:
    """moses 在场时 frugality 增人口只付 1 食物; 1 食物时也合法."""
    p = _player(hand_civil=("frugality",), leader="moses",
                developed=("agriculture",), card_tokens={"agriculture": 1},
                yellow_bank=18, worker_pool=1)
    state = _state(p)
    assert PlayActionCard("frugality") in legal_actions(db, state)
    new = apply(state, PlayActionCard("frugality"), db)
    p0 = new.players[0]
    assert p0.yellow_bank == 17
    assert p0.worker_pool == 2
    assert p0.card_tokens == {"agriculture": 1}  # 付 1 再得 1


def test_hammurabi_leader_take_discount(db: CardDB) -> None:
    """拿领袖牌费用 -1 白点: 5 号位(2 点)领袖 1 点可拿."""
    row = _row(None, None, None, None, None, "moses")
    p = _player(leader="hammurabi", civil_actions=1)
    state = _state(p, card_row=row)
    assert TakeCard(5) in legal_actions(db, state)
    new = apply(state, TakeCard(5), db)
    assert new.players[0].civil_actions == 0
    assert new.players[0].hand_civil == ("moses",)
    # 无 hammurabi: 1 白点不够 2 点费
    other = _player(civil_actions=1)
    assert TakeCard(5) not in legal_actions(db, _state(other, card_row=row))


def test_hammurabi_take_leader_discount_apply_no_red_padding(db: CardDB) -> None:
    """修复回归: apply 侧同样扣减领袖拿牌费, 差额不得再从红点垫付.

    hammurabi 玩家 1 白点拿 5 号位(2 费)领袖: 折扣后实付 1 白点,
    结算后白点归零且红点不变。
    """
    row = _row(None, None, None, None, None, "moses")
    p = _player(leader="hammurabi", civil_actions=1, military_actions=2)
    new = apply(_state(p, card_row=row), TakeCard(5), db)
    p0 = new.players[0]
    assert p0.civil_actions == 0
    assert p0.military_actions == 2
    assert p0.hand_civil == ("moses",)


def test_hammurabi_flexible_red_as_white_take_card(db: CardDB) -> None:
    """白点不足支付白点费用时, 每回合一次可用 1 红点抵 1 白点."""
    row = _row(None, None, None, None, None, "stockpile")
    p = _player(leader="hammurabi", civil_actions=1, military_actions=2)
    state = _state(p, card_row=row)
    assert TakeCard(5) in legal_actions(db, state)  # 2 点费 = 1 白 + 1 红
    new = apply(state, TakeCard(5), db)
    p0 = new.players[0]
    assert p0.civil_actions == 0
    assert p0.military_actions == 1
    # 无 hammurabi 不可垫付
    other = _player(civil_actions=1, military_actions=2)
    assert TakeCard(5) not in legal_actions(db, _state(other, card_row=row))


def test_hammurabi_flexible_red_as_white_develop_tech(db: CardDB) -> None:
    p = _player(leader="hammurabi", civil_actions=0, military_actions=1,
                hand_civil=("religion",), science=0)
    state = _state(p)
    assert DevelopTech("religion") in legal_actions(db, state)
    new = apply(state, DevelopTech("religion"), db)
    p0 = new.players[0]
    assert p0.military_actions == 0
    assert p0.turn_discounts == {effects.HAMMURABI_FLEX_KEY: 1}
    assert "religion" in p0.developed


def test_hammurabi_flexible_limited_to_once_per_turn(db: CardDB) -> None:
    """官方规则: 每回合一次, 可将 1 个军事行动当作内政行动使用.

    本回合已垫付(turn_discounts 记录)后, 白点不足的动作不再合法。
    """
    p = _player(leader="hammurabi", civil_actions=0, military_actions=2,
                hand_civil=("religion",), science=0,
                turn_discounts={effects.HAMMURABI_FLEX_KEY: 1})
    assert DevelopTech("religion") not in legal_actions(db, _state(p))


def test_hammurabi_flexible_pads_at_most_one_point(db: CardDB) -> None:
    """每次垫付最多 1 点: 2 点费仅 0 白点时, 2 红点也不可垫付."""
    row = _row(None, None, None, None, None, "stockpile")
    p = _player(leader="hammurabi", civil_actions=0, military_actions=3)
    assert TakeCard(5) not in legal_actions(db, _state(p, card_row=row))
    # 1 白点 + 1 红点垫付 2 点费仍合法
    p = _player(leader="hammurabi", civil_actions=1, military_actions=1)
    assert TakeCard(5) in legal_actions(db, _state(p, card_row=row))


def test_hammurabi_flexible_resets_next_turn(db: CardDB) -> None:
    """垫付标记存于 turn_discounts, 回合结束行动点恢复时清空."""
    p = _player(leader="hammurabi", civil_actions=0, military_actions=1,
                hand_civil=("religion",), science=0)
    state = _state(p)
    new = apply(state, DevelopTech("religion"), db)
    assert new.players[0].turn_discounts == {effects.HAMMURABI_FLEX_KEY: 1}
    new = apply(new, PassTurn(), db)
    # 回合结束: turn_discounts 重置, 下一回合可再次垫付
    assert new.players[0].turn_discounts == {}


def test_aristotle_take_technology_gains_science(db: CardDB) -> None:
    row = _row("agriculture", "stockpile")
    p = _player(leader="aristotle", science=0, developed=())
    new = apply(_state(p, card_row=row), TakeCard(0), db)
    assert new.players[0].science == 1        # 拿科技卡 +1 科技
    assert new.players[0].hand_civil == ("agriculture",)
    # 拿非科技卡(行动卡)不加
    new2 = apply(new, TakeCard(1), db)
    assert new2.players[0].science == 1
    assert new2.players[0].hand_civil == ("agriculture", "stockpile")


def test_moses_discount_in_increase_population(db: CardDB) -> None:
    """moses: IncreasePopulation 动作食物费 -1(银行 18 时 2 -> 1)."""
    p = _player(leader="moses", developed=("agriculture",),
                card_tokens={"agriculture": 1}, yellow_bank=18, worker_pool=1)
    state = _state(p)
    assert IncreasePopulation() in legal_actions(db, state)
    new = apply(state, IncreasePopulation(), db)
    p0 = new.players[0]
    assert p0.civil_actions == 3
    assert p0.card_tokens == {}
    assert p0.yellow_bank == 17
    assert p0.worker_pool == 2


def test_julius_caesar_end_to_end_via_civ_values(db: CardDB) -> None:
    """集成: 真实注册 handler 经 apply(PlayLeader) -> civ_values 端到端生效."""
    p = _player(hand_civil=("julius_caesar",), civil_actions=1)
    new = apply(_state(p), PlayLeader("julius_caesar"), db)
    civ = civ_values(db, new.players[0])
    assert civ.strength == 1
    assert civ.military_actions == 3
