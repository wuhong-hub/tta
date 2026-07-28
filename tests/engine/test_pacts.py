"""条约、体面退出与 Julius Caesar 双政治测试(P2-T10).

覆盖: ProposePact/PactAccept/PactReject/CancelPact/Resign 序列化、pacts
新形状 (卡 id, 侧) 序列化往返与旧格式兼容、2 人局不生成条约动作、提议
(压 pact_offer pending)/拒绝(牌回手, 本回合不能再政治行动)/接受(双方
pacts 追加, 静态效果生效)、旧条约互斥(双方既有条约失效入 removed)、停战
阻断侵略、开放边境攻击 +2 军力、攻击终止类条约(军事同盟/军事保护承诺)、
主权丧失 B 侧战争豁免、取缔条约、体面退出(文明移除/轮换跳过/只剩 1 人
判胜/对其宣战者战争牌移除 +7 文化/相关条约移除/时代 IV 不可退出)、
Caesar 一次性双政治。

规则核对(规则书 p4 提出条约/取缔条约/体面退出 + 卡牌数值表 v1.09 p3 条约表):
- 提出条约为政治行动: 展示条约牌 -> 宣告目标 -> 宣告自己扮演 A 或 B ->
  对方决定接受/拒绝; 拒绝则牌拿回手且本回合不能再执行政治行动;
- 接受: 双方游戏区域已有条约牌立即失效(从游戏中移除), 新条约立即生效;
- 取缔条约: 将你为当事人的一项条约从游戏中移除(政治行动);
- 体面退出(时代 IV 不允许): 手牌弃置, 游戏区域卡牌入 removed, 其他玩家
  游戏区域中与你有关的条约移除; 对其宣战者将战争牌从游戏中移除并 +7 文化;
  只剩 1 人 -> 游戏立即结束该玩家获胜(直接判胜, 不比文化);
- 条约静态效果按卡牌数值表 p3 A/B 列(见 civ.PACT_STATIC_BONUSES)。
"""

from collections import Counter
from dataclasses import replace

