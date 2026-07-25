"""官方回合状态机测试(见 tta/engine/turn.py 模块 docstring)."""

import pytest

from tta.engine import turn
from tta.engine.actions import IllegalActionError, PassTurn
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import ROW_SLOTS, GameState, PendingEffect, PlayerState


def _card(card_id: str, category: CardCategory, age: Age = Age.A,
          **overrides: object) -> CardDefinition:
    base: dict = {
        "id": card_id,
        "name": card_id,
        "name_en": card_id,
        "age": age,
        "deck": DeckType.CIVIL,
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
        "irrigation": _card(
            "irrigation", CardCategory.FARM, Age.I, token_value=2),
        "bronze": _card("bronze", CardCategory.MINE, token_value=1),
        "iron": _card("iron", CardCategory.MINE, Age.I, token_value=2),
        "philosophy": _card(
            "philosophy", CardCategory.LAB, urban_produces={"science": 1}),
        "religion": _card(
            "religion", CardCategory.TEMPLE,
            urban_produces={"happiness": 1, "culture": 1}),
        "leader_a": _card("leader_a", CardCategory.LEADER),
        "leader_i": _card("leader_i", CardCategory.LEADER, Age.I),
        "wonder_a": _card("wonder_a", CardCategory.WONDER,
                          wonder_stages=(3, 2)),
        "wonder_i": _card("wonder_i", CardCategory.WONDER, Age.I,
                          wonder_stages=(2,)),
    }
    # 牌列/牌堆填充卡(行动卡, 无数值); 每时代 20 张
    for age, prefix in ((Age.A, "xa"), (Age.I, "xi"),
                        (Age.II, "xii"), (Age.III, "xiii")):
        for i in range(20):
            card_id = f"{prefix}{i}"
            cards[card_id] = _card(card_id, CardCategory.ACTION, age)
    return CardDB(cards=cards, initial_tableau=("agriculture", "bronze"),
                  initial_government="despotism")


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {"name": name}
    base.update(overrides)
    return PlayerState(**base)


def _state(**overrides: object) -> GameState:
    base: dict = {
        "round": 1,
        "age": Age.A,
        "current_player": 0,
        "card_row": (None,) * ROW_SLOTS,
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (_player("P0"), _player("P1")),
        "rng_state": 0,
    }
    base.update(overrides)
    return GameState(**base)


def _full_row(prefix: str) -> tuple[str, ...]:
    return tuple(f"{prefix}{i}" for i in range(ROW_SLOTS))


# --- 回合末阶段 -----------------------------------------------------------


def test_end_of_turn_scores_rates_and_restores_actions() -> None:
    p0 = _player(
        "P0",
        science=3,
        culture=2,
        civil_actions=0,
        military_actions=0,
        turn_discounts={"unit_build": 2},
        buildings={"lab": {"philosophy": 1}, "temple": {"religion": 1}},
    )
    state = _state(players=(p0, _player("P1")))
    new = turn.advance(state, _db())
    q = new.players[0]
    # 增速计分: science +1(哲学), culture +1(宗教)
    assert q.science == 4
    assert q.culture == 3
    # 行动点恢复为 civ 总值(专制 4 白 2 红), 回合折扣清空
    assert q.civil_actions == 4
    assert q.military_actions == 2
    assert q.turn_discounts == {}
    # 入参不被改动
    assert state.players[0].civil_actions == 0


def test_corruption_paid_resource_then_food() -> None:
    # blue_bank=4 -> 腐败 4; 资源仅 3(bronze×3), 差值 1 由食物(agriculture)补
    p0 = _player(
        "P0",
        blue_bank=4,
        card_tokens={"bronze": 3, "agriculture": 2},
        buildings={"mine": {"bronze": 1}},
    )
    new = turn.advance(_state(players=(p0, _player("P1"))), _db())
    q = new.players[0]
    # bronze 3 点全部付腐败, agriculture 付 1; 支付蓝点放回供给区
    # (4+3+1=8), 资源生产 bronze 1 工人从供给区取 1 蓝点 (8-1=7)
    assert q.card_tokens == {"agriculture": 1, "bronze": 1}
    assert q.blue_bank == 7


