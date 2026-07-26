"""时代 III 事件(15 张 Impact 计分类)与终局结算测试(P2-T12).

文本以卡牌数值表 PDF 第 4 页 Events 表 Age III 行为准(全为自动计分,
无玩家决策 pending):

- impact_of_agriculture: +文化 = 农场产出(Σ 农场工人 × token_value);
  产出 > 消耗(黄点轨道)再 +4;
- impact_of_architecture: +文化 = 城市建筑等级总和(每工人 = 一张同级卡,
  级 = 时代序, A=1);
- impact_of_balance: +文化 = 2 × min(科技/文化/食物/资源 四项产出);
- impact_of_colonies: 每殖民地 +3 文化;
- impact_of_competition: +文化 = 军事单位与竞技场的等级总和;
- impact_of_government: +2 文化/内政行动, +1 文化/军事行动(civ 总值);
- impact_of_happiness: +2 文化/笑脸, -2 文化/不快乐工人(文化下限 0);
- impact_of_industry: +文化 = 矿场资源产出;
- impact_of_population: 超过 10 的每个人口 +2 文化(人口 = 工人总数);
- impact_of_progress: +2 文化 × (政体等级 + 特殊科技等级和);
- impact_of_science / impact_of_strength: 按科技增速/军力排名计分
  (2p 10/0, 3p 14/7/0, 4p 15/10/5/0); 平局按当前玩家顺时针近者优先
  (终局结算时起始玩家视作当前玩家, 规则书 p7);
- impact_of_technology: 每项时代 III 科技 +4 文化(政体算科技);
- impact_of_variety: +2 文化/类型(军事单位、城市建筑、特殊科技);
- impact_of_wonders: 每奇迹按时代 +5/4/3/2(A/I/II/III); 翻面奇迹
  (ravages_of_time)仍计入(规则书附录 p12: 被摧残的奇迹仍视作相应时代
  的已完成奇迹)。

终局(turn.proceed 最后一轮回绕): current_events 先、future_events 后,
各自原顺序结算两堆中所有时代 III 事件(其余卡留堆不结算) -> 终局奖励
(bill_gates: +文化 = 实验室额外产出 = Σ 有工人实验室 工人数 × 等级;
实验室每回合产资源的经济改造 P2-DEFERRED) -> final_scores = 终局文化。
"""

from dataclasses import replace

import pytest

from tta.cards import build_card_db
from tta.engine import events, turn
from tta.engine.actions import SeedEvent
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType, Phase
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PlayerState,
    replace_player,
)

_INITIAL_DEVELOPED = (
    "agriculture", "agriculture", "bronze", "bronze",
    "philosophy", "religion", "warriors",
)
_INITIAL_BUILDINGS = {
    "farm": {"agriculture": 2},
    "mine": {"bronze": 2},
    "lab": {"philosophy": 1},
    "infantry": {"warriors": 1},
}
"""默认布局: 农场产出 2, 矿场产出 2, 科技增速 1, 文化增速 0, 军力 1, 笑脸 0."""


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {
        "name": name,
        "developed": _INITIAL_DEVELOPED,
        "buildings": {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()},
    }
    base.update(overrides)
    return PlayerState(**base)


def _state(*, num_players: int = 2, **overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.III,
        "current_player": 0,
        "card_row": (None,) * ROW_SLOTS,
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": tuple(_player(f"P{i}") for i in range(num_players)),
        "rng_state": 42,
        "phase": Phase.POLITICS,
    }
    base.update(overrides)
    return GameState(**base)


def _resolve(db: CardDB, state: GameState, card_id: str) -> GameState:
    return events.resolve_event(state, db, card_id)


def _buildings(**changes: dict[str, int]) -> dict[str, dict[str, int]]:
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings.update({k: dict(v) for k, v in changes.items()})
    return buildings


def _db_with_fake_event(age: Age) -> CardDB:
    """完整牌库 + 一张未注册 handler 的指定时代测试事件卡."""
    db = build_card_db()
    fake = CardDefinition(
        id="fake_event_x", name="假事件", name_en="Fake Event", age=age,
        deck=DeckType.MILITARY, category=CardCategory.EVENT,
        text="测试桩。", handler="fake_event_x", quantities=(0, 0, 0),
    )
    return CardDB(
        cards={**db.cards, fake.id: fake},
        initial_tableau=db.initial_tableau,
        initial_government=db.initial_government,
        initial_workers=db.initial_workers,
    )


# --- 注册完备性 -----------------------------------------------------------------


def test_all_age_iii_events_registered() -> None:
    db = build_card_db()
    age_iii_events = [
        card for card in db.cards.values()
        if card.category is CardCategory.EVENT and card.age is Age.III
    ]
    assert len(age_iii_events) == 15
    for card in age_iii_events:
        assert card.handler in events.EVENT_HANDLERS, card.id


