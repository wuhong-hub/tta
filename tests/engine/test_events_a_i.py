"""时代 I 事件处理器测试(P2-T6).

覆盖 15 个时代 I 事件(文本以卡牌数值表 PDF 第 4 页 Events 表 Age I 行
为准; 强弱比较按 civ 军力, 平局按当前玩家顺时针近者优先, 规则书 p7;
2 人局"两个最X"理解为"一个最X"):

- barbarians: 文化领先者(文化分最多, PDF 竖琴图标)若为两个最弱文明之一,
  失去 1 人口(PDF 棋子图标; 优先空闲工人池, 黄点回银行);
- border_conflict: 最弱失去 1 城市建筑/农场/矿场(该玩家选择, 强制
  pending); 最强产 3 资源(按价值);
- crusades: 最强 +4 文化, 最弱 -4 文化(下限 0, 同 turn 食物短缺口径);
- cultural_influence / scientific_breakthrough: +文化/科技 = 各自增速;
- foray: 两个最强各产共 3 食物/资源(各自选组合, 可放弃);
- good_harvest / new_deposits: 农场/矿场立即生产(忽略消耗与腐败);
- immigration: 笑脸最多的所有文明(平局全部, 规则书 p7)免费 +1 人口;
- pestilence: 全场 -1 人口; raiders: 两个最弱各失去共 2 食物/资源
  (各自选组合, 强制 pending, 不足损失到此为止);
- rats: 清空农场卡上全部蓝点回供给区;
- rebellion: 下回合 -2 白点(当前玩家挂 civil_action_debt 于回合末行动点
  恢复时生效; 他玩家行动点已恢复完毕, 立即 -2);
- reign_of_terror: 最弱 -1 人口;
- uncertain_borders: 最弱从黄点银行给最强 1 黄点。
"""

from dataclasses import replace

import pytest