from tta.cards import build_card_db
from tta.engine import effects, turn
from tta.engine.actions import (
    Build,
    CancelPact,
    DeclareWar,
    DevelopTech,
    IncreasePopulation,
    PactAccept,
    PactReject,
    PassTurn,
    PlayAggression,
    ProposePact,
    Resign,
    SkipPolitics,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.civ import civ_values
from tta.engine.enums import Age, Phase
from tta.engine.legal import legal_actions
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
    from_dict,
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


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {
        "name": name,
        "developed": _INITIAL_DEVELOPED,
        "buildings": {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()},
    }
    base.update(overrides)
    return PlayerState(**base)


def _state(*, age: Age = Age.II, players: tuple[PlayerState, ...] | None = None,
           **overrides: object) -> GameState:
    if players is None:
        players = (_player("P0"), _player("P1"), _player("P2"))
    base: dict = {
        "round": 2,
        "age": age,
        "current_player": 0,
        "card_row": (None,) * ROW_SLOTS,
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": players,
        "rng_state": 42,
        "phase": Phase.POLITICS,
    }
    base.update(overrides)
    return GameState(**base)


def _offer_state(**overrides: object) -> GameState:
    """P0 提出 peace_treaty(侧 A)后的状态(pact_offer pending, responder=1)."""
    p0 = _player("P0", hand_military=("peace_treaty",), **overrides)
    state = _state(players=(p0, _player("P1"), _player("P2")))
    return apply(state, ProposePact("peace_treaty", 1, "A"), build_card_db())


# --- 序列化 ---------------------------------------------------------------------


def test_propose_pact_serialization_roundtrip() -> None:
    action = ProposePact("peace_treaty", 2, "B")
    assert action_from_dict(action_to_dict(action)) == action


def test_pact_accept_reject_serialization_roundtrip() -> None:
    assert action_from_dict(action_to_dict(PactAccept())) == PactAccept()
    assert action_from_dict(action_to_dict(PactReject())) == PactReject()


def test_cancel_pact_resign_serialization_roundtrip() -> None:
    assert action_from_dict(
        action_to_dict(CancelPact("peace_treaty"))) == CancelPact("peace_treaty")
    assert action_from_dict(action_to_dict(Resign())) == Resign()


def test_pacts_side_shape_serialization_roundtrip() -> None:
    p = _player("P0", pacts=(("peace_treaty", "A"),), resigned=True)
    state = _state(players=(p, _player("P1"), _player("P2")))
    assert from_dict(to_dict(state)) == state


def test_pacts_old_string_format_backward_compatible() -> None:
    # 旧格式 pacts 为纯卡 id 字符串列表(T8/T9 停战建模), 读入落侧 "A"
    p = _player("P0", pacts=(("peace_treaty", "A"),))
    state = _state(players=(p, _player("P1"), _player("P2")))
    data = to_dict(state)
    data["players"][0]["pacts"] = ["peace_treaty"]
    assert from_dict(data) == state


def test_resigned_defaults_false_in_old_format() -> None:
    state = _state()
    data = to_dict(state)
    for player in data["players"]:
        assert "resigned" not in player  # 缺省不落盘(旧格式逐字节兼容)
    assert from_dict(data) == state


# --- ProposePact 合法性 -----------------------------------------------------------


def test_propose_not_offered_in_2p() -> None:
    # 规则书 p4: 提出一项条约(2 人游戏时不允许)
    db = build_card_db()
    p0 = _player("P0", hand_military=("peace_treaty",))
    state = _state(players=(p0, _player("P1")))
    assert not any(isinstance(a, ProposePact) for a in legal_actions(db, state))


def test_propose_enumerated_for_each_target_and_side() -> None:
    # 对称条约(peace_treaty)仅举侧 A; 非对称(acceptance_of_supremacy)举 A/B
    db = build_card_db()
    p0 = _player(
        "P0", hand_military=("peace_treaty", "acceptance_of_supremacy"))
    state = _state(players=(p0, _player("P1"), _player("P2")))
    legal = legal_actions(db, state)
    assert ProposePact("peace_treaty", 1, "A") in legal
    assert ProposePact("peace_treaty", 2, "A") in legal
    assert ProposePact("peace_treaty", 1, "B") not in legal
    assert ProposePact("acceptance_of_supremacy", 1, "A") in legal
    assert ProposePact("acceptance_of_supremacy", 1, "B") in legal
    assert ProposePact("acceptance_of_supremacy", 2, "B") in legal
    assert ProposePact("peace_treaty", 0, "A") not in legal  # 目标非己


def test_propose_requires_pact_card_in_hand() -> None:
    db = build_card_db()
    p0 = _player("P0", hand_military=("fighting_band",))
    state = _state(players=(p0, _player("P1"), _player("P2")))
    assert not any(isinstance(a, ProposePact) for a in legal_actions(db, state))


# --- 提议/拒绝/接受结算 ------------------------------------------------------------


def test_propose_pushes_offer_pending() -> None:
    state = _offer_state()
    assert state.players[0].hand_military == ()  # 展示条约牌(离手)
    assert state.phase is Phase.POLITICS  # 响应期间保持政治相位
    assert len(state.pending) == 1
    pending = state.pending[0]
    assert pending.kind == "pact_offer"
    assert pending.responder == 1
    assert pending.context == {
        "card": "peace_treaty", "proposer": 0, "side": "A"}
    # 响应方动作: 接受/拒绝
    legal = legal_actions(build_card_db(), state)
    assert PactAccept() in legal
    assert PactReject() in legal


def test_pact_reject_returns_card_and_ends_politics() -> None:
    db = build_card_db()
    state = apply(_offer_state(), PactReject(), db)
    # 条约牌拿回提出者手牌; 本回合提出者不能再执行政治行动(转 ACTION)
    assert state.players[0].hand_military == ("peace_treaty",)
    assert state.pending == ()
    assert state.phase is Phase.ACTION
    assert not any(
        isinstance(a, (ProposePact, CancelPact, Resign))
        for a in legal_actions(db, state))


def test_pact_accept_appends_both_sides() -> None:
    db = build_card_db()
    state = apply(_offer_state(), PactAccept(), db)
    assert state.players[0].pacts == (("peace_treaty", "A"),)
    assert state.players[1].pacts == (("peace_treaty", "B"),)
    assert state.pending == ()
    assert state.phase is Phase.ACTION  # 每回合限 1 政治行动


def test_pact_accept_asymmetric_sides() -> None:
    # 提出者宣告自己扮演 B -> 对方为 A
    db = build_card_db()
    p0 = _player("P0", hand_military=("acceptance_of_supremacy",))
    state = _state(players=(p0, _player("P1"), _player("P2")))
    state = apply(state, ProposePact("acceptance_of_supremacy", 1, "B"), db)
    state = apply(state, PactAccept(), db)
    assert state.players[0].pacts == (("acceptance_of_supremacy", "B"),)
    assert state.players[1].pacts == (("acceptance_of_supremacy", "A"),)


def test_pact_accept_expires_existing_pacts() -> None:
    # 规则书 p4: 任一当事人游戏区域中已有条约牌 -> 旧条约立即失效移除
    db = build_card_db()
    p0 = _player(
        "P0", hand_military=("military_alliance",),
        pacts=(("peace_treaty", "A"),))
    p1 = _player("P1", pacts=(("peace_treaty", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    state = apply(state, ProposePact("military_alliance", 1, "A"), db)
    state = apply(state, PactAccept(), db)
    assert state.players[0].pacts == (("military_alliance", "A"),)
    assert state.players[1].pacts == (("military_alliance", "B"),)
    assert "peace_treaty" in state.removed


# --- 条约静态效果(civ 合成) --------------------------------------------------------


def _rates(db, state, seat):
    """含条约合成的文明数值(players/index 口径)."""
    return civ_values(db, state.players[seat], state.players, seat)


def test_peace_treaty_static_happiness() -> None:
    db = build_card_db()
    state = apply(_offer_state(), PactAccept(), db)
    base = civ_values(db, state.players[0]).happiness
    assert _rates(db, state, 0).happiness == base + 1
    assert _rates(db, state, 1).happiness == base + 1


def test_military_alliance_static_strength() -> None:
    db = build_card_db()
    p0 = _player("P0", hand_military=("military_alliance",))
    state = _state(players=(p0, _player("P1"), _player("P2")))
    state = apply(state, ProposePact("military_alliance", 1, "A"), db)
    state = apply(state, PactAccept(), db)
    base = civ_values(db, state.players[0]).strength
    assert _rates(db, state, 0).strength == base + 3
    assert _rates(db, state, 1).strength == base + 3


def test_acceptance_of_supremacy_culture_rates() -> None:
    db = build_card_db()
    p0 = _player("P0", hand_military=("acceptance_of_supremacy",))
    state = _state(players=(p0, _player("P1"), _player("P2")))
    state = apply(state, ProposePact("acceptance_of_supremacy", 1, "A"), db)
    state = apply(state, PactAccept(), db)
    # A +1 文化增速; B -1(下限 0, 本例基础增速 1 -> 0)
    base_a = civ_values(db, state.players[0]).culture_rate
    base_b = civ_values(db, state.players[1]).culture_rate
    assert _rates(db, state, 0).culture_rate == base_a + 1
    assert _rates(db, state, 1).culture_rate == max(0, base_b - 1)


def test_international_tourism_culture_per_partner_wonder() -> None:
    db = build_card_db()
    p0 = _player("P0", wonders=("pyramids", "colossus"))
    p1 = _player("P1", pacts=(("international_tourism", "B"),))
    p0 = replace(p0, pacts=(("international_tourism", "A"),))
    state = _state(players=(p0, p1, _player("P2")))
    # 对方 2 个已完成奇迹 -> +2 文化增速
    base = civ_values(db, state.players[1]).culture_rate
    assert _rates(db, state, 1).culture_rate == base + 2


def test_trade_agreement_side_b_science_rate() -> None:
    db = build_card_db()
    p0 = _player("P0", pacts=(("international_trade_agreement", "A"),))
    p1 = _player("P1", pacts=(("international_trade_agreement", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    base = civ_values(db, state.players[1]).science_rate
    assert _rates(db, state, 1).science_rate == base + 1


def test_trade_agreement_side_a_resource_production() -> None:
    # A 侧每回合 +1 资源生产(回合末生产阶段, 矿场卡上 +1 蓝点)
    db = build_card_db()
    p0 = _player("P0", pacts=(("international_trade_agreement", "A"),))
    p1 = _player("P1", pacts=(("international_trade_agreement", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    new = turn.end_of_turn(state, db)
    # 矿场卡产 1 蓝点 + 条约 +1 = bronze 卡上 2 蓝点
    assert new.players[0].card_tokens.get("bronze", 0) == 2
    # B 侧无资源生产加成: 仅矿场卡产 1
    p1_state = replace(new, current_player=1)
    p1_new = turn.end_of_turn(p1_state, db)
    assert p1_new.players[1].card_tokens.get("bronze", 0) == 1


# --- 条约与攻击的互动 ---------------------------------------------------------------


def _aggressor(**overrides: object) -> PlayerState:
    base: dict = {
        "buildings": {
            "farm": {"agriculture": 2}, "mine": {"bronze": 2},
            "lab": {"philosophy": 1}, "infantry": {"warriors": 3},
        },
        "hand_military": ("raid_i",),
        "military_actions": 2,
    }
    base.update(overrides)
    return _player("P0", **base)


def _weak_target(**overrides: object) -> PlayerState:
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {}
    base: dict = {"buildings": buildings}
    base.update(overrides)
    return _player("P1", **base)


def test_pact_blocks_aggression_between_holders() -> None:
    # 停战类条约(双方 pacts 同录)生效中不可互相攻击
    db = build_card_db()
    p0 = _aggressor(pacts=(("acceptance_of_supremacy", "A"),))
    p1 = _weak_target(pacts=(("acceptance_of_supremacy", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    assert not any(
        isinstance(a, PlayAggression) and a.target == 1
        for a in legal_actions(db, state))


def test_open_borders_attack_strength_bonus() -> None:
    # 开放边境: 若一方攻击另一方, 攻击者 +2 军力(攻击快照口径)
    db = build_card_db()
    p0 = _aggressor(pacts=(("open_borders_agreement", "A"),))
    p1 = _weak_target(pacts=(("open_borders_agreement", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    new = apply(state, PlayAggression("raid_i", 1), db)
    # 3 武士 = 3 军力 + 开放边境 +2 = 5
    assert new.pending[0].context["attack_strength"] == 5


def test_military_alliance_ends_on_attack() -> None:
    # 军事同盟: 若一方攻击另一方, 条约终止(从游戏中移除); 攻击不携带同盟加成
    db = build_card_db()
    p0 = _aggressor(pacts=(("military_alliance", "A"),))
    p1 = _weak_target(pacts=(("military_alliance", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    new = apply(state, PlayAggression("raid_i", 1), db)
    assert new.players[0].pacts == ()
    assert new.players[1].pacts == ()
    assert "military_alliance" in new.removed
    # 条约先终止再快照: 3 武士 = 3(不含同盟 +3)
    assert new.pending[0].context["attack_strength"] == 3


def test_loss_of_sovereignty_war_immunity_for_side_b() -> None:
    # 主权丧失: 无人能对 B 侧宣战(第三方也不可); A/B 之间本已互不攻击
    db = build_card_db()
    p0 = _player(
        "P0", hand_military=("war_over_technology_ii",), military_actions=3)
    p1 = _player("P1", pacts=(("loss_of_sovereignty", "B"),))
    p2 = _player("P2", pacts=(("loss_of_sovereignty", "A"),))
    state = _state(players=(p0, p1, p2))
    legal = legal_actions(db, state)
    assert DeclareWar("war_over_technology_ii", 1) not in legal
    assert DeclareWar("war_over_technology_ii", 2) in legal


# --- CancelPact -------------------------------------------------------------------


def test_cancel_pact_enumerated_and_settles() -> None:
    db = build_card_db()
    p0 = _player("P0", pacts=(("peace_treaty", "A"),))
    p1 = _player("P1", pacts=(("peace_treaty", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    assert CancelPact("peace_treaty") in legal_actions(db, state)
    new = apply(state, CancelPact("peace_treaty"), db)
    assert new.players[0].pacts == ()
    assert new.players[1].pacts == ()
    assert "peace_treaty" in new.removed  # 从游戏中移除
    assert new.phase is Phase.ACTION


def test_cancel_pact_not_offered_in_2p() -> None:
    # 规则书 p4: 取缔一项条约(2 人游戏时不允许)
    db = build_card_db()
    p0 = _player("P0", pacts=(("peace_treaty", "A"),))
    p1 = _player("P1", pacts=(("peace_treaty", "B"),))
    state = _state(players=(p0, p1))
    assert not any(isinstance(a, CancelPact) for a in legal_actions(db, state))


def test_cancel_pact_not_offered_without_pact() -> None:
    db = build_card_db()
    assert not any(isinstance(a, CancelPact) for a in legal_actions(db, _state()))


# --- Resign ----------------------------------------------------------------------


def test_resign_enumerated_outside_age_four() -> None:
    db = build_card_db()
    assert Resign() in legal_actions(db, _state())
    state_iv = _state(age=Age.IV)
    assert not any(isinstance(a, Resign) for a in legal_actions(db, state_iv))


def test_resign_removes_civilization() -> None:
    # 手牌弃置; 游戏区域卡牌(developed/领袖/奇迹/殖民地/在途战争)入 removed
    db = build_card_db()
    p0 = _player(
        "P0",
        hand_civil=("code_of_laws",), hand_military=("fighting_band",),
        leader="hammurabi", wonders=("pyramids",),
        wonder_progress=("colossus", 1), colonies=("vast_territory_i",),
        declared_wars=(("war_over_culture_iii", 1),),
    )
    state = _state(players=(p0, _player("P1"), _player("P2")))
    new = apply(state, Resign(), db)
    p = new.players[0]
    assert p.resigned
    assert p.hand_civil == () and p.hand_military == ()
    assert p.developed == () and p.leader is None
    assert p.wonders == () and p.wonder_progress is None
    assert p.colonies == () and p.declared_wars == ()
    assert "code_of_laws" in new.discard
    assert "fighting_band" in new.military_discard
    for card_id in ("hammurabi", "pyramids", "colossus", "vast_territory_i",
                    "war_over_culture_iii"):
        assert card_id in new.removed
    # 进行中奇迹已付阶段蓝点退回供给区(与过期口径一致)
    assert p.blue_bank == p0.blue_bank + 1
    assert new.phase is Phase.ACTION


def test_resign_rotation_skips_seat() -> None:
    # 退出后轮换跳过其座位: 0 退出 -> 1 -> 2 -> 1(跳过 0, round+1)
    db = build_card_db()
    state = _state(civil_deck=("code_of_laws",) * 20)
    state = apply(state, Resign(), db)
    state = apply(state, PassTurn(), db)
    assert state.current_player == 1
    state = apply(state, SkipPolitics(), db)
    state = apply(state, PassTurn(), db)
    assert state.current_player == 2
    state = apply(state, SkipPolitics(), db)
    state = apply(state, PassTurn(), db)
    assert state.current_player == 1  # 跳过已退出的 0 号位
    assert state.round == 3


def test_resign_last_remaining_player_wins() -> None:
    # 2 人局一方退出 -> 只剩 1 人, 游戏立即结束, 该玩家直接判胜(不比文化)
    db = build_card_db()
    p0 = _player("P0", culture=50)
    p1 = _player("P1", culture=5)
    state = _state(players=(p0, p1))
    new = apply(state, Resign(), db)
    assert new.terminal
    assert new.final_scores is not None
    assert new.final_scores[1] > new.final_scores[0]  # 文化落后仍判胜


def test_resign_removes_wars_declared_on_resigner() -> None:
    # 其他玩家向退出者宣告的战争: 战争牌从游戏中移除, 宣战者 +7 文化
    db = build_card_db()
    p1 = _player(
        "P1", declared_wars=(("war_over_culture_iii", 0),), culture=3)
    state = _state(players=(_player("P0"), p1, _player("P2")))
    new = apply(state, Resign(), db)
    assert new.players[1].declared_wars == ()
    assert "war_over_culture_iii" in new.removed
    assert new.players[1].culture == 10
    assert not new.terminal  # 仍有 2 人, 游戏继续


def test_resign_removes_related_pacts() -> None:
    # 移除其他玩家游戏区域中与退出者有关的条约牌
    db = build_card_db()
    p0 = _player("P0", pacts=(("peace_treaty", "A"),))
    p1 = _player("P1", pacts=(("peace_treaty", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    new = apply(state, Resign(), db)
    assert new.players[0].pacts == ()
    assert new.players[1].pacts == ()
    assert "peace_treaty" in new.removed


def test_resigned_player_only_pass_turn() -> None:
    # 退出者回合仅剩 PassTurn(文明已移除, 无其他合法动作)
    db = build_card_db()
    state = apply(_state(), Resign(), db)
    assert legal_actions(db, state) == [PassTurn()]


# --- 体面退出后未来内政牌堆按新人数重组(规则书 p4, T13) ------------------------------


def test_resign_rebuilds_future_civil_decks() -> None:
    """3 人局时代 A 退出 1 人: 未开启的 I/II/III 内政堆按 2 人重组重洗.

    规则书 p4 体面退出: "在进入时代II或III之前, 玩家按照初始设置根据玩家
    当前人数重新调整相应的牌堆"。
    """
    db = build_card_db()
    future = {
        age.value: db.deck_for(age, 3)
        for age in (Age.I, Age.II, Age.III)
    }
    current = ("code_of_laws",) * 7  # 已开启的当前牌堆(时代 A)
    state = _state(age=Age.A, civil_deck=current, future_decks=future)
    rng_before = state.rng_state
    new = apply(state, Resign(), db)
    assert not new.terminal
    # 已开启的当前牌堆不变(规则: "不再更改当前的游戏牌堆")
    assert new.civil_deck == current
    # 未开启的 I/II/III 堆按 2 人重组(multiset 相等), 且消费 rng 重洗
    assert set(new.future_decks) == {"I", "II", "III"}
    for age in (Age.I, Age.II, Age.III):
        assert Counter(new.future_decks[age.value]) == Counter(
            db.deck_for(age, 2))
    assert new.rng_state != rng_before


def test_resign_rebuilds_only_unopened_decks() -> None:
    """时代 II 中退出: 只剩 III 堆未开启, 仅重组 III; 当前 II 堆不变."""
    db = build_card_db()
    current = db.deck_for(Age.II, 3)[:5]
    state = _state(
        age=Age.II, civil_deck=current,
        future_decks={Age.III.value: db.deck_for(Age.III, 3)})
    new = apply(state, Resign(), db)
    assert new.civil_deck == current
    assert set(new.future_decks) == {"III"}
    assert Counter(new.future_decks["III"]) == Counter(db.deck_for(Age.III, 2))


def test_resign_rebuild_deterministic() -> None:
    """同状态两次退出: 重组结果(含 rng_state)一致."""
    db = build_card_db()
    future = {age.value: db.deck_for(age, 4)
              for age in (Age.I, Age.II, Age.III)}
    players = tuple(_player(f"P{i}") for i in range(4))
    state = _state(age=Age.A, players=players, future_decks=future)
    first = apply(state, Resign(), db)
    second = apply(state, Resign(), db)
    assert first.future_decks == second.future_decks
    assert first.rng_state == second.rng_state
    for age in (Age.I, Age.II, Age.III):
        assert Counter(first.future_decks[age.value]) == Counter(
            db.deck_for(age, 3))


def test_resign_terminal_no_rebuild() -> None:
    """2 人局退出即终局: 不重组(无后续时代可进)."""
    db = build_card_db()
    future = {age.value: db.deck_for(age, 2)
              for age in (Age.I, Age.II, Age.III)}
    state = _state(age=Age.A, players=(_player("P0"), _player("P1")),
                   future_decks=future)
    new = apply(state, Resign(), db)
    assert new.terminal
    assert new.future_decks == future


# --- Julius Caesar 双政治 ----------------------------------------------------------


def test_caesar_second_political_action() -> None:
    # 凯撒在场且 caesar_used=False: 政治动作结算后可再执行一次政治行动
    db = build_card_db()
    p0 = _player(
        "P0", leader="julius_caesar",
        pacts=(("peace_treaty", "A"), ("military_alliance", "A")))
    p1 = _player("P1", pacts=(("peace_treaty", "B"),))
    p2 = _player("P2", pacts=(("military_alliance", "B"),))
    state = _state(players=(p0, p1, p2))
    # 第一次政治动作(取缔)-> 回 POLITICS 而非 ACTION, caesar_used=True
    state = apply(state, CancelPact("peace_treaty"), db)
    assert state.phase is Phase.POLITICS
    assert state.players[0].caesar_used
    # 第二次政治动作 -> ACTION(一次性)
    state = apply(state, CancelPact("military_alliance"), db)
    assert state.phase is Phase.ACTION


def test_no_second_politics_without_caesar() -> None:
    db = build_card_db()
    p0 = _player("P0", pacts=(("peace_treaty", "A"),))
    p1 = _player("P1", pacts=(("peace_treaty", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    state = apply(state, CancelPact("peace_treaty"), db)
    assert state.phase is Phase.ACTION
    assert not state.players[0].caesar_used


def test_caesar_used_not_retriggered() -> None:
    # caesar_used=True 时政治动作后不再回 POLITICS(一次性)
    db = build_card_db()
    p0 = _player(
        "P0", leader="julius_caesar", caesar_used=True,
        pacts=(("peace_treaty", "A"),))
    p1 = _player("P1", pacts=(("peace_treaty", "B"),))
    state = _state(players=(p0, p1, _player("P2")))
    state = apply(state, CancelPact("peace_treaty"), db)
    assert state.phase is Phase.ACTION


# --- P3-T5: trade_routes_agreement 每回合食物/资源替换 -----------------------------
#
# 卡牌数值表 v1.09 p3 条约表: A "Can use 1食物 instead of 1资源 each turn";
# B "Can use 1资源 instead of 1食物 each turn"。引擎确定性口径(SIMPLIFICATION):
# 仅当主货币不足且差额恰为 1 时启用替换(官方为玩家主动选择); 每回合一次,
# 已用标记 turn_discounts["trade_routes_used"], 回合末行动点恢复时清空。


def _trade_routes_state(side: str, **p0_overrides: object) -> GameState:
    """P0(side 侧)/P1(对侧)缔约 trade_routes 的 3 人局(ACTION 相位)."""
    other = "B" if side == "A" else "A"
    p0 = _player(
        "P0", pacts=(("trade_routes_agreement", side),), **p0_overrides)
    p1 = _player("P1", pacts=(("trade_routes_agreement", other),))
    return _state(players=(p0, p1, _player("P2")), phase=Phase.ACTION)


def test_trade_routes_side_a_food_for_resource() -> None:
    # A 侧支付资源费(建青铜 2 资源), 资源差 1 点 -> 用 1 食物抵 1 资源
    db = build_card_db()
    state = _trade_routes_state(
        "A", civil_actions=4,
        developed=_INITIAL_DEVELOPED + ("bronze",),
        card_tokens={"bronze": 1, "agriculture": 2})
    legal = legal_actions(db, state)
    assert Build("bronze") in legal  # 资源 1 + 食物抵 1 >= 造价 2
    new = apply(state, Build("bronze"), db)
    p = new.players[0]
    # 支付: 1 食物(agriculture 2->1) + 1 资源(bronze 1->0)
    assert p.card_tokens == {"agriculture": 1}
    assert p.turn_discounts == {effects.TRADE_ROUTES_USED_KEY: 1}
    assert p.buildings["mine"]["bronze"] == 3


def test_trade_routes_substitution_requires_pact() -> None:
    # 未缔约: 资源 1 < 造价 2, 不可建造
    db = build_card_db()
    p0 = _player(
        "P0", civil_actions=4,
        developed=_INITIAL_DEVELOPED + ("bronze",),
        card_tokens={"bronze": 1, "agriculture": 2})
    state = _state(players=(p0, _player("P1"), _player("P2")),
                   phase=Phase.ACTION)
    assert Build("bronze") not in legal_actions(db, state)


def test_trade_routes_effect_starts_on_accept() -> None:
    # 缔约(提议 -> 接受)后替换立即可用
    db = build_card_db()
    p0 = _player(
        "P0", hand_military=("trade_routes_agreement",), civil_actions=4,
        developed=_INITIAL_DEVELOPED + ("bronze",),
        card_tokens={"bronze": 1, "agriculture": 2})
    state = _state(players=(p0, _player("P1"), _player("P2")))
    state = apply(state, ProposePact("trade_routes_agreement", 1, "A"), db)
    state = apply(state, PactAccept(), db)
    assert state.players[0].pacts == (("trade_routes_agreement", "A"),)
    assert Build("bronze") in legal_actions(db, state)


def test_trade_routes_not_used_when_resource_sufficient() -> None:
    # SIMPLIFICATION: 主货币足够时不替换(官方为玩家主动选择), 食物不动
    db = build_card_db()
    state = _trade_routes_state(
        "A", civil_actions=4,
        developed=_INITIAL_DEVELOPED + ("bronze",),
        card_tokens={"bronze": 2, "agriculture": 1})
    new = apply(state, Build("bronze"), db)
    p = new.players[0]
    assert p.card_tokens == {"agriculture": 1}  # 正常付 2 资源
    assert effects.TRADE_ROUTES_USED_KEY not in p.turn_discounts


def test_trade_routes_once_per_turn() -> None:
    # 本回合已用过替换(标记在) -> 差额 1 也不可再替换
    db = build_card_db()
    state = _trade_routes_state(
        "A", civil_actions=4,
        developed=_INITIAL_DEVELOPED + ("bronze",),
        card_tokens={"bronze": 1, "agriculture": 2},
        turn_discounts={effects.TRADE_ROUTES_USED_KEY: 1})
    assert Build("bronze") not in legal_actions(db, state)


def test_trade_routes_marker_resets_at_turn_end() -> None:
    # 回合末行动点恢复时清空已用标记(下个回合可再替换)
    db = build_card_db()
    state = _trade_routes_state(
        "A", civil_actions=4,
        developed=_INITIAL_DEVELOPED + ("bronze",),
        card_tokens={"bronze": 1, "agriculture": 2})
    state = apply(state, Build("bronze"), db)
    assert state.players[0].turn_discounts == {effects.TRADE_ROUTES_USED_KEY: 1}
    new = turn.end_of_turn(state, db)
    assert effects.TRADE_ROUTES_USED_KEY not in new.players[0].turn_discounts


def test_trade_routes_side_b_resource_for_food() -> None:
    # B 侧支付食物费(增人口费 2 食物), 食物差 1 -> 用 1 资源抵 1 食物
    db = build_card_db()
    state = _trade_routes_state(
        "B", civil_actions=4, card_tokens={"agriculture": 1, "bronze": 2})
    legal = legal_actions(db, state)
    assert IncreasePopulation() in legal  # 食物 1 + 资源抵 1 >= 人口费 2
    new = apply(state, IncreasePopulation(), db)
    p = new.players[0]
    assert p.card_tokens == {"bronze": 1}  # 付 1 食物 + 1 资源
    assert p.turn_discounts == {effects.TRADE_ROUTES_USED_KEY: 1}
    assert p.worker_pool == 2
    assert p.yellow_bank == 17


def test_trade_routes_side_a_does_not_help_food_payment() -> None:
    # 替换方向由本方侧决定: A 侧(食->资)不能用于食物费用
    db = build_card_db()
    state = _trade_routes_state(
        "A", civil_actions=4, card_tokens={"agriculture": 1, "bronze": 2})
    assert IncreasePopulation() not in legal_actions(db, state)


def test_trade_routes_effect_ends_on_cancel() -> None:
    # 取缔条约后替换失效
    db = build_card_db()
    state = _trade_routes_state(
        "A", civil_actions=4,
        developed=_INITIAL_DEVELOPED + ("bronze",),
        card_tokens={"bronze": 1, "agriculture": 2})
    state = replace(state, phase=Phase.POLITICS)
    state = apply(state, CancelPact("trade_routes_agreement"), db)
    assert state.phase is Phase.ACTION
    assert Build("bronze") not in legal_actions(db, state)


# --- P3-T5: scientific_cooperation 研发折扣与对方付费 ------------------------------
#
# 卡牌数值表 v1.09 p3 条约表: "Discover a technology for -2科技, other player
# pays 1科技"(Sym=Yes, 双方可用)。卡面无 "each turn" 字样 -> 不限次(对照
# trade_routes 的 each turn); 对方支付为强制, 不足时扣到 0(下限 0)。仅
# DevelopTech(政府变更不属 "discover a technology")。


def _scientific_state(p1_science: int = 3, **p0_overrides: object) -> GameState:
    """P0(A 侧)/P1(B 侧)缔约 scientific_cooperation 的 3 人局(ACTION 相位)."""
    p0 = _player(
        "P0", pacts=(("scientific_cooperation", "A"),), **p0_overrides)
    p1 = _player(
        "P1", science=p1_science, pacts=(("scientific_cooperation", "B"),))
    return _state(players=(p0, p1, _player("P2")), phase=Phase.ACTION)


def test_scientific_cooperation_discount_and_partner_pays() -> None:
    # 研发法典(6 科技) -2 = 4; 结算时缔约对方 -1 科技
    db = build_card_db()
    state = _scientific_state(
        hand_civil=("code_of_laws",), science=4, civil_actions=4)
    legal = legal_actions(db, state)
    assert DevelopTech("code_of_laws") in legal
    new = apply(state, DevelopTech("code_of_laws"), db)
    assert new.players[0].science == 0
    assert "code_of_laws" in new.players[0].developed
    assert new.players[1].science == 2  # 对方支付 1 科技


def test_scientific_cooperation_requires_pact() -> None:
    # 未缔约: 科技 4 < 法典 6, 不可研发
    db = build_card_db()
    p0 = _player("P0", hand_civil=("code_of_laws",), science=4, civil_actions=4)
    state = _state(players=(p0, _player("P1"), _player("P2")),
                   phase=Phase.ACTION)
    assert DevelopTech("code_of_laws") not in legal_actions(db, state)


def test_scientific_cooperation_partner_pays_floors_at_zero() -> None:
    # 对方科技不足 1 时仍生效, 扣到 0(下限 0)
    db = build_card_db()
    state = _scientific_state(
        0, hand_civil=("code_of_laws",), science=4, civil_actions=4)
    new = apply(state, DevelopTech("code_of_laws"), db)
    assert new.players[0].science == 0
    assert new.players[1].science == 0


def test_scientific_cooperation_not_limited_per_turn() -> None:
    # 卡面无 "each turn" -> 一回合多次研发均享折扣, 对方每次都付 1 科技
    db = build_card_db()
    state = _scientific_state(
        5, hand_civil=("code_of_laws", "warfare"), science=10, civil_actions=4)
    state = apply(state, DevelopTech("code_of_laws"), db)  # 10 - (6-2) = 6
    assert state.players[0].science == 6
    assert state.players[1].science == 4
    assert DevelopTech("warfare") in legal_actions(db, state)
    state = apply(state, DevelopTech("warfare"), db)  # 6 - (5-2) = 3
    assert state.players[0].science == 3
    assert state.players[1].science == 3  # 对方再付 1


def test_scientific_cooperation_pending_develop_tech() -> None:
    # develop_tech pending 子行动同口径: 折扣适用, 对方仍付 1 科技
    db = build_card_db()
    state = _scientific_state(
        hand_civil=("code_of_laws",), science=4, civil_actions=4)
    pending = PendingEffect(effects.KIND_DEVELOP_TECH, 0)
    state = replace(state, pending=(pending,))
    legal = legal_actions(db, state)
    assert DevelopTech("code_of_laws") in legal
    new = apply(state, DevelopTech("code_of_laws"), db)
    assert new.pending == ()
    assert new.players[0].science == 0
    assert new.players[1].science == 2


def test_scientific_cooperation_effect_ends_on_cancel() -> None:
    # 取缔条约后折扣与对方付费均失效
    db = build_card_db()
    state = _scientific_state(
        hand_civil=("code_of_laws",), science=4, civil_actions=4)
    state = replace(state, phase=Phase.POLITICS)
    state = apply(state, CancelPact("scientific_cooperation"), db)
    assert DevelopTech("code_of_laws") not in legal_actions(db, state)