def test_unregistered_age_iii_event_fails_loud() -> None:
    # 时代 III 过场兜底已删除: 未注册事件一律 fail-loud
    db = _db_with_fake_event(Age.III)
    with pytest.raises(ValueError, match="fake_event_x"):
        _resolve(db, _state(), "fake_event_x")


# --- impact_of_agriculture -------------------------------------------------------


def test_impact_of_agriculture_surplus_bonus() -> None:
    db = build_card_db()
    # P0: 农场产出 2, 黄点银行 18 -> 消耗 0, 2 > 0 -> +2 +4 = 6
    # P1: 黄点银行 4 -> 消耗 4, 2 不超 -> +2
    state = _state(players=(_player("P0"), _player("P1", yellow_bank=4)))
    new = _resolve(db, state, "impact_of_agriculture")
    assert new.players[0].culture == 6
    assert new.players[1].culture == 2


# --- impact_of_architecture ------------------------------------------------------


def test_impact_of_architecture_urban_levels() -> None:
    db = build_card_db()
    # P0: philosophy(1 级) + printing_press(2 级) 各 1 工人 -> +3; P1: 仅 philosophy -> +1
    p0 = _player(
        "P0",
        developed=_INITIAL_DEVELOPED + ("printing_press",),
        buildings=_buildings(lab={"philosophy": 1, "printing_press": 1}),
    )
    new = _resolve(db, _state(players=(p0, _player("P1"))),
                   "impact_of_architecture")
    assert new.players[0].culture == 3
    assert new.players[1].culture == 1


# --- impact_of_balance -----------------------------------------------------------


def test_impact_of_balance_two_times_minimum_rate() -> None:
    db = build_card_db()
    # P0: 文化增速 0 -> min = 0 -> +0
    # P1: 宗教工人(文化 1) -> min(1, 1, 2, 2) = 1 -> +2
    p1 = _player("P1", buildings=_buildings(temple={"religion": 1}))
    new = _resolve(db, _state(players=(_player("P0"), p1)), "impact_of_balance")
    assert new.players[0].culture == 0
    assert new.players[1].culture == 2


# --- impact_of_colonies ----------------------------------------------------------


def test_impact_of_colonies_three_per_colony() -> None:
    db = build_card_db()
    p0 = _player(
        "P0", colonies=("historic_territory_i", "developed_territory_i"))
    new = _resolve(db, _state(players=(p0, _player("P1"))), "impact_of_colonies")
    assert new.players[0].culture == 6
    assert new.players[1].culture == 0


# --- impact_of_competition -------------------------------------------------------


def test_impact_of_competition_unit_and_arena_levels() -> None:
    db = build_card_db()
    # P0: warriors(1 级) + bread_and_circuses 竞技场(2 级) -> +3
    # P1: warriors 2 工人(1 级 × 2) -> +2
    p0 = _player(
        "P0",
        developed=_INITIAL_DEVELOPED + ("bread_and_circuses",),
        buildings=_buildings(arena={"bread_and_circuses": 1}),
    )
    p1 = _player("P1", buildings=_buildings(infantry={"warriors": 2}))
    new = _resolve(db, _state(players=(p0, p1)), "impact_of_competition")
    assert new.players[0].culture == 3
    assert new.players[1].culture == 2


# --- impact_of_government --------------------------------------------------------


def test_impact_of_government_action_points() -> None:
    db = build_card_db()
    # P0 专制(4 白 2 红) -> 2×4 + 2 = 10; P1 君主制(5 白 3 红) -> 2×5 + 3 = 13
    new = _resolve(
        db,
        _state(players=(_player("P0"), _player("P1", government="monarchy"))),
        "impact_of_government")
    assert new.players[0].culture == 10
    assert new.players[1].culture == 13


# --- impact_of_happiness ---------------------------------------------------------


def test_impact_of_happiness_smiles_and_discontent() -> None:
    db = build_card_db()
    # P0: 黄点银行 12 -> 幸福需求 2, 笑脸 0 -> 2 不快乐工人 -> 10 - 4 = 6
    # P1: 宗教工人 1 笑脸, 需求 0 -> +2
    p0 = _player("P0", culture=10, yellow_bank=12)
    p1 = _player("P1", buildings=_buildings(temple={"religion": 1}))
    new = _resolve(db, _state(players=(p0, p1)), "impact_of_happiness")
    assert new.players[0].culture == 6
    assert new.players[1].culture == 2


def test_impact_of_happiness_culture_floor_zero() -> None:
    db = build_card_db()
    # 文化 1, 2 不快乐工人 -> -4, 下限 0
    p0 = _player("P0", culture=1, yellow_bank=12)
    new = _resolve(db, _state(players=(p0, _player("P1"))),
                   "impact_of_happiness")
    assert new.players[0].culture == 0