def test_corruption_unpayable_loss_capped_no_negative() -> None:
    # blue_bank=0 -> 腐败 6; 无任何蓝点 -> 损失到此为止, 不产生负值不抛错
    p0 = _player("P0", blue_bank=0, card_tokens={}, buildings={})
    new = turn.advance(_state(players=(p0, _player("P1"))), _db())
    q = new.players[0]
    assert q.card_tokens == {}
    assert q.blue_bank == 0


def test_consumption_shortage_costs_four_culture_each() -> None:
    # yellow_bank=17 -> 消耗 1; 无食物 -> 缺 1 -> 文化 10 - 4
    p0 = _player("P0", yellow_bank=17, culture=10, card_tokens={})
    new = turn.advance(_state(players=(p0, _player("P1"))), _db())
    assert new.players[0].culture == 6


def test_consumption_shortage_culture_floor_zero() -> None:
    p0 = _player("P0", yellow_bank=17, culture=3, card_tokens={})
    new = turn.advance(_state(players=(p0, _player("P1"))), _db())
    assert new.players[0].culture == 0


def test_uprising_skips_production_but_restores_actions() -> None:
    # yellow_bank=10 -> 幸福需求 4, 不满 4 > 空闲工人 1 -> 起义
    p0 = _player(
        "P0",
        yellow_bank=10,
        blue_bank=4,
        science=3,
        culture=2,
        civil_actions=0,
        military_actions=0,
        card_tokens={"bronze": 2},
        buildings={"lab": {"philosophy": 1}, "mine": {"bronze": 1}},
    )
    new = turn.advance(_state(players=(p0, _player("P1"))), _db())
    q = new.players[0]
    # 生产整体跳过: 不计分/不腐败/不生产
    assert q.science == 3
    assert q.culture == 2
    assert q.card_tokens == {"bronze": 2}
    assert q.blue_bank == 4
    # 行动点仍恢复
    assert q.civil_actions == 4
    assert q.military_actions == 2


# --- 回合开始: 弃牌/补牌 ---------------------------------------------------


def test_first_round_skips_refill() -> None:
    row = ("xa0", "xa1") + (None,) * (ROW_SLOTS - 2)
    state = _state(round=1, current_player=0, card_row=row,
                   civil_deck=("xa5", "xa6"))
    new = turn.advance(state, _db())
    assert new.round == 1
    assert new.current_player == 1
    assert new.card_row == row
    assert new.civil_deck == ("xa5", "xa6")
    assert new.removed == ()


def test_two_players_discard_three_slide_and_refill() -> None:
    state = _state(
        round=2,
        age=Age.I,
        current_player=0,
        card_row=_full_row("xi"),
        civil_deck=("xi13", "xi14", "xi15", "xi16"),
    )
    new = turn.advance(state, _db())
    # 弃最左 3 个位置的牌入 removed, 其余左移, 右侧从牌堆顶依次补满
    assert new.removed == ("xi0", "xi1", "xi2")
    assert new.card_row == tuple(f"xi{i}" for i in range(3, 16))
    assert new.civil_deck == ("xi16",)
    assert new.current_player == 1
    assert new.round == 2
    assert new.age is Age.I


