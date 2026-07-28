"""回合开始选择机制 + Churchill/Bill Gates 测试(P3-T4).

- 回合开始选择(turn_start_choice pending): 公开阵型后、phase 置 POLITICS
  前压入, phase 保持 TURN_START 直至 ChooseTurnStart 结算(强制, 不可
  DeclineResponse);
- winston_churchill: 每回合二选一(PDF 第 2 页 Leaders 表 Age III 行:
  "+3 文化" 或 "本回合军事用途 3 科技 + 3 资源");
- bill_gates: (a) 实验室按矿山方式产资源(economy.produce "resource" 时
  LAB 类别有工人卡各产 1 蓝点, 蓝点价值 = 时代等级, 规则书附录);
  (b) 被替换离场时 +文化 = Σ 有工人实验室卡 × 时代等级(即时);
  实验室产资源不计入 impact_of_industry(规则书附录 p12)。
"""

import pytest

from tta.cards import build_card_db
from tta.engine import choices, economy, events, turn
from tta.engine.actions import (
    ChooseTurnStart,
    DeclineResponse,
    IllegalActionError,
    PlayLeader,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, Phase
from tta.engine.legal import legal_actions, turn_discount_for
from tta.engine.state import ROW_SLOTS, GameState, PlayerState


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {"name": name}
    base.update(overrides)
    return PlayerState(**base)


def _state(**overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.IV,  # 时代 IV 无牌堆: 回合开始不补牌, 聚焦选择机制
        "current_player": 0,
        "card_row": (None,) * ROW_SLOTS,
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (_player("P0"), _player("P1")),
        "rng_state": 0,
        "phase": Phase.ACTION,
    }
    base.update(overrides)
    return GameState(**base)


def _proceed_with_leader(leader: str | None) -> GameState:
    """P1 持指定领袖, 由 P0 推进到 P1 的回合开始."""
    p1 = _player("P1", leader=leader)
    state = _state(players=(_player("P0"), p1))
    return turn.proceed(state, build_card_db())


# --- 回合开始选择 pending 流程 -------------------------------------------------


def test_turn_start_choice_pending_pushed() -> None:
    new = _proceed_with_leader("winston_churchill")
    assert new.current_player == 1
    assert new.phase is Phase.TURN_START  # 选择完成前保持 TURN_START
    assert len(new.pending) == 1
    pending = new.pending[0]
    assert pending.kind == choices.KIND_TURN_START_CHOICE
    assert pending.responder is None  # 由 current_player 自己响应
    assert pending.context == {"source": "winston_churchill"}


def test_legal_offers_two_options_without_decline() -> None:
    new = _proceed_with_leader("winston_churchill")
    actions = legal_actions(build_card_db(), new)
    assert actions == [
        ChooseTurnStart(choices.CHURCHILL_OPTION_CULTURE),
        ChooseTurnStart(choices.CHURCHILL_OPTION_MILITARY),
    ]
    assert DeclineResponse() not in actions


def test_decline_turn_start_choice_raises() -> None:
    new = _proceed_with_leader("winston_churchill")
    with pytest.raises(IllegalActionError):
        apply(new, DeclineResponse(), build_card_db())


def test_invalid_option_raises() -> None:
    new = _proceed_with_leader("winston_churchill")
    with pytest.raises(IllegalActionError):
        apply(new, ChooseTurnStart("gold"), build_card_db())


def test_no_choice_pending_without_turn_start_leader() -> None:
    new = _proceed_with_leader(None)
    assert new.pending == ()
    assert new.phase is Phase.POLITICS


def test_choose_turn_start_serialization_roundtrip() -> None:
    action = ChooseTurnStart("military")
    assert action_from_dict(action_to_dict(action)) == action


# --- Churchill 两选项 -----------------------------------------------------------


def test_churchill_culture_option() -> None:
    new = _proceed_with_leader("winston_churchill")
    db = build_card_db()
    after = apply(new, ChooseTurnStart("culture"), db)
    q = after.players[1]
    assert q.culture == new.players[1].culture + 3
    assert after.pending == ()
    assert after.phase is Phase.POLITICS  # 选择后正常进入政治阶段
    # 政治阶段合法动作恢复(SkipPolitics 恒可用)
    assert legal_actions(db, after)


def test_churchill_military_option() -> None:
    new = _proceed_with_leader("winston_churchill")
    after = apply(new, ChooseTurnStart("military"), build_card_db())
    q = after.players[1]
    assert q.science == new.players[1].science + 3
    assert q.turn_discounts == {"unit_build": 3}
    assert turn_discount_for(q, CardCategory.INFANTRY) == 3
    assert after.pending == ()
    assert after.phase is Phase.POLITICS


def test_churchill_military_discount_stacks() -> None:
    """军事折扣与 homer/patriotism 同键叠加(turn_discounts["unit_build"])."""
    p1 = _player(
        "P1", leader="winston_churchill", turn_discounts={"unit_build": 2})
    state = _state(players=(_player("P0"), p1))
    new = turn.proceed(state, build_card_db())
    after = apply(new, ChooseTurnStart("military"), build_card_db())
    assert after.players[1].turn_discounts["unit_build"] == 5


# --- Bill Gates: 实验室产资源 ----------------------------------------------------


def test_gates_labs_produce_blue_tokens() -> None:
    """领袖为 bill_gates 时, 有工人实验室卡各产 1 蓝点(矿场照常)."""
    db = build_card_db()
    p = _player(
        "P0",
        leader="bill_gates",
        developed=("philosophy", "computers", "bronze"),
        buildings={"lab": {"philosophy": 1, "computers": 1},
                   "mine": {"bronze": 1}},
        blue_bank=10,
    )
    q = economy.produce(db, p, "resource")
    assert q.card_tokens == {"philosophy": 1, "computers": 1, "bronze": 1}
    assert q.blue_bank == 7
    # 实验室蓝点价值 = 时代等级(philosophy A=1, computers III=4), 计入资源总量
    assert economy.resource_total(db, q) == 1 + 4 + 1
    # 入参不被改动
    assert p.card_tokens == {}


def test_labs_do_not_produce_without_gates() -> None:
    db = build_card_db()
    p = _player(
        "P0",
        developed=("philosophy", "bronze"),
        buildings={"lab": {"philosophy": 1}, "mine": {"bronze": 1}},
        blue_bank=10,
    )
    q = economy.produce(db, p, "resource")
    assert q.card_tokens == {"bronze": 1}


def test_labs_not_resource_gain_target_without_gates() -> None:
    """非 Gates 玩家的实验室不作为资源蓝点落点(gain_tokens 仍落矿场)."""
    db = build_card_db()
    p = _player(
        "P0",
        developed=("philosophy", "bronze"),
        buildings={"lab": {"philosophy": 1}, "mine": {"bronze": 1}},
        blue_bank=5,
    )
    q = economy.gain_tokens(db, p, "resource", 2)
    assert q.card_tokens == {"bronze": 2}


def test_gates_resource_gain_targets_lowest_lab() -> None:
    """Gates 玩家获得资源时, 蓝点落最低等级卡(实验室等级 = 时代序)."""
    db = build_card_db()
    p = _player(
        "P0",
        leader="bill_gates",
        developed=("philosophy", "computers"),
        buildings={"lab": {"philosophy": 1, "computers": 1}},
        blue_bank=5,
    )
    q = economy.gain_tokens(db, p, "resource", 2)
    # philosophy(A=1) < computers(III=4)
    assert q.card_tokens == {"philosophy": 2}


def test_gates_lab_tokens_spent_as_resources() -> None:
    """实验室蓝点可按等级价值支付资源(含 Gates 离场后残留在卡上的蓝点)."""
    db = build_card_db()
    p = _player(
        "P0",
        developed=("computers",),
        buildings={"lab": {"computers": 1}},
        card_tokens={"computers": 1},
        blue_bank=16,
    )
    assert economy.resource_total(db, p) == 4
    q = economy.pay(db, p, "resource", 4)
    assert q.card_tokens == {}
    assert q.blue_bank == 17  # 取下的蓝点放回供给区


# --- Bill Gates: 被替换离场即时奖励 ----------------------------------------------


def test_gates_replacement_grants_lab_level_culture() -> None:
    """PlayLeader 替换 bill_gates: +文化 = Σ 有工人实验室卡 × 时代等级."""
    db = build_card_db()
    p0 = _player(
        "P0",
        leader="bill_gates",
        developed=("philosophy", "computers"),
        buildings={"lab": {"philosophy": 1, "computers": 2}},
        hand_civil=("sid_meier",),
        civil_actions=2,
        culture=5,
    )
    state = _state(players=(p0, _player("P1")))
    new = apply(state, PlayLeader("sid_meier"), db)
    q = new.players[0]
    # philosophy(A=1) + computers(III=4) = 5(每卡 1 次, 与工人数无关)
    assert q.culture == 10
    assert q.leader == "sid_meier"
    assert "bill_gates" in new.discard
    # 替换领袖拿回 1 白点(净耗 0)
    assert q.civil_actions == 2


def test_non_gates_replacement_no_bonus() -> None:
    db = build_card_db()
    p0 = _player(
        "P0",
        leader="sid_meier",
        developed=("philosophy",),
        buildings={"lab": {"philosophy": 1}},
        hand_civil=("bill_gates",),
        civil_actions=2,
        culture=5,
    )
    state = _state(players=(p0, _player("P1")))
    new = apply(state, PlayLeader("bill_gates"), db)
    assert new.players[0].culture == 5


# --- Bill Gates: 实验室产资源不计入工业的影响 --------------------------------------


def test_gates_labs_not_counted_in_impact_of_industry() -> None:
    """规则书附录 p12: 工业的影响只计矿场产出, 实验室产资源不计入."""
    db = build_card_db()
    p0 = _player(
        "P0",
        leader="bill_gates",
        developed=("computers",),
        buildings={"lab": {"computers": 1}},
    )
    p1 = _player(
        "P1",
        developed=("bronze",),
        buildings={"mine": {"bronze": 2}},
    )
    state = _state(age=Age.III, players=(p0, p1))
    new = events.resolve_event(state, db, "impact_of_industry")
    assert new.players[0].culture == 0
    assert new.players[1].culture == 2
