"""战争宣告与结算测试(P2-T9).

覆盖: DeclareWar 序列化与合法性(手牌 WAR 卡/目标非己/军事行动费/Gandhi
双倍费用/Gandhi 持有者禁宣/停战条约/最后游戏轮禁止/可挑战军力更强者)、
宣告结算(付红点, 战争牌手牌 -> declared_wars, phase -> ACTION)、次回合
回合开始结算时机(宣告当回合不结算; 补牌后/公开阵型前)、平局无效果、
三种战争效果(科技/领土/文化, 按军力差与转移上限)、夺取特殊科技(同名
不可夺/同类型留高弃低/可放弃)、declared_wars 序列化往返。

规则核对(规则书 p3-p4 + 卡牌数值表 v1.09 第 3 页 War 表):
- 战争在宣告者的下个回合开始阶段结算(补牌后、公开专属阵型前);
- 结算时比较双方纯军力等级, 双方都不可打出军事奖励牌;
- 平局无效果; 无论如何战争牌最终入军事弃牌堆;
- 三张战争牌的效果均以胜者的军力优势(军力差)计:
  war_over_technology_ii 败者 -科技 = 军力差, 胜者 +所失科技并可夺取
  对方 1 张特殊科技牌; war_over_territory_ii 败者 -黄点 = 1 + 军力差÷5
  (向下取整), 胜者获得等量(黄点银行转移, 不足则全给);
  war_over_culture_iii 败者 -文化 = 5 + 军力差, 胜者 +等量(按实失量);
- 战争与侵略不同: 规则书未禁止向军力更强者宣战。
"""

from dataclasses import replace

