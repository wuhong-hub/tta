"""时代 II 事件处理器测试(P2-T11).

覆盖 15 个时代 II 事件(文本以卡牌数值表 PDF 第 4 页 Events 表 Age II 行
为准; 强弱比较按 civ 军力, 平局按当前玩家顺时针近者优先, 规则书 p7;
2 人局"两个最X"理解为"一个最X"):

- civil_unrest: 每个文明每个不快乐工人(不满 = 黄点轨道幸福需求 - 笑脸,
  见 civ.discontent)-4 文化; 不快乐工人最多的所有文明各 -1 储存蓝点
  (按 (token_value, card_id) 升序取 1 个回供给区, 确定性口径); 全场无
  不快乐工人则无效果;
- cold_war: 两个最强文明各 +6 科技;
- crime_wave: 两个最弱文明各 -3 文化与 -1 科技(下限 0);
- economic_progress: 每名玩家矿场农场立即生产, 不忽略消耗与腐败
  (按回合生产阶段次序: 腐败 -> 食物生产 -> 消耗 -> 资源生产);
- emigration: 每个文明失去一半人口(向上取整, 移回黄点银行);
- iconoclasm: 弃掉所有非当前时代的在场领袖(入内政弃牌堆);
- independence_declaration: 最弱文明失去 1 个殖民地(该玩家选择, 强制
  pending; 永久黄/蓝标记归还, 下限 0; 地区牌入 past_events);
- international_agreement: 最强文明可用最多 5 白点从卡牌列拿牌(逐个
  选择, "done" 提前结束), 跳过其下一次政治行动, 结束后补满卡牌列;
- national_pride: 文化分最多的文明 +5 文化;
- politics_of_strength: 最强 +5 军事牌, 最弱 -3 军事牌(手牌, 按 card_id
  字典序确定弃置, SIMPLIFICATION); 最终时代(III/IV)改为 ±文化(+5/-3);
- popularization_of_science: 每个文明 +文化 = 其科技增速;
- prosperity: 每个文明每个笑脸 +1 人口(至多 8, 黄点银行尽力而为);
- ravages_of_time: 每名玩家将 1 个 A/I 奇迹翻面(选择, 强制 pending;
  翻面奇迹效果失效, 每个转为 +2 文化增速);
- refugees: 最弱 -3 文化与 -1 人口; 最强 +3 文化与 +1 人口;
- terrorism: 文化分最少的文明之外, 其他每个文明各摧毁 1 个城市建筑
  (受害者选择, 强制 pending; 失去口径同 border_conflict: -1 工人回池)。
"""

from dataclasses import replace

import pytest