# --- impact_of_industry ----------------------------------------------------------


def test_impact_of_industry_mine_production() -> None:
    db = build_card_db()
    p1 = _player("P1", buildings=_buildings(mine={"bronze": 1}))
    new = _resolve(db, _state(players=(_player("P0"), p1)), "impact_of_industry")
    assert new.players[0].culture == 2
    assert new.players[1].culture == 1


# --- impact_of_population --------------------------------------------------------


def test_impact_of_population_over_ten() -> None:
    db = build_card_db()
    # P0: 工人总数 7(池) + 6(卡上) = 13 -> 超过 10 有 3 -> +6; P1: 共 7 -> +0
    p0 = _player("P0", worker_pool=7)
    new = _resolve(db, _state(players=(p0, _player("P1"))),
                   "impact_of_population")
    assert new.players[0].culture == 6
    assert new.players[1].culture == 0


# --- impact_of_progress ----------------------------------------------------------


def test_impact_of_progress_government_and_specials() -> None:
    db = build_card_db()
    # P0: 专制(1 级) + code_of_laws(2 级特殊科技) -> 2 × 3 = 6; P1: 仅专制 -> +2
    p0 = _player("P0", developed=_INITIAL_DEVELOPED + ("code_of_laws",))
    new = _resolve(db, _state(players=(p0, _player("P1"))), "impact_of_progress")
    assert new.players[0].culture == 6
    assert new.players[1].culture == 2


# --- impact_of_science / impact_of_strength(排名计分) ------------------------------


def test_impact_of_science_ranking_3p() -> None:
    db = build_card_db()
    # 科技增速 P0=3, P1=1, P2=2 -> 14/0/7
    p0 = _player(
        "P0",
        developed=_INITIAL_DEVELOPED + ("alchemy",),
        buildings=_buildings(lab={"philosophy": 1, "alchemy": 1}),
    )
    p2 = _player(
        "P2",
        developed=_INITIAL_DEVELOPED + ("alchemy",),
        buildings=_buildings(lab={"alchemy": 1}),
    )
    state = _state(num_players=3, players=(p0, _player("P1"), p2))
    new = _resolve(db, state, "impact_of_science")
    assert [p.culture for p in new.players] == [14, 0, 7]


def test_impact_of_science_ranking_2p() -> None:
    db = build_card_db()
    # 2 人局 10/0: P1 科技增速更高 -> P1 +10
    p1 = _player(
        "P1",
        developed=_INITIAL_DEVELOPED + ("alchemy",),
        buildings=_buildings(lab={"philosophy": 1, "alchemy": 1}),
    )
    new = _resolve(db, _state(players=(_player("P0"), p1)),
                   "impact_of_science")
    assert [p.culture for p in new.players] == [0, 10]


def test_impact_of_science_tie_broken_clockwise_from_current() -> None:
    db = build_card_db()
    # 科技增速相同(均为 1): 当前玩家 1 号位 -> 顺时针近者优先, P1 +10
    state = _state(current_player=1)
    new = _resolve(db, state, "impact_of_science")
    assert [p.culture for p in new.players] == [0, 10]


def test_impact_of_strength_ranking_4p() -> None:
    db = build_card_db()
    # 军力 P0=3, P1=2, P2=1, P3=0 -> 15/10/5/0
    players = tuple(
        _player(f"P{i}", buildings=_buildings(infantry={"warriors": n}))
        for i, n in enumerate((3, 2, 1, 0))
    )
    state = _state(num_players=4, players=players)
    new = _resolve(db, state, "impact_of_strength")
    assert [p.culture for p in new.players] == [15, 10, 5, 0]


# --- impact_of_technology --------------------------------------------------------


def test_impact_of_technology_age_iii_techs() -> None:
    db = build_card_db()
    # P0: computers + oil(2 项 III 级科技) -> +8; P1: 民主制(III 级政体算科技) -> +4
    p0 = _player("P0", developed=_INITIAL_DEVELOPED + ("computers", "oil"))
    p1 = _player("P1", government="democracy")
    new = _resolve(db, _state(players=(p0, p1)), "impact_of_technology")
    assert new.players[0].culture == 8
    assert new.players[1].culture == 4


# --- impact_of_variety -----------------------------------------------------------