from tta.cards import build_card_db
from tta.engine import turn
from tta.engine.actions import (
    ChooseEventOption,
    DeclareWar,
    DeclineResponse,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, Phase
from tta.engine.legal import legal_actions
from tta.engine.state import ROW_SLOTS, GameState, PlayerState, from_dict, to_dict

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


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {
        "name": name,
        "developed": _INITIAL_DEVELOPED,
        "buildings": {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()},
    }
    base.update(overrides)
    return PlayerState(**base)


def _strong_buildings(warriors: int) -> dict[str, dict[str, int]]:
    """军力 = warriors 的建筑布局(每武士 1 军力)."""
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": warriors}
    return buildings


def _declarer(**overrides: object) -> PlayerState:
    """宣告方: 2 武士(军力 2) + 3 军事行动 + 手牌科技之战."""
    base: dict = {
        "buildings": _strong_buildings(2),
        "hand_military": ("war_over_technology_ii",),
        "military_actions": 3,
    }
    base.update(overrides)
    return _player("P0", **base)


def _state(*, age: Age = Age.II, **overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": age,
        "current_player": 0,
        "card_row": (None,) * ROW_SLOTS,
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (_declarer(), _player("P1")),
        "rng_state": 42,
        "phase": Phase.POLITICS,
    }
    base.update(overrides)
    return GameState(**base)


def _resolve_next_turn(state: GameState) -> GameState:
    """推进到宣告者的下个回合开始(战争在此时结算).

    时代 IV 无牌堆: 回合开始仅弃牌列(本测试牌列恒空), 隔离补牌/时代
    结束副作用; 军事牌堆/弃牌堆亦按时代 IV 口径为空。
    """
    state = replace(
        state, age=Age.IV, current_player=len(state.players) - 1,
        military_deck=(), future_military_decks={}, military_discard=())
    return turn.proceed(state, build_card_db())


# --- DeclareWar 序列化 ----------------------------------------------------------


def test_declare_war_serialization_roundtrip() -> None:
    action = DeclareWar("war_over_culture_iii", 1)
    assert action_from_dict(action_to_dict(action)) == action


def test_declared_wars_state_serialization_roundtrip() -> None:
    state = _state(players=(
        _declarer(declared_wars=(("war_over_technology_ii", 1),)),
        _player("P1"),
    ))
    assert from_dict(to_dict(state)) == state


# --- DeclareWar 合法性 -----------------------------------------------------------


def test_declare_war_enumerated_for_valid_target() -> None:
    db = build_card_db()
    assert DeclareWar("war_over_technology_ii", 1) in legal_actions(db, _state())


def test_declare_war_requires_war_card_in_hand() -> None:
    db = build_card_db()
    p0 = _declarer(hand_military=("fighting_band",))
    state = _state(players=(p0, _player("P1")))
    assert not any(isinstance(a, DeclareWar) for a in legal_actions(db, state))


def test_declare_war_target_self_excluded() -> None:
    db = build_card_db()
    assert DeclareWar("war_over_technology_ii", 0) not in legal_actions(
        db, _state())


def test_declare_war_requires_military_actions() -> None:
    # 科技之战费 2 红点: 仅 1 红点不可宣告, 2 红点可宣告
    db = build_card_db()
    p0 = _declarer(military_actions=1)
    state = _state(players=(p0, _player("P1")))
    assert DeclareWar("war_over_technology_ii", 1) not in legal_actions(db, state)
    p0 = _declarer(military_actions=2)
    state = _state(players=(p0, _player("P1")))
    assert DeclareWar("war_over_technology_ii", 1) in legal_actions(db, state)


def test_gandhi_doubles_war_cost() -> None:
    # 甘地被动: 针对其文明的战争花费双倍军事行动(费 2 -> 4)
    db = build_card_db()
    p1 = _player("P1", leader="mahatma_gandhi")
    p0 = _declarer(military_actions=3)
    state = _state(players=(p0, p1))
    assert DeclareWar("war_over_technology_ii", 1) not in legal_actions(db, state)
    p0 = _declarer(military_actions=4)
    state = _state(players=(p0, p1))
    assert DeclareWar("war_over_technology_ii", 1) in legal_actions(db, state)


def test_gandhi_owner_cannot_declare_war() -> None:
    # 甘地卡文本: 你不能打出侵略或战争牌
    db = build_card_db()
    p0 = _declarer(leader="mahatma_gandhi")
    state = _state(players=(p0, _player("P1")))
    assert not any(isinstance(a, DeclareWar) for a in legal_actions(db, state))


def test_peace_pact_blocks_war_declaration() -> None:
    # 停战类条约生效中不可互相攻击/宣战(T10 建模: 双方 pacts 同录)
    db = build_card_db()
    p0 = _declarer(pacts=("peace_treaty",))
    p1 = _player("P1", pacts=("peace_treaty",))
    state = _state(players=(p0, p1))
    assert not any(isinstance(a, DeclareWar) for a in legal_actions(db, state))


def test_declare_war_forbidden_in_last_round() -> None:
    # 规则书 p4: 你不能在最后的游戏轮宣告战争
    db = build_card_db()
    state = _state(last_round=True)
    assert not any(isinstance(a, DeclareWar) for a in legal_actions(db, state))


def test_declare_war_allows_stronger_target() -> None:
    # 与侵略不同: 规则书未禁止向军力更强者宣战
    db = build_card_db()
    p1 = _player("P1", buildings=_strong_buildings(5))  # 军力 5 > 宣告方 2
    state = _state(players=(_declarer(), p1))
    assert DeclareWar("war_over_technology_ii", 1) in legal_actions(db, state)


# --- 宣告结算 ---------------------------------------------------------------------


def test_declare_war_pays_and_moves_card_to_declared_wars() -> None:
    db = build_card_db()
    p0 = _declarer(hand_military=("war_over_technology_ii", "fighting_band"))
    state = _state(players=(p0, _player("P1")))
    new = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    assert new.players[0].military_actions == 1  # 付 2 红点
    assert new.players[0].hand_military == ("fighting_band",)
    assert new.players[0].declared_wars == (("war_over_technology_ii", 1),)
    # 战争牌在途, 尚未入军事弃牌堆; 每回合限 1 政治行动 -> phase ACTION
    assert "war_over_technology_ii" not in new.military_discard
    assert new.phase is Phase.ACTION


def test_war_not_resolved_on_declaration_turn() -> None:
    # 宣告当回合不结算: 双方科技/文化/黄点均不变
    db = build_card_db()
    p1 = _player("P1", science=5)
    state = _state(players=(_declarer(), p1))
    new = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    assert new.players[1].science == 5
    assert new.players[0].science == 0
    assert new.pending == ()


# --- 结算时机与平局 -----------------------------------------------------------------


def test_war_resolved_at_declarer_next_turn_start() -> None:
    # 次回合回合开始阶段(补牌后、公开阵型前)结算; 战争牌入军事弃牌堆
    p1 = _player("P1", science=5)
    state = _state(players=(_declarer(), p1))
    db = build_card_db()
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    new = _resolve_next_turn(state)
    assert new.players[0].declared_wars == ()
    assert "war_over_technology_ii" in new.military_discard
    # 军力 2 vs 1, 差 1: 败者 -1 科技, 胜者 +1(无特殊科技可夺取, 无 pending)
    assert new.players[1].science == 4
    assert new.players[0].science == 1
    assert new.current_player == 0
    assert new.phase is Phase.POLITICS


def test_war_tie_no_effect() -> None:
    # 双方军力相等 -> 战争结算不产生任何效果, 战争牌仍入军事弃牌堆
    p1 = _player("P1", buildings=_strong_buildings(2), science=5, culture=5)
    state = _state(players=(_declarer(), p1))
    db = build_card_db()
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    new = _resolve_next_turn(state)
    assert new.players[1].science == 5
    assert new.players[0].science == 0
    assert new.players[1].culture == 5
    assert new.players[0].declared_wars == ()
    assert "war_over_technology_ii" in new.military_discard
    assert new.pending == ()


# --- 科技之战(war_over_technology_ii) ----------------------------------------------


def _tech_war_state(**p1_overrides: object) -> GameState:
    """宣告并完成科技之战后的状态(军力 2 vs 1, 差 1)."""
    p1 = _player("P1", **p1_overrides)
    state = _state(players=(_declarer(), p1))
    db = build_card_db()
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    return _resolve_next_turn(state)


def test_war_over_technology_science_transfer_capped() -> None:
    # 败者失去科技 = 军力差(下限 0), 胜者获得实失量
    new = _tech_war_state(science=0)
    assert new.players[1].science == 0
    assert new.players[0].science == 0


def test_war_over_technology_seize_special_tech() -> None:
    # 胜者可夺取对方 1 张特殊科技牌(pending responder=胜者, 可放弃)
    db = build_card_db()
    p1_developed = _INITIAL_DEVELOPED + ("code_of_laws",)
    new = _tech_war_state(developed=p1_developed, science=5)
    assert len(new.pending) == 1
    pending = new.pending[0]
    assert pending.kind == "war_seize_tech"
    assert pending.responder == 0
    legal = legal_actions(db, new)
    assert ChooseEventOption("code_of_laws") in legal
    assert DeclineResponse() in legal
    # 夺取: 败者失去, 胜者获得(免费, 不触发研发即时收益)
    settled = apply(new, ChooseEventOption("code_of_laws"), db)
    assert "code_of_laws" not in settled.players[1].developed
    assert "code_of_laws" in settled.players[0].developed
    assert settled.pending == ()


def test_war_over_technology_seize_declinable() -> None:
    # 夺取为可选: DeclineResponse 放弃, 特殊科技留在败方
    db = build_card_db()
    p1_developed = _INITIAL_DEVELOPED + ("code_of_laws",)
    new = _tech_war_state(developed=p1_developed, science=5)
    settled = apply(new, DeclineResponse(), db)
    assert settled.pending == ()
    assert "code_of_laws" in settled.players[1].developed
    assert "code_of_laws" not in settled.players[0].developed


def test_war_over_technology_seize_same_name_blocked() -> None:
    # 胜利者不能夺取与自己游戏区域或手牌中同名的特殊科技牌
    p0 = _declarer(developed=_INITIAL_DEVELOPED + ("code_of_laws",))
    p1 = _player(
        "P1", developed=_INITIAL_DEVELOPED + ("code_of_laws",), science=5)
    state = _state(players=(p0, p1))
    db = build_card_db()
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    new = _resolve_next_turn(state)
    # 科技照转, 但无可夺取 -> 无 pending
    assert new.players[1].science == 4
    assert new.pending == ()
    assert "code_of_laws" in new.players[1].developed


def test_war_over_technology_seize_same_name_in_hand_blocked() -> None:
    # 胜者手牌中的同名特殊科技亦不可夺取
    p0 = _declarer(hand_civil=("code_of_laws",))
    p1 = _player(
        "P1", developed=_INITIAL_DEVELOPED + ("code_of_laws",), science=5)
    state = _state(players=(p0, p1))
    db = build_card_db()
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    new = _resolve_next_turn(state)
    assert new.pending == ()
    assert "code_of_laws" in new.players[1].developed


def test_war_seize_same_type_keeps_higher_discards_lower() -> None:
    # 夺取同类型特殊科技: 保留等级较高者, 弃置另一张(胜者 warfare I 级,
    # 夺取 strategy II 级 -> 保留 strategy, warfare 入弃牌堆)。
    # 军力口径: 宣告方 2 武士 + warfare(+1) = 3; 目标 1 武士 + strategy(+3)
    # = 4 -> 宣告方败, 目标胜; 此处反转为目标宣告... 改用目标为败方布局:
    # 宣告方 4 武士 + warfare = 5; 目标 1 武士 + strategy = 4, 差 1。
    db = build_card_db()
    p0 = _declarer(
        developed=_INITIAL_DEVELOPED + ("warfare",),
        buildings=_strong_buildings(4),
    )
    p1 = _player(
        "P1", developed=_INITIAL_DEVELOPED + ("strategy",), science=5)
    state = _state(players=(p0, p1))
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    new = _resolve_next_turn(state)
    assert new.pending[0].kind == "war_seize_tech"
    settled = apply(new, ChooseEventOption("strategy"), db)
    assert "strategy" in settled.players[0].developed
    assert "warfare" not in settled.players[0].developed
    assert "warfare" in settled.discard
    assert "strategy" not in settled.players[1].developed


def test_war_seize_stolen_lower_level_discarded() -> None:
    # 反向: 胜者已有高等级同类型(strategy II), 夺取低等级(warfare I)
    # -> 保留 strategy, 夺取来的 warfare 直接入弃牌堆。
    db = build_card_db()
    p0 = _declarer(
        developed=_INITIAL_DEVELOPED + ("strategy",),
        buildings=_strong_buildings(1),  # 1 武士 + strategy(+3) = 4
    )
    p1 = _player(
        "P1", developed=_INITIAL_DEVELOPED + ("warfare",),
        buildings=_strong_buildings(1),  # 1 武士 + warfare(+1) = 2, 差 2
        science=5,
    )
    state = _state(players=(p0, p1))
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    new = _resolve_next_turn(state)
    # 军力差 2: 败者 -2 科技
    assert new.players[1].science == 3
    assert new.players[0].science == 2
    settled = apply(new, ChooseEventOption("warfare"), db)
    assert "strategy" in settled.players[0].developed
    assert "warfare" not in settled.players[0].developed
    assert "warfare" in settled.discard
    assert "warfare" not in settled.players[1].developed


# --- 领土之战(war_over_territory_ii) ----------------------------------------------


def _territory_war(p0_warriors: int, p1_warriors: int,
                   **p1_overrides: object) -> GameState:
    """宣告并完成领土之战后的状态(军力 = 武士数)."""
    p0 = _declarer(
        hand_military=("war_over_territory_ii",),
        buildings=_strong_buildings(p0_warriors),
    )
    p1 = _player("P1", buildings=_strong_buildings(p1_warriors),
                 **p1_overrides)
    state = _state(players=(p0, p1))
    db = build_card_db()
    state = apply(state, DeclareWar("war_over_territory_ii", 1), db)
    return _resolve_next_turn(state)


def test_war_over_territory_yellow_transfer() -> None:
    # 军力 6 vs 1, 差 5: 败者 -黄点 = 1 + 5÷5 = 2, 胜者 +2(银行转移)
    new = _territory_war(6, 1)
    assert new.players[1].yellow_bank == 16
    assert new.players[0].yellow_bank == 20


def test_war_over_territory_fraction_rounded_down() -> None:
    # 军力 3 vs 1, 差 2: 1 + 2÷5(向下取整 0) = 1 黄点
    new = _territory_war(3, 1)
    assert new.players[1].yellow_bank == 17
    assert new.players[0].yellow_bank == 19


def test_war_over_territory_capped_by_loser_bank() -> None:
    # 败者黄点银行不足则全给(军力 6 vs 1 应转 2, 银行仅 1 -> 转 1)
    new = _territory_war(6, 1, yellow_bank=1)
    assert new.players[1].yellow_bank == 0
    assert new.players[0].yellow_bank == 19


# --- 文化之战(war_over_culture_iii) -------------------------------------------------


def test_war_over_culture_transfer() -> None:
    # 费 3 红点; 军力 2 vs 1, 差 1: 败者 -文化 = 5 + 1 = 6, 胜者 +6
    db = build_card_db()
    p0 = _declarer(
        hand_military=("war_over_culture_iii",), military_actions=3)
    p1 = _player("P1", culture=10)
    state = _state(players=(p0, p1))
    state = apply(state, DeclareWar("war_over_culture_iii", 1), db)
    assert state.players[0].military_actions == 0  # 费 3
    new = _resolve_next_turn(state)
    assert new.players[1].culture == 4
    assert new.players[0].culture == 6


def test_war_over_culture_capped_by_loser_culture() -> None:
    # 败者文化不足则全给(应失 6, 仅有 4 -> 胜者 +4)
    db = build_card_db()
    p0 = _declarer(hand_military=("war_over_culture_iii",))
    p1 = _player("P1", culture=4)
    state = _state(players=(p0, p1))
    state = apply(state, DeclareWar("war_over_culture_iii", 1), db)
    new = _resolve_next_turn(state)
    assert new.players[1].culture == 0
    assert new.players[0].culture == 4


# --- 防御方获胜与多场战争 -------------------------------------------------------------


def test_defender_can_win_war() -> None:
    # 结算时目标军力更高 -> 目标为胜者, 宣告方为败者(差 1: 宣告方 -6 文化)
    db = build_card_db()
    p0 = _declarer(hand_military=("war_over_culture_iii",), culture=10)
    p1 = _player("P1", buildings=_strong_buildings(3), culture=3)
    state = _state(players=(p0, p1))
    state = apply(state, DeclareWar("war_over_culture_iii", 1), db)
    new = _resolve_next_turn(state)
    assert new.players[0].culture == 4
    assert new.players[1].culture == 9
    assert "war_over_culture_iii" in new.military_discard


def test_multiple_declared_wars_resolve_in_order() -> None:
    # 对同一目标宣告两场战争: 逐张结算, 均入军事弃牌堆
    db = build_card_db()
    p0 = _declarer(
        hand_military=("war_over_technology_ii", "war_over_culture_iii"),
        military_actions=5,
        declared_wars=(("war_over_culture_iii", 1),),
    )
    p1 = _player("P1", science=5, culture=10)
    state = _state(players=(p0, p1))
    state = apply(state, DeclareWar("war_over_technology_ii", 1), db)
    assert state.players[0].declared_wars == (
        ("war_over_culture_iii", 1), ("war_over_technology_ii", 1))
    new = _resolve_next_turn(state)
    # 文化之战先结算(差 1: -6 文化), 科技之战后结算(-1 科技)
    assert new.players[1].culture == 4
    assert new.players[0].culture == 6
    assert new.players[1].science == 4
    assert new.players[0].science == 1
    assert new.players[0].declared_wars == ()
    assert set(new.military_discard) == {
        "war_over_technology_ii", "war_over_culture_iii"}