from tta.cards import build_card_db
from tta.engine import civ, events
from tta.engine.actions import (
    ChooseEventOption,
    DeclineResponse,
    PassTurn,
    SeedEvent,
    SkipPolitics,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType, Phase
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PlayerState,
    from_dict,
    replace_player,
    to_dict,
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
"""默认布局: 军力 1(1 武士), 科技增速 1(哲学), 文化增速 0, 笑脸 0."""


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
        "age": Age.II,
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


def _reveal(db: CardDB, state: GameState) -> GameState:
    """当前玩家军事手牌置入一张筹划卡并打出 SeedEvent, 揭示 current_events 顶."""
    idx = state.current_player
    state = replace_player(state, idx, replace(
        state.players[idx], hand_military=("development_of_crafts",)))
    return apply(state, SeedEvent("development_of_crafts"), db)


def _strong(name: str, warriors: int, **overrides: object) -> PlayerState:
    """军力 = warriors 个武士工人的玩家."""
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": warriors}
    if warriors == 0:
        del buildings["infantry"]
    return _player(name, buildings=buildings, **overrides)


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


def test_all_age_ii_events_registered() -> None:
    db = build_card_db()
    age_ii_events = [
        card for card in db.cards.values()
        if card.category is CardCategory.EVENT and card.age is Age.II
    ]
    assert len(age_ii_events) == 15
    for card in age_ii_events:
        assert card.handler in events.EVENT_HANDLERS, card.id


# --- civil_unrest ----------------------------------------------------------------


def test_civil_unrest_culture_loss_and_blue_token() -> None:
    db = build_card_db()
    # P0 黄点银行 12 -> 幸福需求 2, 笑脸 0 -> 2 个不快乐工人, -8 文化;
    # 不快乐工人最多 -> -1 蓝点(最低价值卡 agriculture, 回供给区)
    p0 = _player("P0", yellow_bank=12, culture=10,
                 card_tokens={"agriculture": 2, "bronze": 1})
    state = _state(
        players=(p0, _player("P1")),
        current_events=("civil_unrest", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].culture == 2
    assert new.players[0].card_tokens == {"agriculture": 1, "bronze": 1}
    assert new.players[0].blue_bank == 17
    # P1 无不快乐工人(黄点银行 18 需求 0): 不受影响
    assert new.players[1].culture == 0
    assert new.players[1].card_tokens == {}


def test_civil_unrest_no_unhappy_workers_no_effect() -> None:
    db = build_card_db()
    state = _state(
        players=(_player("P0", culture=7), _player("P1", culture=9)),
        current_events=("civil_unrest", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].culture == 7
    assert new.players[1].culture == 9


def test_civil_unrest_tied_most_all_lose_blue_token() -> None:
    # 两名玩家不快乐工人数并列最多(黄点银行均 12, 需求 2): 均 -1 蓝点
    db = build_card_db()
    p0 = _player("P0", yellow_bank=12, card_tokens={"bronze": 1})
    p1 = _player("P1", yellow_bank=12, card_tokens={"agriculture": 1})
    state = _state(
        players=(p0, p1),
        current_events=("civil_unrest", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].card_tokens == {}
    assert new.players[1].card_tokens == {}
    assert new.players[0].blue_bank == 17
    assert new.players[1].blue_bank == 17


# --- cold_war --------------------------------------------------------------------


def test_cold_war_two_strongest_gain_science_3p() -> None:
    db = build_card_db()
    # 军力 P0=1, P1=3, P2=2 -> 两个最强 = P1, P2
    state = _state(
        num_players=3,
        players=(_strong("P0", 1), _strong("P1", 3), _strong("P2", 2)),
        current_events=("cold_war", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].science == 0
    assert new.players[1].science == 6
    assert new.players[2].science == 6


def test_cold_war_2p_only_one_strongest() -> None:
    db = build_card_db()
    state = _state(
        players=(_strong("P0", 2), _strong("P1", 1)),
        current_events=("cold_war", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].science == 6
    assert new.players[1].science == 0


# --- crime_wave -------------------------------------------------------------------


def test_crime_wave_weakest_loses_culture_and_science() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong("P1", 1, culture=2, science=5)
    state = _state(
        players=(p0, p1),
        current_events=("crime_wave", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[1].culture == 0   # 2 - 3 下限 0
    assert new.players[1].science == 4   # 5 - 1
    assert new.players[0].culture == 0
    assert new.players[0].science == 0


# --- economic_progress -------------------------------------------------------------


def test_economic_progress_applies_consumption_and_corruption() -> None:
    db = build_card_db()
    # P0: 蓝点银行 10 -> 腐败 2(无储存, 损失到此为止); 黄点银行 14 -> 消耗 2,
    # 食物生产 1 后仍缺 1 -> -4 文化; 矿场照常生产
    p0 = _player("P0", blue_bank=10, yellow_bank=14, culture=10)
    state = _state(
        players=(p0, _player("P1")),
        current_events=("economic_progress", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].card_tokens == {"bronze": 1}
    assert new.players[0].culture == 6
    assert new.players[0].blue_bank == 9
    # P1 无腐败无消耗(蓝 16 / 黄 18): 农场矿场各 +1 蓝点
    assert new.players[1].card_tokens == {"agriculture": 1, "bronze": 1}
    assert new.players[1].blue_bank == 14
    assert new.players[1].culture == 0


# --- emigration ---------------------------------------------------------------------


def test_emigration_loses_half_rounded_up() -> None:
    db = build_card_db()
    # 默认人口 7(空闲 1 + 卡上 6) -> 向上取整失去 4: 空闲池 1, 再按
    # (类别, card_id) 字典序 farm 2 + infantry 1
    state = _state(
        players=(_player("P0"), _player("P1", worker_pool=0)),
        current_events=("emigration", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].worker_pool == 0
    assert new.players[0].buildings["farm"] == {}
    assert new.players[0].buildings["infantry"] == {}
    assert new.players[0].buildings["lab"] == {"philosophy": 1}
    assert new.players[0].yellow_bank == 22
    # P1 人口 6 -> 失去 3: farm 2 + infantry 1
    assert new.players[1].buildings["farm"] == {}
    assert new.players[1].buildings["infantry"] == {}
    assert new.players[1].buildings["lab"] == {"philosophy": 1}
    assert new.players[1].buildings["mine"] == {"bronze": 2}
    assert new.players[1].yellow_bank == 21


# --- iconoclasm ---------------------------------------------------------------------


def test_iconoclasm_discards_non_current_age_leaders() -> None:
    db = build_card_db()
    # 当前时代 II: moses(A) 弃掉; william_shakespeare(II) 保留
    p0 = _player("P0", leader="moses", leader_ages=("A",))
    p1 = _player("P1", leader="william_shakespeare", leader_ages=("II",))
    state = _state(
        players=(p0, p1),
        current_events=("iconoclasm", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].leader is None
    assert new.players[0].leader_ages == ("A",)
    assert new.players[1].leader == "william_shakespeare"
    assert "moses" in new.discard


# --- independence_declaration ---------------------------------------------------------


def test_independence_declaration_weakest_loses_colony() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong("P1", 1, colonies=("developed_territory_i",))
    state = _state(
        players=(p0, p1),
        current_events=("independence_declaration", "development_of_science"),
    )
    new = _reveal(db, state)
    assert len(new.pending) == 1
    assert new.pending[0].kind == events.KIND_EVENT_LOSE_COLONY
    assert new.pending[0].responder == 1
    legal = legal_actions(db, new)
    assert ChooseEventOption("developed_territory_i") in legal
    assert DeclineResponse() not in legal  # 强制失去, 不可放弃
    new = apply(new, ChooseEventOption("developed_territory_i"), db)
    assert new.pending == ()
    assert new.players[1].colonies == ()
    # 永久黄/蓝标记归还(下限 0); 地区牌入 past_events
    assert new.players[1].yellow_bank == 17
    assert new.players[1].blue_bank == 15
    assert new.past_events == (
        "independence_declaration", "developed_territory_i")


def test_independence_declaration_no_colony_no_pending() -> None:
    db = build_card_db()
    state = _state(
        players=(_strong("P0", 2), _strong("P1", 1)),
        current_events=("independence_declaration", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.pending == ()


# --- international_agreement ----------------------------------------------------------

_REFILL_DECK = (
    "kremlin", "coal", "eiffel_tower", "ocean_liner_service",
    "selective_breeding", "theology", "iron", "swordsmen",
    "monarchy", "theocracy", "printing_press", "knights",
)


def _agreement_state(p0: PlayerState, p1: PlayerState) -> GameState:
    row: list[str | None] = [None] * ROW_SLOTS
    row[0] = "iron"        # 1 白点
    row[5] = "theology"    # 2 白点
    return _state(
        players=(p0, p1),
        card_row=tuple(row),
        civil_deck=_REFILL_DECK,
        current_events=("international_agreement", "development_of_science"),
    )


def test_international_agreement_take_then_done_replenishes() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2, civil_actions=5)
    p1 = _strong("P1", 1)
    new = _reveal(db, _agreement_state(p0, p1))
    # 最强压入拿牌 pending(预算 5), 并标记跳过下一次政治行动
    assert len(new.pending) == 1
    assert new.pending[0].kind == events.KIND_EVENT_AGREEMENT
    assert new.pending[0].responder == 0
    assert new.pending[0].context["budget"] == 5
    assert new.players[0].miss_political_action
    legal = legal_actions(db, new)
    assert ChooseEventOption("0") in legal
    assert ChooseEventOption("5") in legal
    assert ChooseEventOption(events.AGREEMENT_DONE) in legal
    assert DeclineResponse() not in legal  # 以 "done" 选项结束, 非放弃白名单
    # 拿 0 号位 iron(1 白点): 入手牌, 预算剩 4, 重压 pending
    new = apply(new, ChooseEventOption("0"), db)
    assert new.players[0].hand_civil == ("iron",)
    assert new.players[0].civil_actions == 4
    assert new.card_row[0] is None
    assert len(new.pending) == 1
    assert new.pending[0].context["budget"] == 4
    # "done" 结束拿牌: 空槽从左到右以牌堆顶补满
    new = apply(new, ChooseEventOption(events.AGREEMENT_DONE), db)
    assert new.pending == ()
    assert new.card_row[0] == "kremlin"
    assert all(card_id is not None for card_id in new.card_row)
    assert len(new.civil_deck) == len(_REFILL_DECK) - 12


def test_international_agreement_budget_exhaustion_finalizes() -> None:
    db = build_card_db()
    # 白点 2: 拿 5 号位 theology(2 白点)后白点耗尽 -> 自动结束并补牌
    p0 = _strong("P0", 2, civil_actions=2)
    p1 = _strong("P1", 1)
    new = _reveal(db, _agreement_state(p0, p1))
    legal = legal_actions(db, new)
    assert ChooseEventOption("5") in legal
    new = apply(new, ChooseEventOption("5"), db)
    assert new.pending == ()
    assert new.players[0].hand_civil == ("theology",)
    assert new.players[0].civil_actions == 0
    assert all(card_id is not None for card_id in new.card_row)


def test_international_agreement_miss_next_political_action() -> None:
    db = build_card_db()
    p0 = _player("P0", miss_political_action=True)
    state = _state(players=(p0, _player("P1")))
    # 政治相位仅剩 SkipPolitics; 结算后清旗并转入行动相位
    assert legal_actions(db, state) == [SkipPolitics()]
    new = apply(state, SkipPolitics(), db)
    assert new.phase is Phase.ACTION
    assert not new.players[0].miss_political_action


# --- national_pride -------------------------------------------------------------------


def test_national_pride_most_culture_gains() -> None:
    db = build_card_db()
    state = _state(
        players=(_player("P0", culture=3), _player("P1", culture=8)),
        current_events=("national_pride", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].culture == 3
    assert new.players[1].culture == 13


def test_national_pride_tie_broken_clockwise() -> None:
    db = build_card_db()
    state = _state(
        players=(_player("P0", culture=5), _player("P1", culture=5)),
        current_player=1,
        current_events=("national_pride", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[1].culture == 10
    assert new.players[0].culture == 5


# --- politics_of_strength -----------------------------------------------------------

_MILITARY_DECK = ("raiders", "rats", "pestilence", "rebellion", "crusades")


def test_politics_of_strength_military_cards() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong(
        "P1", 1,
        hand_military=("barbarians", "crusades", "crusades", "foray"))
    state = _state(
        players=(p0, p1),
        military_deck=_MILITARY_DECK,
        current_events=("politics_of_strength", "development_of_science"),
    )
    new = _reveal(db, state)
    # 最强 +5 军事牌(牌堆顶依次抓)
    assert new.players[0].hand_military == _MILITARY_DECK
    assert new.military_deck == ()
    # 最弱 -3 军事牌(手牌按 card_id 字典序确定弃置)
    assert new.players[1].hand_military == ("foray",)
    assert new.military_discard == ("barbarians", "crusades", "crusades")


def test_politics_of_strength_final_age_culture_instead() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2, culture=4)
    p1 = _strong("P1", 1, culture=2, hand_military=("foray",))
    state = _state(
        players=(p0, p1),
        age=Age.III,
        military_deck=_MILITARY_DECK,
        current_events=("politics_of_strength", "development_of_science"),
    )
    new = _reveal(db, state)
    # 最终时代: ±文化代替(最强 +5, 最弱 -3 下限 0), 军事牌不动
    assert new.players[0].culture == 9
    assert new.players[1].culture == 0
    assert new.players[1].hand_military == ("foray",)
    assert new.military_deck == _MILITARY_DECK


# --- popularization_of_science ---------------------------------------------------------


def test_popularization_of_science_gains_culture_per_science_rate() -> None:
    db = build_card_db()
    # P1 两个实验室工人(科技增速 2); P0 科技增速 1
    p1 = _player("P1", developed=_INITIAL_DEVELOPED + ("philosophy",),
                 buildings={
                     "farm": {"agriculture": 2}, "mine": {"bronze": 2},
                     "lab": {"philosophy": 2}, "infantry": {"warriors": 1},
                 })
    state = _state(
        players=(_player("P0", culture=3), p1),
        current_events=("popularization_of_science", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].culture == 4   # 3 + 1
    assert new.players[1].culture == 2   # 0 + 2


# --- prosperity ------------------------------------------------------------------------


def test_prosperity_population_per_happy_face() -> None:
    db = build_card_db()
    # P0 1 宗教工人(1 笑脸) -> +1 人口; P1 0 笑脸 -> 无; P2 1 笑脸但银行空 -> 无
    p0 = _player("P0", buildings={
        "farm": {"agriculture": 2}, "mine": {"bronze": 2},
        "lab": {"philosophy": 1}, "infantry": {"warriors": 1},
        "temple": {"religion": 1},
    })
    p2 = _player("P2", yellow_bank=0, buildings={
        "farm": {"agriculture": 2}, "mine": {"bronze": 2},
        "lab": {"philosophy": 1}, "infantry": {"warriors": 1},
        "temple": {"religion": 1},
    })
    state = _state(
        num_players=3, players=(p0, _player("P1"), p2),
        current_events=("prosperity", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].worker_pool == 2
    assert new.players[0].yellow_bank == 17
    assert new.players[1].worker_pool == 1
    assert new.players[2].worker_pool == 1
    assert new.players[2].yellow_bank == 0


# --- ravages_of_time ---------------------------------------------------------------------


def test_ravages_of_time_flip_choice_and_effects_lost() -> None:
    db = build_card_db()
    # P0: pyramids(A, +1 白点)与 taj_mahal(I)可翻面; P1 仅 Age II 奇迹 -> 跳过
    p0 = _player("P0", wonders=("pyramids", "taj_mahal"))
    p1 = _player("P1", wonders=("transcontinental_railroad",))
    state = _state(
        players=(p0, p1),
        current_events=("ravages_of_time", "development_of_science"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [0]
    assert new.pending[0].kind == events.KIND_EVENT_RAVAGES
    legal = legal_actions(db, new)
    assert ChooseEventOption("pyramids") in legal
    assert ChooseEventOption("taj_mahal") in legal
    assert ChooseEventOption("transcontinental_railroad") not in legal
    assert DeclineResponse() not in legal  # 强制翻面, 不可放弃
    before = civ.civ_values(db, new.players[0])
    assert before.civil_actions == 5  # despotism 4 + pyramids 1
    new = apply(new, ChooseEventOption("pyramids"), db)
    assert new.pending == ()
    flipped = new.players[0]
    assert flipped.wonders == ("pyramids", "taj_mahal")  # 翻面奇迹留在场上
    assert flipped.wonders_facedown == ("pyramids",)
    after = civ.civ_values(db, flipped)
    # 效果失效(pyramids +1 白点失效), 转为 +2 文化增速
    assert after.civil_actions == 4
    assert after.culture_rate == before.culture_rate + 2


def test_ravages_of_time_no_eligible_wonder_no_pending() -> None:
    db = build_card_db()
    state = _state(
        players=(_player("P0"), _player("P1", wonders=("kremlin",))),
        current_events=("ravages_of_time", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.pending == ()


def test_ravages_of_time_facedown_serialization_roundtrip() -> None:
    p0 = _player("P0", wonders=("pyramids",), wonders_facedown=("pyramids",))
    state = _state(players=(p0, _player("P1")))
    assert from_dict(to_dict(state)) == state
    # 默认空时不落盘(旧格式逐字节兼容, 黄金指纹不变)
    assert "wonders_facedown" not in to_dict(_state())["players"][0]


# --- refugees ----------------------------------------------------------------------------


def test_refugees_weakest_loses_strongest_gains() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2, culture=5)
    p1 = _strong("P1", 1, culture=2)
    state = _state(
        players=(p0, p1),
        current_events=("refugees", "development_of_science"),
    )
    new = _reveal(db, state)
    # 最弱 -3 文化(下限 0)与 -1 人口; 最强 +3 文化与 +1 人口
    assert new.players[1].culture == 0
    assert new.players[1].worker_pool == 0
    assert new.players[1].yellow_bank == 19
    assert new.players[0].culture == 8
    assert new.players[0].worker_pool == 2
    assert new.players[0].yellow_bank == 17


# --- terrorism ----------------------------------------------------------------------------


def test_terrorism_others_destroy_urban_building() -> None:
    db = build_card_db()
    # 文化: P0=5, P1=1(最少), P2=3 -> P0 与 P2 各摧毁 1 城市建筑(各自选择)
    p0 = _player("P0", culture=5)
    p1 = _player("P1", culture=1)
    p2 = _player("P2", culture=3)
    state = _state(
        num_players=3, players=(p0, p1, p2),
        current_events=("terrorism", "development_of_science"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [0, 2]
    assert all(
        e.kind == events.KIND_EVENT_DESTROY_URBAN for e in new.pending)
    legal = legal_actions(db, new)
    assert ChooseEventOption("philosophy") in legal
    assert ChooseEventOption("agriculture") not in legal  # 农场不在其列
    assert ChooseEventOption("warriors") not in legal     # 兵种不在其列
    assert DeclineResponse() not in legal  # 强制失去, 不可放弃
    new = apply(new, ChooseEventOption("philosophy"), db)
    assert new.players[0].buildings.get("lab") == {}
    assert new.players[0].worker_pool == 2
    new = apply(new, ChooseEventOption("philosophy"), db)
    assert new.pending == ()
    assert new.players[2].buildings.get("lab") == {}
    # 文化最少者自身不受影响
    assert new.players[1].buildings["lab"] == {"philosophy": 1}
    assert new.players[1].worker_pool == 1


def test_terrorism_least_culture_tie_broken_clockwise() -> None:
    db = build_card_db()
    # 文化平局(各 1): 顺时针近者(current_player=1 -> P1)为文化最少者,
    # 仅 P0 摧毁 1 城市建筑
    p0 = _player("P0", culture=1)
    p1 = _player("P1", culture=1)
    state = _state(
        players=(p0, p1), current_player=1,
        current_events=("terrorism", "development_of_science"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [0]


# --- 时代 II 过场兜底移除 / fail-loud -------------------------------------------------


def test_unregistered_age_ii_event_fails_loud() -> None:
    # 时代 II 事件未注册 handler -> ValueError(T11 拥有时代 II 全量)
    db = _db_with_fake_event(Age.II)
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("fake_event_x", "development_of_science"),
    )
    with pytest.raises(ValueError, match="fake_event_x"):
        apply(state, SeedEvent("development_of_crafts"), db)


# --- 强制事件 pending 不提供 PassTurn 兜底 ----------------------------------------------


def test_no_pass_turn_dodge_for_mandatory_event_ii_pending() -> None:
    # 强制失去类 pending(ravages, responder=当前玩家)不提供 PassTurn 兜底
    db = build_card_db()
    p0 = _player("P0", wonders=("pyramids",))
    state = _state(
        players=(p0, _player("P1")),
        phase=Phase.ACTION,
        pending=(events.PendingEffect(
            events.KIND_EVENT_RAVAGES, 0, responder=0),),
    )
    legal = legal_actions(db, state)
    assert PassTurn() not in legal
    assert ChooseEventOption("pyramids") in legal
