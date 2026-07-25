"""侵略与防御响应测试(P2-T8).

覆盖: 新动作序列化、PlayAggression 合法性(手牌/目标非己/军力严格更高/
军事行动费/Gandhi 双倍费用/Gandhi 持有者禁打/停战条约)、防御响应
(PlayDefenseBonus / DiscardForStrength / PassResponse, 牌数上限 = 防御方
军事行动点)、防御成功(军力 ≥ 攻击方 -> 侵略牌弃置无效果)与失败(结算
AGGRESSION_HANDLERS)、各侵略效果(enslave/plunder/raid/annex/infiltrate/
spy/armed_intervention)、夺取上限、结算后控制权与相位恢复。

规则核对(卡牌数值表 v1.09 第 3 页 + 规则书 p4):
- raid 的受害建筑图标为城市建筑图标(不含农场/矿场); raid_ii/iii 各摧毁
  2 个建筑, 收益 = 总造价一半(向上取整);
- spy_ii 侵略方为 "Scores same amount"(文化分, 等于受害者实失科技);
- 防御方打出+弃置的牌总数不能超过其总军事行动点数(规则书 p4 限制)。
"""


from tta.cards import build_card_db
from tta.engine.actions import (
    ChooseEventOption,
    DiscardForStrength,
    PassResponse,
    PlayAggression,
    PlayDefenseBonus,
    SkipPolitics,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, Phase
from tta.engine.legal import legal_actions
from tta.engine.state import ROW_SLOTS, GameState, PlayerState

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
_STRONG_BUILDINGS = {
    "farm": {"agriculture": 2},
    "mine": {"bronze": 2},
    "lab": {"philosophy": 1},
    "infantry": {"warriors": 2},
}


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {
        "name": name,
        "developed": _INITIAL_DEVELOPED,
        "buildings": {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()},
    }
    base.update(overrides)
    return PlayerState(**base)


def _aggressor(**overrides: object) -> PlayerState:
    """攻击方: 2 武士(军力 2) + 2 军事行动 + 手牌 raid_i."""
    base: dict = {
        "buildings": {k: dict(v) for k, v in _STRONG_BUILDINGS.items()},
        "hand_military": ("raid_i",),
        "military_actions": 2,
    }
    base.update(overrides)
    return _player("P0", **base)


def _state(*, num_players: int = 2, **overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.A,
        "current_player": 0,
        "card_row": (None,) * ROW_SLOTS,
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (_aggressor(), _player("P1")),
        "rng_state": 42,
        "phase": Phase.POLITICS,
    }
    base.update(overrides)
    return GameState(**base)


def _launched(state: GameState, card_id: str = "raid_i",
              target: int = 1) -> GameState:
    """打出侵略牌进入防御响应 pending 的快捷路径."""
    db = build_card_db()
    return apply(state, PlayAggression(card_id, target), db)


# --- 新动作序列化 ------------------------------------------------------------


def test_new_actions_serialization_roundtrip() -> None:
    actions = [
        PlayDefenseBonus("defense_colonization_i"),
        DiscardForStrength("fighting_band"),
        PassResponse(),
    ]
    for action in actions:
        assert action_from_dict(action_to_dict(action)) == action


# --- PlayAggression 合法性 ----------------------------------------------------


def test_play_aggression_enumerated_for_valid_target() -> None:
    db = build_card_db()
    state = _state()
    assert PlayAggression("raid_i", 1) in legal_actions(db, state)


def test_play_aggression_requires_card_in_hand() -> None:
    db = build_card_db()
    p0 = _aggressor(hand_military=("fighting_band",))
    state = _state(players=(p0, _player("P1")))
    assert not any(
        isinstance(a, PlayAggression) for a in legal_actions(db, state))


def test_play_aggression_target_self_excluded() -> None:
    db = build_card_db()
    state = _state()
    assert PlayAggression("raid_i", 0) not in legal_actions(db, state)


def test_play_aggression_requires_strictly_higher_strength() -> None:
    # 规则书 p4: 不能攻击军力等级大于或等于你的玩家
    db = build_card_db()
    p1 = _player("P1", buildings={
        k: dict(v) for k, v in _STRONG_BUILDINGS.items()})  # 军力 2 = 攻击方
    state = _state(players=(_aggressor(), p1))
    assert PlayAggression("raid_i", 1) not in legal_actions(db, state)


def test_play_aggression_requires_military_actions() -> None:
    # enslave_i 费 2 红点: 仅 1 红点时不可打出; raid_i 费 1 不受影响
    db = build_card_db()
    p0 = _aggressor(
        hand_military=("raid_i", "enslave_i"), military_actions=1)
    state = _state(players=(p0, _player("P1")))
    legal = legal_actions(db, state)
    assert PlayAggression("raid_i", 1) in legal
    assert PlayAggression("enslave_i", 1) not in legal


def test_gandhi_doubles_aggression_cost() -> None:
    # 甘地在场: 对其侵略费用 ×2(P1 遗留被动落地)
    db = build_card_db()
    p0 = _aggressor(hand_military=("plunder_i",), military_actions=2)
    p1 = _player("P1", leader="mahatma_gandhi")
    state = _state(players=(p0, p1))
    assert PlayAggression("plunder_i", 1) in legal_actions(db, state)
    # 仅 1 红点时双倍费(2)不可支付
    p0 = _aggressor(hand_military=("plunder_i",), military_actions=1)
    state = _state(players=(p0, p1))
    assert PlayAggression("plunder_i", 1) not in legal_actions(db, state)


def test_gandhi_owner_cannot_play_aggression() -> None:
    # 甘地卡文本: 你不能打出侵略或战争牌
    db = build_card_db()
    p0 = _aggressor(leader="mahatma_gandhi")
    state = _state(players=(p0, _player("P1")))
    assert not any(
        isinstance(a, PlayAggression) for a in legal_actions(db, state))


def test_peace_pact_blocks_aggression() -> None:
    # 停战类条约(和平条约等)生效中不可互相攻击(T10 建模: 双方 pacts 同录)
    db = build_card_db()
    p0 = _aggressor(pacts=("peace_treaty",))
    p1 = _player("P1", pacts=("peace_treaty",))
    state = _state(players=(p0, p1))
    assert not any(
        isinstance(a, PlayAggression) for a in legal_actions(db, state))


# --- 发动侵略结算 --------------------------------------------------------------


def test_play_aggression_pays_and_pushes_defense_pending() -> None:
    db = build_card_db()
    p0 = _aggressor(hand_military=("raid_i", "fighting_band"))
    state = _state(players=(p0, _player("P1")))
    new = apply(state, PlayAggression("raid_i", 1), db)
    # 付 1 红点(raid_i 费 1), 侵略卡从手牌揭示(不在手牌)
    assert new.players[0].military_actions == 1
    assert new.players[0].hand_military == ("fighting_band",)
    # pending kind="aggression_defense", responder=目标, 攻击军力快照 2
    assert len(new.pending) == 1
    pending = new.pending[0]
    assert pending.kind == "aggression_defense"
    assert pending.responder == 1
    assert pending.context["card"] == "raid_i"
    assert pending.context["attacker"] == 0
    assert pending.context["attack_strength"] == 2
    # 控制权未移(响应机制), 相位保持 POLITICS(响应优先)
    assert new.current_player == 0
    assert new.phase is Phase.POLITICS


def test_defense_legal_actions() -> None:
    db = build_card_db()
    p1 = _player(
        "P1", hand_military=("defense_colonization_i", "fighting_band"),
        military_actions=2)
    state = _launched(_state(players=(_aggressor(), p1)))
    legal = legal_actions(db, state)
    # 防御奖励牌可打出; 任意军事牌可弃置 +1 军力; 恒可 PassResponse
    assert PlayDefenseBonus("defense_colonization_i") in legal
    assert DiscardForStrength("defense_colonization_i") in legal
    assert DiscardForStrength("fighting_band") in legal
    assert PassResponse() in legal


def test_defense_cards_capped_by_military_actions() -> None:
    # 规则书 p4 限制: 打出+弃置的牌总数不能超过防御方总军事行动点数
    db = build_card_db()
    p1 = _player(
        "P1",
        hand_military=("defense_colonization_i", "defense_colonization_i"),
        military_actions=1,
    )
    state = _launched(_state(players=(_aggressor(), p1)))
    state = apply(state, PlayDefenseBonus("defense_colonization_i"), db)
    legal = legal_actions(db, state)
    assert legal == [PassResponse()]


# --- 防御判定 ------------------------------------------------------------------


def test_defense_bonus_success_discards_aggression() -> None:
    # 防御方军力(1 + 奖励 2 = 3) >= 攻击方(2) -> 侵略失败, 无效果
    db = build_card_db()
    p1 = _player(
        "P1", hand_military=("defense_colonization_i",), military_actions=2)
    state = _launched(_state(players=(_aggressor(), p1)))
    state = apply(state, PlayDefenseBonus("defense_colonization_i"), db)
    state = apply(state, PassResponse(), db)
    assert state.pending == ()
    # 侵略牌与奖励牌均入军事弃牌堆, 无任何侵略效果(实验室工人保留)
    assert set(state.military_discard) == {"raid_i", "defense_colonization_i"}
    assert state.players[1].buildings["lab"] == {"philosophy": 1}
    assert state.phase is Phase.ACTION
    assert state.current_player == 0


def test_defense_discard_for_strength_tie_fails_aggression() -> None:
    # 弃 1 军事牌 +1 军力: 1 + 1 = 2 >= 2(平局防御成功)
    db = build_card_db()
    p1 = _player("P1", hand_military=("fighting_band",), military_actions=2)
    state = _launched(_state(players=(_aggressor(), p1)))
    state = apply(state, DiscardForStrength("fighting_band"), db)
    state = apply(state, PassResponse(), db)
    assert "raid_i" in state.military_discard
    assert state.players[1].buildings["lab"] == {"philosophy": 1}


def test_defense_failure_resolves_effect() -> None:
    # 防御方直接 PassResponse: 1 < 2 -> 侵略成功, 结算 raid_i 摧毁 pending
    db = build_card_db()
    state = _launched(_state())
    state = apply(state, PassResponse(), db)
    assert len(state.pending) == 1
    assert state.pending[0].kind == "aggression_raid"
    assert state.pending[0].responder == 1
    assert state.phase is Phase.ACTION


# --- raid ---------------------------------------------------------------------


def test_raid_i_destroy_building_and_loot() -> None:
    # 受害者摧毁 1 个 I/A 级城市建筑(philosophy 造价 3) -> 工人回池;
    # 攻击方 +ceil(3/2) = 2 资源
    db = build_card_db()
    state = _launched(_state())
    state = apply(state, PassResponse(), db)
    legal = legal_actions(db, state)
    assert ChooseEventOption("philosophy") in legal
    state = apply(state, ChooseEventOption("philosophy"), db)
    victim = state.players[1]
    assert victim.buildings["lab"] == {}
    assert victim.worker_pool == 2
    attacker = state.players[0]
    assert attacker.card_tokens.get("bronze") == 2  # 2 资源入最低级矿场
    assert state.pending == ()
    assert "raid_i" in state.military_discard


def test_raid_i_no_eligible_building_passes() -> None:
    # 受害者无城市建筑工人 -> 仅可 PassResponse 跳过, 无收益
    db = build_card_db()
    p1 = _player("P1", buildings={
        "farm": {"agriculture": 2}, "mine": {"bronze": 2},
        "infantry": {"warriors": 1},
    })
    state = _launched(_state(players=(_aggressor(), p1)))
    state = apply(state, PassResponse(), db)
    assert legal_actions(db, state) == [PassResponse()]
    state = apply(state, PassResponse(), db)
    assert state.pending == ()
    assert state.players[0].card_tokens == {}


def test_raid_ii_destroys_two_buildings_chain() -> None:
    # raid_ii: -1 个 II-A 级 + -1 个 I-A 级城市建筑(链式 pending);
    # 收益 = 总造价一半向上取整: organized_religion 7 + philosophy 3
    # -> ceil(10/2) = 5
    db = build_card_db()
    p1 = _player(
        "P1",
        developed=_INITIAL_DEVELOPED + ("organized_religion",),
        buildings={
            "farm": {"agriculture": 2}, "mine": {"bronze": 2},
            "lab": {"philosophy": 1}, "temple": {"organized_religion": 1},
            "infantry": {"warriors": 1},
        },
    )
    p0 = _aggressor(hand_military=("raid_ii",))
    state = _launched(_state(players=(p0, p1)), "raid_ii")
    state = apply(state, PassResponse(), db)
    # 第一个 pending: max_age=II
    assert state.pending[0].context["max_age"] == "II"
    state = apply(state, ChooseEventOption("organized_religion"), db)
    # 第二个 pending: max_age=I, 累计 loot 带入
    assert state.pending[0].kind == "aggression_raid"
    assert state.pending[0].context["max_age"] == "I"
    assert state.pending[0].context["loot"] == 7
    state = apply(state, ChooseEventOption("philosophy"), db)
    assert state.pending == ()
    victim = state.players[1]
    assert victim.buildings["temple"] == {}
    assert victim.buildings["lab"] == {}
    assert victim.worker_pool == 3
    assert state.players[0].card_tokens.get("bronze") == 5


# --- plunder -------------------------------------------------------------------


def _plundered(p1: PlayerState, card_id: str = "plunder_i") -> GameState:
    p0 = _aggressor(hand_military=(card_id,))
    state = _launched(_state(players=(p0, p1)), card_id)
    db = build_card_db()
    return apply(state, PassResponse(), db)


def test_plunder_transfer_with_mix_choice() -> None:
    db = build_card_db()
    p1 = _player("P1", card_tokens={"agriculture": 2, "bronze": 2})
    state = _plundered(p1)
    assert state.pending[0].kind == "aggression_plunder"
    legal = legal_actions(db, state)
    # 共 3 的组合: food:3 / food:2,resource:1 / food:1,resource:2 / resource:3
    assert ChooseEventOption("food:3") in legal
    assert ChooseEventOption("food:2,resource:1") in legal
    assert ChooseEventOption("food:1,resource:2") in legal
    assert ChooseEventOption("resource:3") in legal
    state = apply(state, ChooseEventOption("food:2,resource:1"), db)
    victim = state.players[1]
    assert victim.card_tokens.get("agriculture", 0) == 0
    assert victim.card_tokens.get("bronze") == 1
    attacker = state.players[0]
    assert attacker.card_tokens.get("agriculture") == 2
    assert attacker.card_tokens.get("bronze") == 1
    assert state.pending == ()


def test_plunder_capped_by_victim_holdings() -> None:
    # 受害者仅 2 食物: 选 food:3 实失 2, 攻击方只得 2(上限 = 实际拥有量)
    db = build_card_db()
    p1 = _player("P1", card_tokens={"agriculture": 2})
    state = _plundered(p1)
    state = apply(state, ChooseEventOption("food:3"), db)
    assert state.players[1].card_tokens.get("agriculture", 0) == 0
    assert state.players[0].card_tokens.get("agriculture") == 2


# --- 其余侵略效果 ----------------------------------------------------------------


def test_enslave_population_loss_and_gains() -> None:
    # 受害者 -1 人口(工人池优先, 黄点回银行); 攻击方 +2 食物 +2 资源
    db = build_card_db()
    p0 = _aggressor(hand_military=("enslave_i",))
    state = _launched(_state(players=(p0, _player("P1"))), "enslave_i")
    assert state.players[0].military_actions == 0  # 费 2 红点
    state = apply(state, PassResponse(), db)
    assert state.pending == ()  # 无受害者选择, 即时结算
    victim = state.players[1]
    assert victim.worker_pool == 0
    assert victim.yellow_bank == 19
    attacker = state.players[0]
    assert attacker.card_tokens.get("agriculture") == 2
    assert attacker.card_tokens.get("bronze") == 2


def test_annex_colony_transfer_with_tokens() -> None:
    # developed_territory_i 永久 1 黄点 1 蓝点: 受害者归还, 攻击方取得
    db = build_card_db()
    p1 = _player("P1", colonies=("developed_territory_i",))
    p0 = _aggressor(hand_military=("annex_ii",))
    state = _launched(_state(players=(p0, p1)), "annex_ii")
    state = apply(state, PassResponse(), db)
    assert state.pending[0].kind == "aggression_annex"
    legal = legal_actions(db, state)
    assert ChooseEventOption("developed_territory_i") in legal
    state = apply(state, ChooseEventOption("developed_territory_i"), db)
    victim = state.players[1]
    assert victim.colonies == ()
    assert victim.yellow_bank == 17
    assert victim.blue_bank == 15
    attacker = state.players[0]
    assert attacker.colonies == ("developed_territory_i",)
    assert attacker.yellow_bank == 19
    assert attacker.blue_bank == 17
    assert state.pending == ()


def test_annex_no_colony_no_effect() -> None:
    db = build_card_db()
    p0 = _aggressor(hand_military=("annex_ii",))
    state = _launched(_state(players=(p0, _player("P1"))), "annex_ii")
    state = apply(state, PassResponse(), db)
    assert state.pending == ()
    assert state.phase is Phase.ACTION


def test_infiltrate_discard_leader() -> None:
    # 受害者弃领袖(homer, 时代 A = 1 级) -> 攻击方 +3 文化/级 = +3
    db = build_card_db()
    p1 = _player("P1", leader="homer", leader_ages=("A",))
    p0 = _aggressor(hand_military=("infiltrate_ii",))
    state = _launched(_state(players=(p0, p1)), "infiltrate_ii")
    state = apply(state, PassResponse(), db)
    assert state.pending[0].kind == "aggression_infiltrate"
    legal = legal_actions(db, state)
    assert ChooseEventOption("leader") in legal
    state = apply(state, ChooseEventOption("leader"), db)
    victim = state.players[1]
    assert victim.leader is None
    assert "homer" in state.discard
    assert state.players[0].culture == 3
    assert state.pending == ()


def test_infiltrate_discard_unfinished_wonder() -> None:
    # 弃未完成奇迹(pyramids 已付 2 阶段): 蓝点退回供给区, 卡入 removed;
    # 攻击方 +3 文化(时代 A = 1 级)
    db = build_card_db()
    p1 = _player("P1", wonder_progress=("pyramids", 2), blue_bank=10)
    p0 = _aggressor(hand_military=("infiltrate_ii",))
    state = _launched(_state(players=(p0, p1)), "infiltrate_ii")
    state = apply(state, PassResponse(), db)
    legal = legal_actions(db, state)
    assert ChooseEventOption("pyramids") in legal
    state = apply(state, ChooseEventOption("pyramids"), db)
    victim = state.players[1]
    assert victim.wonder_progress is None
    assert victim.blue_bank == 12
    assert "pyramids" in state.removed
    assert state.players[0].culture == 3


def test_spy_science_loss_scores_culture() -> None:
    # PDF: 受害者 -5 科技; 攻击方 Scores same amount(文化分, 按实失量)
    db = build_card_db()
    p1 = _player("P1", science=3)
    p0 = _aggressor(hand_military=("spy_ii",))
    state = _launched(_state(players=(p0, p1)), "spy_ii")
    state = apply(state, PassResponse(), db)
    assert state.players[1].science == 0
    assert state.players[0].culture == 3
    assert state.pending == ()


def test_armed_intervention_culture_loss() -> None:
    # 受害者 -7 文化(下限 0); 攻击方 +7 文化(独立效果)
    db = build_card_db()
    p1 = _player("P1", culture=10)
    p0 = _aggressor(hand_military=("armed_intervention_iii",))
    state = _launched(_state(players=(p0, p1)), "armed_intervention_iii")
    state = apply(state, PassResponse(), db)
    assert state.players[1].culture == 3
    assert state.players[0].culture == 7


# --- 控制权与相位恢复 -------------------------------------------------------------


def test_control_and_phase_restored_after_resolution() -> None:
    # 结算后控制权回攻击方, phase -> ACTION; 每回合限 1 政治行动
    db = build_card_db()
    p0 = _aggressor(hand_military=("raid_i", "plunder_i"))
    state = _launched(_state(players=(p0, _player("P1"))))
    state = apply(state, PassResponse(), db)
    state = apply(state, ChooseEventOption("philosophy"), db)
    assert state.current_player == 0
    assert state.phase is Phase.ACTION
    legal = legal_actions(db, state)
    assert SkipPolitics() not in legal
    assert not any(isinstance(a, PlayAggression) for a in legal)