def test_impact_of_variety_type_count() -> None:
    db = build_card_db()
    # P0: 城市建筑 1 类(philosophy) + 兵种 1 类(warriors) -> 2 类 -> +4
    # P1: 城市建筑 2 类(+religion), 兵种 2 类(+knights), 特殊 1 类(code_of_laws)
    #     -> 5 类 -> +10
    p1 = _player(
        "P1",
        developed=_INITIAL_DEVELOPED + ("knights", "code_of_laws"),
        buildings=_buildings(
            temple={"religion": 1}, cavalry={"knights": 1}),
    )
    new = _resolve(db, _state(players=(_player("P0"), p1)), "impact_of_variety")
    assert new.players[0].culture == 4
    assert new.players[1].culture == 10


# --- impact_of_wonders(翻面奇迹仍计入) ---------------------------------------------


def test_impact_of_wonders_by_age_including_facedown() -> None:
    db = build_card_db()
    # P0: pyramids(A, 5, 已翻面仍计入) + great_wall(I, 4) + eiffel_tower(II, 3)
    #     + internet(III, 2) -> +14; P1: colossus(A) -> +5
    p0 = _player(
        "P0",
        wonders=("pyramids", "great_wall", "eiffel_tower", "internet"),
        wonders_facedown=("pyramids",),
    )
    p1 = _player("P1", wonders=("colossus",))
    new = _resolve(db, _state(players=(p0, p1)), "impact_of_wonders")
    assert new.players[0].culture == 14
    assert new.players[1].culture == 5


# --- 揭示端到端(政治阶段揭示即结算) --------------------------------------------------


def test_reveal_impact_event_scores_immediately() -> None:
    db = build_card_db()
    p0 = _player("P0", colonies=("historic_territory_i",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("impact_of_colonies", "development_of_science"),
    )
    state = replace_player(state, 0, replace(
        state.players[0], hand_military=("development_of_crafts",)))
    new = apply(state, SeedEvent("development_of_crafts"), db)
    assert new.players[0].culture == 3
    assert new.players[1].culture == 0
    assert new.past_events == ("impact_of_colonies",)
    assert new.current_events == ("development_of_science",)
    assert new.future_events == ("development_of_crafts",)
    assert new.phase is Phase.ACTION


# --- 终局结算(turn.proceed 回绕 -> events.endgame_scoring) ---------------------------

def _endgame_state(**overrides: object) -> GameState:
    """最后一轮末位玩家回合结束前的状态(advance 后回绕触发终局)."""
    base: dict = {
        "round": 5,
        "age": Age.IV,
        "last_round": True,
        "current_player": 1,
        "phase": Phase.ACTION,
    }
    base.update(overrides)
    return _state(**base)


def test_endgame_resolves_current_then_future_events() -> None:
    db = build_card_db()
    # 顺序约定: current_events 先(原顺序), future_events 后(原顺序);
    # 非时代 III 卡(development_of_crafts)不结算并留堆
    p0 = _player(
        "P0", culture=5, colonies=("historic_territory_i",),
        wonders=("pyramids",))
    p1 = _player("P1", culture=7)
    state = _endgame_state(
        players=(p0, p1),
        current_events=("impact_of_colonies", "development_of_crafts"),
        future_events=("impact_of_wonders", "impact_of_population"),
    )
    new = turn.advance(state, db)
    assert new.terminal is True
    # P0: 5 + 3(殖民) + 5(奇迹) + 0(人口 7 不超 10) = 13; P1: 7
    assert new.final_scores == (13, 7)
    assert new.past_events == (
        "impact_of_colonies", "impact_of_wonders", "impact_of_population")
    assert new.current_events == ("development_of_crafts",)
    assert new.future_events == ()


def test_endgame_no_events_keeps_culture_scores() -> None:
    db = build_card_db()
    state = _endgame_state(
        players=(_player("P0", culture=5), _player("P1", culture=7)))
    new = turn.advance(state, db)
    assert new.terminal is True
    assert new.final_scores == (5, 7)


def test_endgame_rating_tie_treats_starting_player_as_current() -> None:
    db = build_card_db()
    # 终局平局: 起始玩家(0 号位)视作当前玩家(规则书 p7), 即使末位行动者为 1 号位
    state = _endgame_state(
        players=(_player("P0", culture=5), _player("P1", culture=7)),
        current_events=("impact_of_science",),
    )
    new = turn.advance(state, db)
    assert new.final_scores == (15, 7)


def test_endgame_bill_gates_bonus() -> None:
    db = build_card_db()
    # bill_gates 终局: +文化 = 实验室额外产出 = philosophy(1 级) + alchemy(2 级) = 3
    p1 = _player(
        "P1", culture=7, leader="bill_gates",
        developed=_INITIAL_DEVELOPED + ("alchemy",),
        buildings=_buildings(lab={"philosophy": 1, "alchemy": 1}),
    )
    state = _endgame_state(players=(_player("P0", culture=5), p1))
    new = turn.advance(state, db)
    assert new.terminal is True
    assert new.final_scores == (5, 10)
