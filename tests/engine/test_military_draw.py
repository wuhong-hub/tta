"""军事牌堆组建与回合末抓弃测试(P2-T3).

覆盖: new_game 军事组建(时代 A 事件堆 = 人数+2, 余牌入 removed, I/II/III
军事堆入 future_military_decks, 时代 A military_deck 为空)、回合末抓军事牌
(min(剩余红点, 3), 牌堆空切洗军事弃牌堆, 时代 IV 不抓)、超上限弃牌
discard_military pending 流程、时代切换军事堆更替。
"""

import pytest

from tta.cards import build_card_db
from tta.engine import turn
from tta.engine.actions import (
    DiscardMilitary,
    IllegalActionError,
    PassTurn,
    Resign,
    SkipPolitics,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType, Phase
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.setup import new_game
from tta.engine.state import ROW_SLOTS, GameState, PlayerState


def _card(card_id: str, category: CardCategory, age: Age = Age.A,
          deck: DeckType = DeckType.CIVIL, **overrides: object,
          ) -> CardDefinition:
    base: dict = {
        "id": card_id,
        "name": card_id,
        "name_en": card_id,
        "age": age,
        "deck": deck,
        "category": category,
    }
    base.update(overrides)
    return CardDefinition(**base)


def _db() -> CardDB:
    cards = {
        "despotism": _card(
            "despotism", CardCategory.GOVERNMENT,
            government=GovernmentStats(
                civil_actions=4, military_actions=2, urban_limit=2),
        ),
        "agriculture": _card("agriculture", CardCategory.FARM, token_value=1),
        "bronze": _card("bronze", CardCategory.MINE, token_value=1),
        # 军事手牌上限 +1 的奇迹(验证 military_hand_extra 计入上限)
        "great_library": _card(
            "great_library", CardCategory.WONDER, wonder_stages=(1,),
            wonder_bonus={"military_hand_extra": 1}),
    }
    for age, prefix in ((Age.A, "xa"), (Age.I, "xi"),
                        (Age.II, "xii"), (Age.III, "xiii")):
        for i in range(20):
            cards[f"{prefix}{i}"] = _card(f"{prefix}{i}", CardCategory.ACTION, age)
    for age, prefix in ((Age.A, "ma"), (Age.I, "mi"),
                        (Age.II, "mii"), (Age.III, "miii")):
        for i in range(10):
            cards[f"{prefix}{i}"] = _card(
                f"{prefix}{i}", CardCategory.EVENT, age,
                deck=DeckType.MILITARY, quantities=(1, 1, 1))
    return CardDB(cards=cards, initial_tableau=("agriculture", "bronze"),
                  initial_government="despotism")


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {"name": name}
    base.update(overrides)
    return PlayerState(**base)


def _state(**overrides: object) -> GameState:
    """默认: round 2 / 时代 I / P0 行动, 牌列满, 内政堆余 7 张."""
    base: dict = {
        "round": 2,
        "age": Age.I,
        "current_player": 0,
        "card_row": tuple(f"xi{i}" for i in range(ROW_SLOTS)),
        "civil_deck": tuple(f"xi{i}" for i in range(ROW_SLOTS, 20)),
        "future_decks": {
            "II": tuple(f"xii{i}" for i in range(20)),
            "III": tuple(f"xiii{i}" for i in range(20)),
        },
        "discard": (),
        "removed": (),
        "players": (_player("P0"), _player("P1")),
        "rng_state": 7,
    }
    base.update(overrides)
    return GameState(**base)


# --- new_game 军事组建(真实牌库) -------------------------------------------


@pytest.fixture(scope="module")
def real_db() -> CardDB:
    return build_card_db()


@pytest.mark.parametrize("num_players", (2, 3, 4))
def test_setup_current_events_count(real_db, num_players) -> None:
    """时代 A 军事堆(10 事件)取 人数+2 张为 current_events, 余入 removed."""
    state = new_game(real_db, num_players, seed=5)
    assert len(state.current_events) == num_players + 2
    age_a_military = real_db.deck_for(Age.A, num_players, DeckType.MILITARY)
    assert len(age_a_military) == 10
    # 事件堆 + 移除 = 时代 A 军事堆全集(multiset), 不回牌堆
    assert sorted(state.current_events + state.removed) == sorted(age_a_military)


@pytest.mark.parametrize("num_players", (2, 3, 4))
def test_setup_future_military_decks(real_db, num_players) -> None:
    """时代 A 无军事牌可抓; I/II/III 军事堆洗匀入 future_military_decks."""
    state = new_game(real_db, num_players, seed=5)
    assert state.military_deck == ()
    assert set(state.future_military_decks) == {"I", "II", "III"}
    for key, age in (("I", Age.I), ("II", Age.II), ("III", Age.III)):
        expected = real_db.deck_for(age, num_players, DeckType.MILITARY)
        assert sorted(state.future_military_decks[key]) == sorted(expected)


def test_first_round_no_military_draw(real_db) -> None:
    """第一回合全员 0 红点 -> 回合末抓不到军事牌."""
    state = new_game(real_db, 2, seed=3)
    assert all(p.military_actions == 0 for p in state.players)
    new = apply(state, PassTurn(), real_db)
    assert all(p.hand_military == () for p in new.players)
    assert new.pending == ()


# --- 回合末抓军事牌 ----------------------------------------------------------


def test_draw_capped_by_remaining_military_actions() -> None:
    db = _db()
    p0 = _player("P0", military_actions=2)
    state = _state(players=(p0, _player("P1")),
                   military_deck=("mi0", "mi1", "mi2", "mi3"))
    new = turn.advance(state, db)
    assert new.players[0].hand_military == ("mi0", "mi1")
    assert new.military_deck == ("mi2", "mi3")
    # 手牌 2 = 上限 2, 无弃牌 pending
    assert new.pending == ()
    # 入参不被改动
    assert state.players[0].hand_military == ()


def test_draw_capped_at_three() -> None:
    db = _db()
    p0 = _player("P0", military_actions=5)
    state = _state(players=(p0, _player("P1")),
                   military_deck=tuple(f"mi{i}" for i in range(6)))
    new = turn.advance(state, db)
    assert new.players[0].hand_military == ("mi0", "mi1", "mi2")
    assert len(new.military_deck) == 3


def test_draw_nothing_when_deck_and_discard_empty() -> None:
    db = _db()
    p0 = _player("P0", military_actions=3)
    state = _state(players=(p0, _player("P1")))
    new = turn.advance(state, db)
    assert new.players[0].hand_military == ()
    assert new.rng_state == state.rng_state  # 未洗牌, rng 不消耗


def test_reshuffle_discard_when_deck_empty() -> None:
    """牌堆空且弃牌堆非空 -> 切洗弃牌堆为新牌堆继续抓."""
    db = _db()
    discard = tuple(f"mi{i}" for i in range(5))
    p0 = _player("P0", military_actions=2)
    state = _state(players=(p0, _player("P1")),
                   military_deck=(), military_discard=discard)
    new = turn.advance(state, db)
    hand = new.players[0].hand_military
    assert len(hand) == 2
    assert new.military_discard == ()
    assert len(new.military_deck) == 3
    # 守恒: 手牌 + 新牌堆 = 原弃牌堆
    assert sorted(hand + new.military_deck) == sorted(discard)
    assert new.rng_state != state.rng_state  # 切洗消耗 rng


def test_age_four_no_draw() -> None:
    db = _db()
    p0 = _player("P0", military_actions=3)
    state = _state(age=Age.IV, civil_deck=(), future_decks={},
                   players=(p0, _player("P1")),
                   military_deck=("mi0", "mi1"))
    new = turn.advance(state, db)
    assert new.players[0].hand_military == ()
    assert new.military_deck == ("mi0", "mi1")


# --- 时代切换军事堆更替 ------------------------------------------------------


def test_age_a_end_enables_age_one_military_deck() -> None:
    """时代 A 于第一次补牌时结束, 同时启用时代 I 军事堆."""
    db = _db()
    state = _state(
        round=1, age=Age.A, current_player=1,
        card_row=tuple(f"xa{i}" for i in range(ROW_SLOTS)),
        civil_deck=("xa13", "xa14", "xa15"),
        future_decks={
            "I": tuple(f"xi{i}" for i in range(20)),
            "II": tuple(f"xii{i}" for i in range(20)),
            "III": tuple(f"xiii{i}" for i in range(20)),
        },
        military_deck=(),
        future_military_decks={"I": ("mi0", "mi1", "mi2")},
    )
    new = turn.advance(state, db)
    assert new.age is Age.I
    assert new.military_deck == ("mi0", "mi1", "mi2")
    assert "I" not in new.future_military_decks


def test_age_transition_replaces_military_deck() -> None:
    """时代 I 结束: 旧军事牌堆余牌入 removed, 启用时代 II 军事堆."""
    db = _db()
    state = _state(
        current_player=1,
        civil_deck=("xi13", "xi14", "xi15"),  # 恰好补满 3 空位后牌堆尽
        military_deck=("mi8", "mi9"),
        military_discard=("mi7",),
        future_military_decks={"II": ("mii0", "mii1"), "III": ("miii0",)},
    )
    new = turn.advance(state, db)
    assert new.age is Age.II
    assert new.military_deck == ("mii0", "mii1")
    assert "II" not in new.future_military_decks
    assert "mi8" in new.removed
    assert "mi9" in new.removed
    # 军事弃牌堆按时代清空: 旧弃牌堆并入 removed, 不再参与重洗
    assert new.military_discard == ()
    assert "mi7" in new.removed


def test_age_transition_discard_excluded_from_reshuffle() -> None:
    """时代切换后: 旧时代军事弃牌堆不参与新时代牌堆的重洗."""
    db = _db()
    # 时代 II: 牌堆仅 1 张, 当前时代弃牌堆为空(旧时代弃牌堆已入 removed)
    p0 = _player("P0", military_actions=3)
    state = _state(age=Age.II,
                   players=(p0, _player("P1")),
                   military_deck=("mii0",), military_discard=(),
                   removed=("mi7", "mi6"))
    new = turn.advance(state, db)
    # 只抓到牌堆仅有的 1 张; 旧时代弃牌(mi6/mi7)不被重洗回牌堆
    assert new.players[0].hand_military == ("mii0",)
    assert new.military_deck == ()
    assert new.military_discard == ()
    # removed 新增部分仅为回合开始弃掉的牌列最左 3 张, 旧军事弃牌不动
    assert new.removed == ("mi7", "mi6", "xi0", "xi1", "xi2")
    assert new.rng_state == state.rng_state  # 未发生切洗


def test_enter_age_four_clears_military_discard() -> None:
    """时代 III 牌堆尽 -> 时代 IV: 军事牌堆余牌与军事弃牌堆均入 removed."""
    db = _db()
    state = _state(
        round=3,
        age=Age.III,
        card_row=("xiii0",) + (None,) * (ROW_SLOTS - 1),
        civil_deck=("xiii1",),
        future_decks={},
        military_deck=("miii8",),
        military_discard=("miii7",),
    )
    new = turn.advance(state, db)
    assert new.age is Age.IV
    assert new.military_deck == ()
    assert new.military_discard == ()
    assert "miii8" in new.removed
    assert "miii7" in new.removed


# --- 回合末弃多余军事牌(discard_military pending) ---------------------------


def test_discard_excess_pending_flow() -> None:
    """手牌 4 > 上限 2 -> pending count=2; 弃牌结算完毕才生产/推进."""
    db = _db()
    p0 = _player("P0", military_actions=0,
                 hand_military=("mi0", "mi1", "mi2", "mi3"))
    state = _state(players=(p0, _player("P1")),
                   military_deck=("mi4", "mi5"))
    new = turn.advance(state, db)
    # 官方顺序(规则书 p6): 弃置多余的军事牌 -> 起义检定 -> 生产 -> 抓取
    # 军事牌。阶段 1 压入 pending 即停: 抓牌与推进均未发生,
    # current_player/round/age/牌列/牌堆全部保持
    assert new.current_player == 0
    assert new.round == state.round
    assert new.age is state.age
    assert new.card_row == state.card_row
    assert new.civil_deck == state.civil_deck
    assert new.military_deck == ("mi4", "mi5")  # 抓牌尚未发生
    assert new.players[0].hand_military == ("mi0", "mi1", "mi2", "mi3")
    assert new.removed == ()
    assert new.phase is Phase.TURN_START
    # pending 由刚结束回合的 P0 响应, context 带续跑标记
    assert len(new.pending) == 1
    pending = new.pending[0]
    assert pending.kind == "discard_military"
    assert pending.responder == 0
    assert pending.context == {"count": 2, "resume": "end_of_turn_production"}
    # 法律: 仅 DiscardMilitary(强制弃牌, 响应期无 PassTurn 兜底)
    legal = legal_actions(db, new)
    assert legal
    assert all(isinstance(a, DiscardMilitary) for a in legal)
    assert PassTurn() not in legal
    assert {a.card_id for a in legal} == {"mi0", "mi1", "mi2", "mi3"}
    # 弃 1 张: 入军事弃牌堆, count 递减, 仍不推进不抓牌
    new = apply(new, DiscardMilitary("mi1"), db)
    assert new.players[0].hand_military == ("mi0", "mi2", "mi3")
    assert new.military_discard == ("mi1",)
    assert new.current_player == 0
    assert new.card_row == state.card_row
    assert new.military_deck == ("mi4", "mi5")
    assert len(new.pending) == 1
    assert new.pending[0].context["count"] == 1
    # 再弃 1 张: 合规, pending pop -> 续跑阶段 2(0 红点不抓牌) -> 推进,
    # 下一位回合开始此刻才发生
    new = apply(new, DiscardMilitary("mi0"), db)
    assert new.pending == ()
    assert new.players[0].hand_military == ("mi2", "mi3")
    assert new.military_discard == ("mi1", "mi0")
    assert new.military_deck == ("mi4", "mi5")
    assert new.current_player == 1
    assert new.phase is Phase.POLITICS
    # 下一位回合开始恰执行一次: 弃最左 3 张入 removed, 左移后补 3 张
    assert new.removed == ("xi0", "xi1", "xi2")
    assert new.card_row == tuple(f"xi{i}" for i in range(3, 16))
    assert new.civil_deck == ("xi16", "xi17", "xi18", "xi19")
    # 政治阶段: 无军事手牌可打出时仅剩 Resign(时代 IV 外恒可退出, P2-T10)
    assert legal_actions(db, new) == [Resign(), SkipPolitics()]


def test_discard_settles_before_military_draw() -> None:
    """弃牌先于抓牌(官方顺序): 响应者手牌不含新抓牌, 只能弃原有手牌."""
    db = _db()
    # 上限 2, 手牌 3 -> 超 1; 剩余红点 2 -> 弃牌后抓 2 张
    p0 = _player("P0", military_actions=2,
                 hand_military=("mi0", "mi1", "mi2"))
    state = _state(players=(p0, _player("P1")),
                   military_deck=("mi3", "mi4", "mi5"))
    new = turn.advance(state, db)
    # 阶段 1 压 pending 即停: 抓牌未发生, 响应者手牌 = 原 3 张
    assert len(new.pending) == 1
    assert new.pending[0].context == {"count": 1,
                                      "resume": "end_of_turn_production"}
    assert new.players[0].hand_military == ("mi0", "mi1", "mi2")
    assert new.military_deck == ("mi3", "mi4", "mi5")
    # 响应期只能弃原有手牌(新抓的 mi3/mi4 不在候选)
    legal = legal_actions(db, new)
    assert {a.card_id for a in legal} == {"mi0", "mi1", "mi2"}
    # 弃 1 张合规 -> 续跑阶段 2: 抓 2 张(剩余红点 2), 恢复行动点, 推进
    new = apply(new, DiscardMilitary("mi1"), db)
    assert new.pending == ()
    assert new.players[0].hand_military == ("mi0", "mi2", "mi3", "mi4")
    assert new.military_deck == ("mi5",)
    assert new.military_discard == ("mi1",)
    # 抓牌后手牌 4 > 上限 2: 官方口径不再检查(下次弃牌检查在该玩家
    # 下个回合末), 无新 pending, 直接推进
    assert new.current_player == 1
    assert new.phase is Phase.POLITICS
    assert new.players[0].military_actions == 2  # 已恢复为 civ 总值


def test_resume_production_runs_exactly_once() -> None:
    """续跑不重复阶段: 腐败/生产仅在弃牌结算后执行一次(弃牌时不执行)."""
    db = _db()
    # blue_bank=4 -> 腐败 4; bronze 5 蓝点付 4 余 1; 资源生产再取 1 蓝点
    p0 = _player("P0", military_actions=0, blue_bank=4,
                 hand_military=("mi0", "mi1", "mi2"),
                 card_tokens={"bronze": 5},
                 buildings={"mine": {"bronze": 1}})
    state = _state(players=(p0, _player("P1")))
    new = turn.advance(state, db)
    # 阶段 1 压 pending 即停: 腐败/生产/恢复均尚未发生
    assert len(new.pending) == 1
    assert new.players[0].card_tokens == {"bronze": 5}
    assert new.players[0].blue_bank == 4
    assert new.players[0].civil_actions == 0
    # 弃 1 张合规 -> 阶段 2 恰执行一次: 腐败付 4(蓝点回供给区 4+4=8),
    # 资源生产 bronze 1 工人从供给区取 1(8-1=7), 行动点恢复, 推进
    new = apply(new, DiscardMilitary("mi2"), db)
    q = new.players[0]
    assert new.pending == ()
    assert q.card_tokens == {"bronze": 2}
    assert q.blue_bank == 7
    assert q.civil_actions == 4
    assert q.military_actions == 2
    assert new.current_player == 1


def test_uprising_with_excess_discard() -> None:
    """超限 + 起义组合: 先弃牌, 起义检定弃牌后执行, 生产跳过但抓牌照行."""
    db = _db()
    # yellow_bank=10 -> 幸福需求 4, 不满 4 > 空闲工人 1 -> 起义
    p0 = _player("P0", military_actions=1, yellow_bank=10, science=3,
                 hand_military=("mi0", "mi1", "mi2"))
    state = _state(players=(p0, _player("P1")),
                   military_deck=("mi3", "mi4"))
    new = turn.advance(state, db)
    # 弃牌 pending 先压入, 起义检定/抓牌尚未发生
    assert len(new.pending) == 1
    assert new.players[0].hand_military == ("mi0", "mi1", "mi2")
    assert new.military_deck == ("mi3", "mi4")
    # 弃 1 张合规 -> 阶段 2: 起义跳过生产(科技不变), 抓 1 张, 恢复行动点
    new = apply(new, DiscardMilitary("mi0"), db)
    q = new.players[0]
    assert new.pending == ()
    assert q.science == 3
    assert q.hand_military == ("mi1", "mi2", "mi3")
    assert new.military_deck == ("mi4",)
    assert q.civil_actions == 4
    assert q.military_actions == 2
    assert new.current_player == 1


def test_discard_military_not_in_hand_illegal() -> None:
    db = _db()
    p0 = _player("P0", military_actions=0, hand_military=("mi0", "mi1", "mi2"))
    state = _state(players=(p0, _player("P1")))
    new = turn.advance(state, db)
    assert len(new.pending) == 1
    with pytest.raises(IllegalActionError):
        apply(new, DiscardMilitary("mi9"), db)


def test_hand_limit_includes_military_hand_extra() -> None:
    """军事手牌上限 = 军事行动点 + military_hand_extra(奇迹加成)."""
    db = _db()
    p0 = _player("P0", military_actions=0,
                 hand_military=("mi0", "mi1", "mi2"),
                 wonders=("great_library",))
    state = _state(players=(p0, _player("P1")))
    new = turn.advance(state, db)
    # 上限 = 2(专制) + 1(奇迹) = 3, 手牌 3 不超
    assert new.pending == ()
    assert new.players[0].hand_military == ("mi0", "mi1", "mi2")


def test_discard_military_action_serialization() -> None:
    action = DiscardMilitary("mi0")
    assert action_to_dict(action) == {"type": "discard_military",
                                      "card_id": "mi0"}
    assert action_from_dict(action_to_dict(action)) == action