from tta.cards import build_card_db
from tta.engine import events, turn
from tta.engine.actions import (
    ChooseEventOption,
    DeclineResponse,
    PassTurn,
    SeedEvent,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType, Phase
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
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
        "age": Age.I,
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


# --- barbarians ---------------------------------------------------------------


def test_barbarians_culture_leader_weakest_loses_population() -> None:
    db = build_card_db()
    # P0 文化领先(5)且最弱(军力 0); P1 文化 3, 军力 1
    p0 = _strong("P0", 0, culture=5)
    p1 = _strong("P1", 1, culture=3)
    state = _state(
        players=(p0, p1),
        current_events=("barbarians", "development_of_science"),
    )
    new = _reveal(db, state)
    # 2 人局"两个最弱" = 一个最弱 = P0; 失去 1 人口: 空闲池 1->0, 回黄点银行
    assert new.players[0].worker_pool == 0
    assert new.players[0].yellow_bank == 19
    assert new.players[1].worker_pool == 1
    assert new.players[1].yellow_bank == 18


def test_barbarians_culture_leader_not_weakest_no_effect() -> None:
    db = build_card_db()
    # P0 文化领先且最强 -> 不失去人口
    p0 = _strong("P0", 2, culture=5)
    p1 = _strong("P1", 1, culture=3)
    state = _state(
        players=(p0, p1),
        current_events=("barbarians", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].worker_pool == 1
    assert new.players[0].yellow_bank == 18
    assert new.players[1].worker_pool == 1


def test_barbarians_culture_tie_broken_clockwise() -> None:
    db = build_card_db()
    # 文化平局(各 5): 顺时针近者(current_player=1 -> 1 号位)为文化领先者;
    # 1 号位军力 0 最弱 -> 失去 1 人口
    p0 = _strong("P0", 2, culture=5)
    p1 = _strong("P1", 0, culture=5)
    state = _state(
        players=(p0, p1), current_player=1,
        current_events=("barbarians", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[1].worker_pool == 0
    assert new.players[1].yellow_bank == 19
    assert new.players[0].worker_pool == 1


def test_barbarians_empty_pool_takes_from_building() -> None:
    db = build_card_db()
    # 文化领先且最弱者无空闲工人: 按 (类别, 卡 id) 字典序从卡上移除
    # (farm < infantry < lab < mine -> agriculture)
    p0 = _strong("P0", 0, culture=5, worker_pool=0)
    p1 = _strong("P1", 1, culture=3)
    state = _state(
        players=(p0, p1),
        current_events=("barbarians", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].buildings["farm"] == {"agriculture": 1}
    assert new.players[0].yellow_bank == 19


# --- border_conflict ----------------------------------------------------------


def test_border_conflict_destroy_choice_and_strongest_produces() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)  # 最强(当前玩家)
    p1 = _strong("P1", 1)  # 最弱
    state = _state(
        players=(p0, p1),
        current_events=("border_conflict", "development_of_science"),
    )
    new = _reveal(db, state)
    # 最强产 3 资源(按价值): bronze(值 1) +3 蓝点, 供给区 -3
    assert new.players[0].card_tokens.get("bronze") == 3
    assert new.players[0].blue_bank == 13
    # 最弱压入强制选择 pending(responder=1): 选项 = 有工人的农场/矿场/城市建筑
    assert len(new.pending) == 1
    assert new.pending[0].kind == events.KIND_EVENT_DESTROY_BUILDING
    assert new.pending[0].responder == 1
    legal = legal_actions(db, new)
    assert ChooseEventOption("agriculture") in legal
    assert ChooseEventOption("bronze") in legal
    assert ChooseEventOption("philosophy") in legal
    assert ChooseEventOption("warriors") not in legal  # 兵种不在其列
    assert ChooseEventOption("religion") not in legal  # 无工人
    assert DeclineResponse() not in legal  # 强制选择, 不可放弃
    # 选择失去 philosophy: 工人回空闲池(空槽类别保留空 dict, 引擎约定)
    new = apply(new, ChooseEventOption("philosophy"), db)
    assert new.pending == ()
    assert new.players[1].buildings.get("lab") == {}
    assert new.players[1].worker_pool == 2


def test_border_conflict_no_building_no_pending() -> None:
    db = build_card_db()
    p0 = _player("P0", buildings={"infantry": {"warriors": 2}})
    # 最弱无任何农场/矿场/城市建筑 -> 无 pending; 最强仍产 3 资源
    p1 = _player("P1", buildings={"infantry": {"warriors": 1}})
    state = _state(
        players=(p0, p1),
        current_events=("border_conflict", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.pending == ()
    assert new.players[0].card_tokens.get("bronze") == 3


def test_border_conflict_full_tie_same_civ() -> None:
    # 军力全平(2 人局): 顺时针近者同为最强与最弱(规则书 p7 平局口径)
    db = build_card_db()
    state = _state(current_events=(
        "border_conflict", "development_of_science"))
    new = _reveal(db, state)
    # P0 既产 3 资源又须失去 1 建筑
    assert new.players[0].card_tokens.get("bronze") == 3
    assert len(new.pending) == 1
    assert new.pending[0].responder == 0


# --- crusades -----------------------------------------------------------------


def test_crusades_strongest_gains_weakest_loses() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2, culture=1)
    p1 = _strong("P1", 1, culture=10)
    state = _state(
        players=(p0, p1),
        current_events=("crusades", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].culture == 5   # 最强 +4
    assert new.players[1].culture == 6   # 最弱 -4


def test_crusades_culture_floored_at_zero() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2, culture=0)
    p1 = _strong("P1", 1, culture=2)
    state = _state(
        players=(p0, p1),
        current_events=("crusades", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[1].culture == 0  # 2 - 4 下限 0


# --- cultural_influence / scientific_breakthrough ------------------------------


def test_cultural_influence_gains_culture_rate() -> None:
    db = build_card_db()
    # P1 多 1 宗教工人(文化增速 1); P0 文化增速 0
    p1 = _player("P1", buildings={
        **_INITIAL_BUILDINGS, "temple": {"religion": 1}})
    p1 = replace(p1, buildings={
        k: dict(v) for k, v in p1.buildings.items()})
    state = _state(
        players=(_player("P0", culture=3), p1),
        current_events=("cultural_influence", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].culture == 3
    assert new.players[1].culture == 1


def test_scientific_breakthrough_gains_science_rate() -> None:
    db = build_card_db()
    # P1 两个实验室工人(科技增速 2)
    p1 = _player("P1", developed=_INITIAL_DEVELOPED + ("philosophy",),
                 buildings={
                     "farm": {"agriculture": 2}, "mine": {"bronze": 2},
                     "lab": {"philosophy": 2}, "infantry": {"warriors": 1},
                 })
    state = _state(
        players=(_player("P0", science=5), p1),
        current_events=("scientific_breakthrough", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].science == 6   # 5 + 1
    assert new.players[1].science == 2   # 0 + 2


# --- foray --------------------------------------------------------------------


def test_foray_two_strongest_choose_mix_3p() -> None:
    db = build_card_db()
    # 军力: P0=1, P1=3, P2=2 -> 两个最强 = 1, 2(顺时针序)
    p0 = _strong("P0", 1)
    p1 = _strong("P1", 3)
    p2 = _strong("P2", 2)
    state = _state(
        num_players=3, players=(p0, p1, p2),
        current_events=("foray", "development_of_science"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [1, 2]
    assert all(e.kind == events.KIND_EVENT_FORAY for e in new.pending)
    legal = legal_actions(db, new)
    for option in events.FORAY_OPTIONS:
        assert ChooseEventOption(option) in legal
    assert DeclineResponse() in legal  # 增益类选择, 可放弃
    # 1 号位选 2 食物 + 1 资源(按价值, agriculture/bronze 值均 1)
    new = apply(new, ChooseEventOption("food:2,resource:1"), db)
    assert new.players[1].card_tokens.get("agriculture") == 2
    assert new.players[1].card_tokens.get("bronze") == 1
    # 2 号位放弃
    new = apply(new, DeclineResponse(), db)
    assert new.pending == ()
    assert new.players[2].card_tokens == {}


def test_foray_2p_only_one_strongest() -> None:
    # 2 人局"两个最强" = 一个最强(规则书 p7)
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong("P1", 1)
    state = _state(
        players=(p0, p1),
        current_events=("foray", "development_of_science"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [0]
    new = apply(new, ChooseEventOption("resource:3"), db)
    assert new.players[0].card_tokens.get("bronze") == 3
    assert new.players[0].blue_bank == 13


def test_foray_gain_by_value_not_token_count() -> None:
    # 产 3 资源按价值计: 仅有 iron(值 2)时放 1 蓝点(余 1 找不齐损失)
    db = build_card_db()
    p0 = _player("P0", developed=("iron", "warriors"),
                 buildings={"infantry": {"warriors": 2}}, worker_pool=1)
    p1 = _strong("P1", 1)
    state = _state(
        players=(p0, p1),
        current_events=("foray", "development_of_science"),
    )
    new = _reveal(db, state)
    new = apply(new, ChooseEventOption("resource:3"), db)
    assert new.players[0].card_tokens.get("iron") == 1
    assert new.players[0].blue_bank == 15


# --- good_harvest / new_deposits -----------------------------------------------


def test_good_harvest_farms_produce_ignoring_consumption_corruption() -> None:
    db = build_card_db()
    # 黄点银行低(消耗需求高)、蓝点银行高(腐败阈值): 事件生产均忽略
    p0 = _player("P0", yellow_bank=5, blue_bank=16)
    state = _state(
        players=(p0, _player("P1")),
        current_events=("good_harvest", "development_of_science"),
    )
    new = _reveal(db, state)
    for p in new.players:
        # 每张有工人的农场卡 +1 蓝点, 无消耗无腐败
        assert p.card_tokens.get("agriculture") == 1
    assert new.players[0].blue_bank == 15
    assert new.players[0].yellow_bank == 5
    assert new.players[1].card_tokens.get("bronze") is None


def test_new_deposits_mines_produce_ignoring_corruption() -> None:
    db = build_card_db()
    p0 = _player("P0", blue_bank=16)
    state = _state(
        players=(p0, _player("P1")),
        current_events=("new_deposits", "development_of_science"),
    )
    new = _reveal(db, state)
    for p in new.players:
        assert p.card_tokens.get("bronze") == 1
        assert p.card_tokens.get("agriculture") is None
    assert new.players[0].blue_bank == 15


# --- immigration ----------------------------------------------------------------


def test_immigration_tied_all_gain_population() -> None:
    # 笑脸平局(全 0): 所有平局文明都 +1 人口(规则书 p7 "所有...保持平局")
    db = build_card_db()
    state = _state(
        num_players=3,
        current_events=("immigration", "development_of_science"),
    )
    new = _reveal(db, state)
    for p in new.players:
        assert p.yellow_bank == 17
        assert p.worker_pool == 2


def test_immigration_most_happiness_only_and_bank_required() -> None:
    db = build_card_db()
    # P0 笑脸 1(宗教工人)领先; P1 笑脸 0; P2 笑脸 1 但黄点银行空 -> 跳过
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
        current_events=("immigration", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].worker_pool == 2
    assert new.players[0].yellow_bank == 17
    assert new.players[1].worker_pool == 1
    assert new.players[2].worker_pool == 1
    assert new.players[2].yellow_bank == 0


def test_immigration_skips_resigned_player() -> None:
    # 3 人局 P1 已退出且笑脸最高(建筑冻结保留): 不参与比较与生效,
    # 在局玩家(笑脸 0 平局)不受影响全部 +1 人口(规则书 p4: 退出者文明移出游戏)
    db = build_card_db()
    resigned = _player("P1", resigned=True, buildings={
        "farm": {"agriculture": 2}, "mine": {"bronze": 2},
        "lab": {"philosophy": 1}, "infantry": {"warriors": 1},
        "temple": {"religion": 1},
    })
    state = _state(
        num_players=3, players=(_player("P0"), resigned, _player("P2")),
        current_events=("immigration", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[0].worker_pool == 2
    assert new.players[0].yellow_bank == 17
    assert new.players[2].worker_pool == 2
    assert new.players[2].yellow_bank == 17
    # 退出者状态不变(不获人口, 也不阻断在局玩家)
    assert new.players[1] == resigned


# --- pestilence -----------------------------------------------------------------


def test_pestilence_each_loses_one_population() -> None:
    db = build_card_db()
    state = _state(
        num_players=3,
        current_events=("pestilence", "development_of_science"),
    )
    new = _reveal(db, state)
    for p in new.players:
        assert p.worker_pool == 0     # 空闲池 1 -> 0
        assert p.yellow_bank == 19    # 回黄点银行


# --- raiders -------------------------------------------------------------------


def test_raiders_weakest_chooses_loss_mix() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong("P1", 1, card_tokens={"agriculture": 1, "bronze": 2})
    state = _state(
        players=(p0, p1),
        current_events=("raiders", "development_of_science"),
    )
    new = _reveal(db, state)
    # 2 人局"两个最弱" = 一个最弱 = P1
    assert [e.responder for e in new.pending] == [1]
    assert new.pending[0].kind == events.KIND_EVENT_RAIDERS
    legal = legal_actions(db, new)
    for option in events.RAIDERS_OPTIONS:
        assert ChooseEventOption(option) in legal
    assert DeclineResponse() not in legal  # 强制失去, 不可放弃
    # 选 1 食物 + 1 资源
    new = apply(new, ChooseEventOption("food:1,resource:1"), db)
    assert new.pending == ()
    assert new.players[1].card_tokens == {"bronze": 1}
    assert new.players[1].blue_bank == 18  # 失去的蓝点回供给区


def test_raiders_loss_capped_by_holdings() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong("P1", 1, card_tokens={"agriculture": 1})  # 仅 1 食物
    state = _state(
        players=(p0, p1),
        current_events=("raiders", "development_of_science"),
    )
    new = _reveal(db, state)
    new = apply(new, ChooseEventOption("food:2"), db)
    # 不足部分损失到此为止(settle_loss 口径)
    assert new.players[1].card_tokens == {}
    assert new.players[1].blue_bank == 17


def test_raiders_empty_weakest_no_pending() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong("P1", 1)  # 无任何储存 -> 无效果, 不压 pending
    state = _state(
        players=(p0, p1),
        current_events=("raiders", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.pending == ()


# --- rats ------------------------------------------------------------------------


def test_rats_clears_all_farm_tokens_to_bank() -> None:
    db = build_card_db()
    p0 = _player("P0", card_tokens={"agriculture": 3, "bronze": 2}, blue_bank=11)
    state = _state(
        players=(p0, _player("P1")),
        current_events=("rats", "development_of_science"),
    )
    new = _reveal(db, state)
    # 农场卡上蓝点全清回供给区; 矿场不动
    assert new.players[0].card_tokens == {"bronze": 2}
    assert new.players[0].blue_bank == 14
    assert new.players[1].card_tokens == {}


# --- rebellion -------------------------------------------------------------------


def test_rebellion_current_debt_others_immediate() -> None:
    db = build_card_db()
    # P0 当前玩家(本回合白点已用 2, 余 2); P1 白点已恢复待下回合(4)
    p0 = _player("P0", civil_actions=2)
    p1 = _player("P1", civil_actions=4)
    state = _state(
        players=(p0, p1),
        current_events=("rebellion", "development_of_science"),
    )
    new = _reveal(db, state)
    # 当前玩家: 挂 debt(本回合不受影响, 下回合行动点恢复时 -2)
    assert new.players[0].civil_action_debt == 2
    assert new.players[0].civil_actions == 2
    # 他玩家: 下回合行动点已恢复完毕 -> 立即 -2
    assert new.players[1].civil_actions == 2
    assert new.players[1].civil_action_debt == 0


def test_rebellion_debt_applies_at_action_restore() -> None:
    db = build_card_db()
    p0 = _player("P0", civil_actions=2, civil_action_debt=2)
    state = _state(players=(p0, _player("P1", civil_actions=4)),
                   phase=Phase.ACTION)
    # 回合末行动点恢复: despotism 4 白点 - debt 2 = 2; debt 清零
    new = turn.end_of_turn(state, db)
    assert new.players[0].civil_actions == 2
    assert new.players[0].civil_action_debt == 0
    assert new.players[1].civil_actions == 4  # 未恢复(非其回合末), 不受影响


def test_rebellion_debt_serialization_roundtrip() -> None:
    p0 = _player("P0", civil_action_debt=2)
    state = _state(players=(p0, _player("P1")))
    assert from_dict(to_dict(state)) == state
    # debt 为 0 时不落盘(旧格式逐字节兼容, 黄金指纹不变)
    assert "civil_action_debt" not in to_dict(_state())["players"][0]


# --- reign_of_terror --------------------------------------------------------------


def test_reign_of_terror_weakest_loses_population() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2)
    p1 = _strong("P1", 1)
    state = _state(
        players=(p0, p1),
        current_events=("reign_of_terror", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[1].worker_pool == 0
    assert new.players[1].yellow_bank == 19
    assert new.players[0].worker_pool == 1


# --- uncertain_borders --------------------------------------------------------------


def test_uncertain_borders_yellow_transfer() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2, yellow_bank=18)
    p1 = _strong("P1", 1, yellow_bank=10)
    state = _state(
        players=(p0, p1),
        current_events=("uncertain_borders", "development_of_science"),
    )
    new = _reveal(db, state)
    # 最弱(P1)给最强(P0)1 黄点
    assert new.players[1].yellow_bank == 9
    assert new.players[0].yellow_bank == 19


def test_uncertain_borders_empty_bank_no_effect() -> None:
    db = build_card_db()
    p0 = _strong("P0", 2, yellow_bank=18)
    p1 = _strong("P1", 1, yellow_bank=0)
    state = _state(
        players=(p0, p1),
        current_events=("uncertain_borders", "development_of_science"),
    )
    new = _reveal(db, state)
    assert new.players[1].yellow_bank == 0
    assert new.players[0].yellow_bank == 18


# --- 时代 I 过场兜底移除 / fail-loud -------------------------------------------------


def test_unregistered_age_i_event_fails_loud() -> None:
    # 时代 I 事件未注册 handler -> ValueError(T6 拥有时代 I 全量)
    db = _db_with_fake_event(Age.I)
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("fake_event_x", "development_of_science"),
    )
    with pytest.raises(ValueError, match="fake_event_x"):
        apply(state, SeedEvent("development_of_crafts"), db)


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


def test_no_pass_turn_dodge_for_mandatory_event_pending() -> None:
    # 强制失去类 pending(raiders, responder=当前玩家)不提供 PassTurn 兜底
    db = build_card_db()
    p0 = _player("P0", card_tokens={"bronze": 2})
    state = _state(
        players=(p0, _player("P1")),
        phase=Phase.ACTION,
        pending=(PendingEffect(
            events.KIND_EVENT_RAIDERS, 0, responder=0),),
    )
    legal = legal_actions(db, state)
    assert PassTurn() not in legal
    assert ChooseEventOption("resource:2") in legal