def test_age_a_ends_at_first_refill() -> None:
    # 起始玩家第二回合开始: 弃 3 -> 左移 -> A 堆补 3 空位 -> A 堆余牌入
    # removed -> 启用 I 堆; 官方规则: 时代 A 结束 nothing else happens,
    # 无过期, 也不扣黄点(yellow_bank 不变)
    state = _state(
        round=1,
        age=Age.A,
        current_player=1,
        card_row=_full_row("xa"),
        civil_deck=("xa13", "xa14", "xa15", "xa16", "xa17"),
        future_decks={"I": ("xi0", "xi1", "xi2")},
    )
    new = turn.advance(state, _db())
    assert new.round == 2
    assert new.current_player == 0
    assert new.age is Age.I
    assert new.card_row == tuple(f"xa{i}" for i in range(3, 16))
    assert new.removed == ("xa0", "xa1", "xa2", "xa16", "xa17")
    assert new.civil_deck == ("xi0", "xi1", "xi2")
    assert new.future_decks == {}
    assert [p.yellow_bank for p in new.players] == [18, 18]


def test_age_a_end_deck_exhausted_continues_with_age_i() -> None:
    # A 堆仅 2 张: 补完 2 个空位后启用 I 堆继续补第 3 个空位
    state = _state(
        round=1,
        age=Age.A,
        current_player=1,
        card_row=_full_row("xa"),
        civil_deck=("xa13", "xa14"),
        future_decks={"I": ("xi0", "xi1", "xi2")},
    )
    new = turn.advance(state, _db())
    assert new.age is Age.I
    assert new.card_row == tuple(f"xa{i}" for i in range(3, 15)) + ("xi0",)
    assert new.civil_deck == ("xi1", "xi2")
    assert new.removed == ("xa0", "xa1", "xa2")


def test_age_i_end_obsolescence_and_yellow_loss() -> None:
    # I 堆最后一张放上牌列 -> 时代 I 结束: 过期处理 + 每人 -2 黄点 + 启用 II 堆
    p1 = _player(
        "P1",
        hand_civil=("xa19", "xi19"),
        leader="leader_a",
        leader_ages=("A",),
        wonder_progress=("wonder_a", 1),
        blue_bank=10,
    )
    p0 = _player("P0", developed=("philosophy",))
    state = _state(
        round=2,
        age=Age.I,
        current_player=0,
        players=(p0, p1),
        card_row=_full_row("xi"),
        civil_deck=("xi13",),
        future_decks={"II": ("xii0", "xii1", "xii2")},
    )
    new = turn.advance(state, _db())
    assert new.age is Age.II
    # 补牌: xi13 放上后 I 堆尽 -> 时代结束 -> II 堆继续补 2 空位
    assert new.card_row == tuple(f"xi{i}" for i in range(3, 13)) + (
        "xi13", "xii0", "xii1")
    assert new.civil_deck == ("xii2",)
    # 过期手牌(时代 A)入弃牌堆, 时代 I 手牌保留
    q = new.players[1]
    assert q.hand_civil == ("xi19",)
    assert new.discard == ("xa19",)
    # 过期领袖入 removed 并清 None, leader_ages 保留
    assert q.leader is None
    assert q.leader_ages == ("A",)
    # 过期未完成奇迹: 已付 1 阶段蓝点退回 blue_bank, 奇迹入 removed
    assert q.wonder_progress is None
    assert q.blue_bank == 11
    assert new.removed == ("xi0", "xi1", "xi2", "leader_a", "wonder_a")
    # 每人 -2 黄点
    assert [p.yellow_bank for p in new.players] == [16, 16]
    # 已研发科技不受影响
    assert new.players[0].developed == ("philosophy",)


def test_age_end_yellow_loss_floor_zero() -> None:
    p0 = _player("P0", yellow_bank=1)
    p1 = _player("P1", yellow_bank=18)
    state = _state(
        round=2,
        age=Age.I,
        current_player=0,
        players=(p0, p1),
        card_row=_full_row("xi"),
        civil_deck=("xi13",),
        future_decks={"II": ("xii0", "xii1", "xii2")},
    )
    new = turn.advance(state, _db())
    assert [p.yellow_bank for p in new.players] == [0, 16]


# --- 时代 IV 与终局 --------------------------------------------------------


def _age_three_refill_state(current: int) -> GameState:
    row = ("xiii0",) + (None,) * (ROW_SLOTS - 1)
    return _state(
        round=3,
        age=Age.III,
        current_player=current,
        players=(_player("P0", culture=5), _player("P1", culture=7)),
        card_row=row,
        civil_deck=("xiii1",),
    )


def test_age_iv_opened_at_start_player_turn_makes_this_round_last() -> None:
    # 起始玩家(0 号位)回合开启 IV -> 本轮即最后一轮
    new = turn.advance(_age_three_refill_state(current=1), _db())
    assert new.age is Age.IV
    assert new.last_round is True
    assert new.round == 4
    assert new.current_player == 0
    assert new.civil_deck == ()
    assert new.terminal is False
    # 时代 IV 的回合开始: 仍弃最左 N 张并左移(仅剩 1 张被弃), 但不补牌
    new = turn.advance(new, _db())
    assert new.terminal is False
    assert new.round == 4
    assert new.current_player == 1
    assert new.card_row == (None,) * ROW_SLOTS
    # 最后一轮结束 -> 终局, final_scores = 各玩家文化
    new = turn.advance(new, _db())
    assert new.terminal is True
    assert new.final_scores == (5, 7)


def test_age_iv_opened_at_other_player_turn_makes_next_round_last() -> None:
    # 非起始玩家(1 号位)回合开启 IV -> 下一轮为最后一轮
    new = turn.advance(_age_three_refill_state(current=0), _db())
    assert new.age is Age.IV
    assert new.last_round is False
    assert new.round == 3
    assert new.current_player == 1
    # 1 号位回合结束 -> 轮次递增, 开启最后一轮
    new = turn.advance(new, _db())
    assert new.terminal is False
    assert new.round == 4
    assert new.last_round is True
    assert new.current_player == 0
    # 最后一轮两位玩家依次行动
    new = turn.advance(new, _db())
    assert new.terminal is False
    assert new.current_player == 1
    new = turn.advance(new, _db())
    assert new.terminal is True
    assert new.final_scores == (5, 7)


def test_age_four_discards_left_cards_but_never_refills() -> None:
    # 时代 IV 无牌堆: 回合开始仍弃最左 N 张并左移, 右侧空位保持空,
    # 卡牌列逐回合缩短
    row = ("xiii5", "xiii6", "xiii7", "xiii8") + (None,) * (ROW_SLOTS - 4)
    state = _state(
        round=3,
        age=Age.IV,
        current_player=0,
        card_row=row,
        civil_deck=(),
    )
    new = turn.advance(state, _db())
    # 2 人局弃最左 3 个位置的牌入 removed, 其余左移, 不补牌
    assert new.removed == ("xiii5", "xiii6", "xiii7")
    assert new.card_row == ("xiii8",) + (None,) * (ROW_SLOTS - 1)
    assert new.civil_deck == ()
    # 下一回合开始: 再弃 3 个位置(仅剩 xiii8), 牌列清空
    new = turn.advance(new, _db())
    assert new.removed == ("xiii5", "xiii6", "xiii7", "xiii8")
    assert new.card_row == (None,) * ROW_SLOTS


# --- PassTurn 接入 ---------------------------------------------------------


def test_apply_pass_turn_discards_pending_and_advances() -> None:
    state = _state(
        round=1,
        current_player=0,
        pending=(PendingEffect(kind="build_farm_mine", discount=1),),
    )
    new = apply(state, PassTurn(), _db())
    assert new.pending == ()
    assert new.current_player == 1


def test_apply_pass_turn_advances_without_pending() -> None:
    new = apply(_state(round=1, current_player=0), PassTurn(), _db())
    assert new.current_player == 1


def test_apply_pass_turn_on_terminal_raises() -> None:
    state = _state(terminal=True, final_scores=(5, 7))
    with pytest.raises(IllegalActionError, match="已结束"):
        apply(state, PassTurn(), _db())
