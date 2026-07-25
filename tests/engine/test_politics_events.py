"""政治阶段框架 + 事件机制测试(P2-T5).

覆盖: 新动作序列化、POLITICS 相位 legal(SeedEvent + SkipPolitics, 每回合
限 1 政治行动)、SeedEvent 结算(军事手牌 -> future_events 顶 -> 揭示
current_events 顶 -> handler 结算 -> past_events -> 当前堆尽重洗
future_events)、未注册事件 fail-loud(Age A)/过场(后续时代, TODO
T6/T11/T12)、TERRITORY 触发殖民竞拍(T7, 详见 test_colonization.py)、
DeclineResponse 白名单兜底、Age A 全 10 事件 handler、事件 pending 链多
玩家轮转。
"""

from dataclasses import replace

import pytest

from tta.cards import build_card_db
from tta.engine import events
from tta.engine.actions import (
    Build,
    CancelPact,
    ChooseEventOption,
    DeclareWar,
    DeclineResponse,
    DevelopTech,
    DiscardMilitary,
    IllegalActionError,
    PassTurn,
    PlayAggression,
    ProposePact,
    Resign,
    SeedEvent,
    SkipPolitics,
    action_from_dict,
    action_to_dict,
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
        "age": Age.A,
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


def _db_with_fake_event() -> CardDB:
    """完整牌库 + 一张未注册 handler 的 Age A 测试事件卡."""
    db = build_card_db()
    fake = CardDefinition(
        id="fake_event_a", name="假事件", name_en="Fake Event", age=Age.A,
        deck=DeckType.MILITARY, category=CardCategory.EVENT,
        text="测试桩。", handler="fake_event_a", quantities=(0, 0, 0),
    )
    return CardDB(
        cards={**db.cards, fake.id: fake},
        initial_tableau=db.initial_tableau,
        initial_government=db.initial_government,
        initial_workers=db.initial_workers,
    )


# --- 新动作序列化 ------------------------------------------------------------


def test_new_actions_serialization_roundtrip() -> None:
    actions = [
        DeclineResponse(),
        SeedEvent("development_of_crafts"),
        PlayAggression("raid_i", 2),
        DeclareWar("war_over_culture_iii", 1),
        ProposePact("peace_treaty", 3),
        CancelPact("peace_treaty"),
        Resign(),
        ChooseEventOption("food"),
    ]
    for action in actions:
        assert action_from_dict(action_to_dict(action)) == action


def test_t8_t9_t10_actions_not_yet_legal() -> None:
    # 侵略/战争/条约需手牌支撑, 空手时不可打出; 2 人局无条约动作(T10);
    # Resign 无需手牌(时代 IV 外恒合法, P2-T10 起合法, 见 test_pacts.py)
    db = build_card_db()
    state = _state()
    legal = legal_actions(db, state)
    for action in (
        PlayAggression("raid_i", 1), DeclareWar("war_over_culture_iii", 1),
        ProposePact("peace_treaty", 1), CancelPact("peace_treaty"),
    ):
        assert action not in legal
        with pytest.raises(IllegalActionError):
            apply(state, action, db)


# --- POLITICS 相位 legal ------------------------------------------------------


def test_politics_legal_seed_event_plus_skip() -> None:
    db = build_card_db()
    p0 = _player(
        "P0", hand_military=("development_of_crafts", "fighting_band"))
    state = _state(players=(p0, _player("P1")))
    legal = legal_actions(db, state)
    # 军事手牌中的 EVENT 卡可筹划; 阵型牌不是政治动作
    assert SeedEvent("development_of_crafts") in legal
    assert legal[-1] == SkipPolitics()
    assert all(
        not isinstance(a, SeedEvent) or a.card_id == "development_of_crafts"
        for a in legal
    )


def test_politics_legal_without_event_cards_is_only_skip() -> None:
    # 无可打出军事牌时, 政治动作仅剩 Resign(时代 IV 外恒可退出, P2-T10)
    db = build_card_db()
    p0 = _player("P0", hand_military=("fighting_band",))
    state = _state(players=(p0, _player("P1")))
    assert legal_actions(db, state) == [Resign(), SkipPolitics()]


def test_politics_action_limited_to_one_per_turn() -> None:
    # 任一政治动作结算后 -> ACTION 相位(每回合限 1 政治行动)
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(players=(p0, _player("P1")), current_events=())
    new = apply(state, SeedEvent("development_of_crafts"), db)
    assert new.phase is Phase.ACTION
    legal = legal_actions(db, new)
    assert SkipPolitics() not in legal
    assert not any(isinstance(a, SeedEvent) for a in legal)


def test_age_iv_seed_event_allowed() -> None:
    # RULES-CHECK(规则书 p4 未禁止): 时代 IV 无军事牌可抽, 但手牌中已有的
    # 事件牌仍可筹划
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(players=(p0, _player("P1")), age=Age.IV, current_events=())
    assert SeedEvent("development_of_crafts") in legal_actions(db, state)


# --- SeedEvent 结算流程 --------------------------------------------------------


def test_seed_event_moves_card_and_reveals_to_past() -> None:
    db = build_card_db()
    p0 = _player(
        "P0", hand_military=("development_of_science", "fighting_band"))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_crafts", "development_of_science"),
    )
    new = apply(state, SeedEvent("development_of_science"), db)
    # 筹划卡: 军事手牌 -> future_events 顶(暗置)
    assert new.players[0].hand_military == ("fighting_band",)
    assert new.future_events[0] == "development_of_science"
    # 揭示 current_events 顶 -> 结算 -> past_events; 非最后一张不重洗
    assert new.past_events == ("development_of_crafts",)
    assert new.current_events == ("development_of_science",)
    # development_of_crafts: 全场 resource+2(蓝点入最低级矿场 bronze)
    for p in new.players:
        assert p.card_tokens.get("bronze") == 2
        assert p.blue_bank == 14
    assert new.phase is Phase.ACTION


def test_seed_event_empty_current_nothing_happens() -> None:
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(players=(p0, _player("P1")), current_events=())
    new = apply(state, SeedEvent("development_of_crafts"), db)
    assert new.future_events == ("development_of_crafts",)
    assert new.past_events == ()
    assert new.phase is Phase.ACTION


def test_seed_event_last_reveal_reshuffles_future_by_age() -> None:
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_science",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_crafts",),
        # future 顶先压入筹划的 Age A 卡; 已有 Age II 与另一张 Age A 在下
        future_events=("cold_war", "development_of_settlement"),
    )
    new = apply(state, SeedEvent("development_of_science"), db)
    # 揭示最后一张 -> 重洗 future 成为新 current: 按时代分组, 早时代在上
    assert new.future_events == ()
    assert len(new.current_events) == 3
    assert {db.get(c).age for c in new.current_events[:2]} == {Age.A}
    assert db.get(new.current_events[2]).age is Age.II
    # Age A 组内 2 张经 rng_shuffle(消费 rng_state)
    assert new.rng_state != state.rng_state
    assert new.past_events == ("development_of_crafts",)


def test_seed_event_territory_starts_colonize_bid() -> None:
    # TERRITORY 揭示 -> 触发殖民竞拍(P2-T7, 详见 test_colonization.py):
    # 地区牌暂不入 past_events, 压入 colonize_bid pending
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("developed_territory_i", "development_of_science"),
    )
    new = apply(state, SeedEvent("development_of_crafts"), db)
    assert new.past_events == ()
    assert new.current_events == ("development_of_science",)
    assert len(new.pending) == 1
    assert new.pending[0].kind == "colonize_bid"
    assert new.pending[0].context["territory"] == "developed_territory_i"


def test_seed_event_unregistered_age_a_event_fails_loud() -> None:
    # fail-loud: Age A 事件未注册 handler -> ValueError(T5 拥有 Age A 全量)
    db = _db_with_fake_event()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("fake_event_a", "development_of_science"),
    )
    with pytest.raises(ValueError, match="fake_event_a"):
        apply(state, SeedEvent("development_of_crafts"), db)


def test_seed_event_unregistered_later_age_passes_through() -> None:
    # TODO(T11/T12): 时代 II/III 事件 handler 未注册前, 揭示为无效果
    # 过场(不阻塞对局), 直接入 past_events; 注册后该兜底移除
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("cold_war", "development_of_science"),
    )
    new = apply(state, SeedEvent("development_of_crafts"), db)
    assert new.past_events == ("cold_war",)


def test_event_handlers_registry_stub() -> None:
    # 注册表机制验证: 2 个测试桩 handler 注册后被调用, 用后清理
    db = _db_with_fake_event()
    calls: list[str] = []

    def _stub(state: GameState, db: CardDB) -> GameState:
        calls.append("stub")
        return state

    events.EVENT_HANDLERS["fake_event_a"] = _stub
    events.EVENT_HANDLERS["fake_event_b"] = _stub
    try:
        p0 = _player("P0", hand_military=("development_of_crafts",))
        state = _state(
            players=(p0, _player("P1")),
            current_events=("fake_event_a", "development_of_science"),
        )
        new = apply(state, SeedEvent("development_of_crafts"), db)
        assert calls == ["stub"]
        assert new.past_events == ("fake_event_a",)
    finally:
        del events.EVENT_HANDLERS["fake_event_a"]
        del events.EVENT_HANDLERS["fake_event_b"]


# --- DeclineResponse 兜底(T1 审查交接) ----------------------------------------


def test_decline_response_offered_for_declinable_pending() -> None:
    db = build_card_db()
    p0 = _player("P0")
    state = _state(
        players=(p0, _player("P1")),
        phase=Phase.ACTION,
        pending=(PendingEffect("build_farm_mine", 3),),
    )
    legal = legal_actions(db, state)
    assert DeclineResponse() in legal
    new = apply(state, DeclineResponse(), db)
    assert new.pending == ()


def test_decline_response_pops_only_first_pending() -> None:
    db = build_card_db()
    state = _state(
        phase=Phase.ACTION,
        pending=(
            PendingEffect("build_farm_mine", 3),
            PendingEffect("build_urban", 1),
        ),
    )
    new = apply(state, DeclineResponse(), db)
    assert new.pending == (PendingEffect("build_urban", 1),)


def test_decline_response_not_offered_for_discard_military() -> None:
    # 强制类 pending(discard_military)不可放弃: 恒有 DiscardMilitary 可执行
    db = build_card_db()
    p0 = _player("P0", hand_military=("fighting_band",))
    state = _state(
        players=(p0, _player("P1")),
        phase=Phase.TURN_START,
        pending=(PendingEffect(
            "discard_military", 0, responder=0, context={"count": 1}),),
    )
    legal = legal_actions(db, state)
    assert DiscardMilitary("fighting_band") in legal
    assert DeclineResponse() not in legal


def test_pass_turn_fallback_suppressed_with_foreign_pendings() -> None:
    # 事件 pending 链: 当前玩家的选择在上、他玩家选择在下时, 不提供
    # PassTurn 兜底(防止一次性丢弃他玩家的 pending), 但可 DeclineResponse
    db = build_card_db()
    state = _state(
        phase=Phase.ACTION,
        pending=(
            PendingEffect(events.KIND_EVENT_MARKETS, 0, responder=0),
            PendingEffect(events.KIND_EVENT_MARKETS, 0, responder=1),
        ),
    )
    legal = legal_actions(db, state)
    assert PassTurn() not in legal
    assert DeclineResponse() in legal
    assert ChooseEventOption("food") in legal


# --- Age A 事件 handler -------------------------------------------------------


def _reveal(db: CardDB, state: GameState) -> GameState:
    """当前玩家军事手牌置入一张筹划卡并打出 SeedEvent, 揭示 current_events 顶."""
    idx = state.current_player
    state = replace_player(state, idx, replace(
        state.players[idx], hand_military=("development_of_crafts",)))
    return apply(state, SeedEvent("development_of_crafts"), db)


def test_event_agriculture_all_food_plus_2() -> None:
    db = build_card_db()
    state = _state(current_events=(
        "development_of_agriculture", "development_of_science"))
    new = _reveal(db, state)
    for p in new.players:
        assert p.card_tokens.get("agriculture") == 2
        assert p.blue_bank == 14


def test_event_crafts_all_resource_plus_2() -> None:
    db = build_card_db()
    state = _state(current_events=(
        "development_of_crafts", "development_of_science"))
    new = _reveal(db, state)
    for p in new.players:
        assert p.card_tokens.get("bronze") == 2


def test_event_science_all_science_plus_2() -> None:
    db = build_card_db()
    state = _state(current_events=(
        "development_of_science", "development_of_crafts"))
    new = _reveal(db, state)
    for p in new.players:
        assert p.science == 2


def test_event_trade_route_all_plus_1_each() -> None:
    db = build_card_db()
    state = _state(current_events=(
        "development_of_trade_route", "development_of_crafts"))
    new = _reveal(db, state)
    for p in new.players:
        assert p.science == 1
        assert p.card_tokens.get("agriculture") == 1
        assert p.card_tokens.get("bronze") == 1
        assert p.blue_bank == 14


def test_event_settlement_free_population() -> None:
    db = build_card_db()
    p1 = _player("P1", yellow_bank=0)
    state = _state(
        players=(_player("P0"), p1),
        current_events=("development_of_settlement", "development_of_crafts"),
    )
    new = _reveal(db, state)
    # yellow_bank > 0: 免费 +1 人口(银行 -1, 空闲工人 +1, 不付食物)
    assert new.players[0].yellow_bank == 17
    assert new.players[0].worker_pool == 2
    assert new.players[0].card_tokens == {}
    # yellow_bank = 0: 不生效
    assert new.players[1].yellow_bank == 0
    assert new.players[1].worker_pool == 1


def test_event_politics_all_draw_3_military() -> None:
    db = build_card_db()
    deck = tuple(f"mil{i}" for i in range(10))
    fake_cards = {
        card_id: CardDefinition(
            id=card_id, name=card_id, name_en=card_id, age=Age.I,
            deck=DeckType.MILITARY, category=CardCategory.BONUS,
            quantities=(0, 0, 0))
        for card_id in deck
    }
    db = CardDB(
        cards={**db.cards, **fake_cards},
        initial_tableau=db.initial_tableau,
        initial_government=db.initial_government,
        initial_workers=db.initial_workers,
    )
    state = _state(
        current_events=("development_of_politics", "development_of_crafts"),
        military_deck=deck,
    )
    new = _reveal(db, state)
    # 从 current_player 起顺时针各抓 3 张(共享军事牌堆)
    assert new.players[0].hand_military == deck[0:3]
    assert new.players[1].hand_military == deck[3:6]
    assert new.military_deck == deck[6:]


def test_event_markets_pending_chain_rotation() -> None:
    db = build_card_db()
    state = _state(
        num_players=3,
        current_player=1,
        current_events=("development_of_markets", "development_of_crafts"),
    )
    new = _reveal(db, state)
    # pending 链: 从 current_player(1 号位)起顺时针, responder = 座位号
    assert [e.responder for e in new.pending] == [1, 2, 0]
    assert all(e.kind == events.KIND_EVENT_MARKETS for e in new.pending)
    # 1 号位选 food
    new = apply(new, ChooseEventOption("food"), db)
    assert new.players[1].card_tokens.get("agriculture") == 2
    assert [e.responder for e in new.pending] == [2, 0]
    # 2 号位选 resource
    new = apply(new, ChooseEventOption("resource"), db)
    assert new.players[2].card_tokens.get("bronze") == 2
    assert [e.responder for e in new.pending] == [0]
    # 0 号位放弃(非强制选择)
    new = apply(new, DeclineResponse(), db)
    assert new.pending == ()
    assert new.players[0].card_tokens == {}
    assert new.phase is Phase.ACTION
    assert new.current_player == 1


def test_event_religion_free_build() -> None:
    db = build_card_db()
    p0 = _player("P0", worker_pool=1, card_tokens={"bronze": 5})
    p1 = _player("P1", worker_pool=0)  # 无可用工人 -> 不入链
    state = _state(
        players=(p0, p1),
        current_events=("development_of_religion", "development_of_crafts"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [0]
    assert new.pending[0].kind == events.KIND_EVENT_RELIGION
    legal = legal_actions(db, new)
    assert Build("religion") in legal
    assert DeclineResponse() in legal
    # 免费建: 不付资源, 不耗行动点, 工人从空闲池放上 religion
    new = apply(new, Build("religion"), db)
    assert new.pending == ()
    built = new.players[0]
    assert built.buildings["temple"] == {"religion": 1}
    assert built.worker_pool == 0
    assert built.card_tokens == {"bronze": 5}
    assert built.civil_actions == 0


def test_event_religion_decline() -> None:
    db = build_card_db()
    state = _state(
        players=(_player("P0"), _player("P1", worker_pool=0)),
        current_events=("development_of_religion", "development_of_crafts"),
    )
    new = _reveal(db, state)
    new = apply(new, DeclineResponse(), db)
    assert new.pending == ()
    assert "temple" not in new.players[0].buildings
    assert new.players[0].worker_pool == 1


def test_event_warfare_free_build() -> None:
    db = build_card_db()
    # warriors 空槽(初始 1 研发 0 工人)才有资格免费建
    p0 = _player("P0", worker_pool=1, buildings={
        "farm": {"agriculture": 2}, "mine": {"bronze": 2},
        "lab": {"philosophy": 1},
    })
    state = _state(
        players=(p0, _player("P1", worker_pool=0)),
        current_events=("development_of_warfare", "development_of_crafts"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [0]
    assert new.pending[0].kind == events.KIND_EVENT_WARFARE
    legal = legal_actions(db, new)
    assert Build("warriors") in legal
    new = apply(new, Build("warriors"), db)
    assert new.players[0].buildings["infantry"] == {"warriors": 1}
    assert new.players[0].worker_pool == 0


def test_event_civilization_farm_mine_option() -> None:
    db = build_card_db()
    # 额外 1 张 agriculture 研发(初始 2 研发 2 工人已满槽), 留出农场空槽
    p0 = _player("P0", worker_pool=1, card_tokens={"bronze": 2},
                 developed=_INITIAL_DEVELOPED + ("agriculture",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_civilization", "development_of_crafts"),
    )
    new = _reveal(db, state)
    assert [e.responder for e in new.pending] == [0, 1]
    legal = legal_actions(db, new)
    assert ChooseEventOption("farm_mine") in legal
    assert ChooseEventOption("urban") in legal
    assert DeclineResponse() in legal
    # 选 farm_mine -> 压入 build_farm_mine 折扣 1 子 pending(同座位)
    new = apply(new, ChooseEventOption("farm_mine"), db)
    assert new.pending[0].kind == "build_farm_mine"
    assert new.pending[0].discount == 1
    assert new.pending[0].responder == 0
    # 建 agriculture: 造价 2 - 折扣 1 = 付 1 资源, 0 行动点
    new = apply(new, Build("agriculture"), db)
    assert new.players[0].buildings["farm"] == {"agriculture": 3}
    assert new.players[0].card_tokens == {"bronze": 1}
    # 剩余 1 号位的选择 pending
    assert [e.responder for e in new.pending] == [1]


def test_event_civilization_tech_option_science_discount() -> None:
    db = build_card_db()
    # hand 中 iron(时代 I 矿场, 科技费 5); 科技 4 + 折扣 1 可研发
    p0 = _player("P0", science=4, hand_civil=("iron",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_civilization", "development_of_crafts"),
    )
    new = _reveal(db, state)
    legal = legal_actions(db, new)
    assert ChooseEventOption("tech") in legal
    new = apply(new, ChooseEventOption("tech"), db)
    assert new.pending[0].kind == "develop_tech"
    assert new.pending[0].discount == 1
    legal = legal_actions(db, new)
    assert DevelopTech("iron") in legal
    new = apply(new, DevelopTech("iron"), db)
    # 科技费 max(0, 5-1) = 4; 0 行动点
    assert new.players[0].science == 0
    assert "iron" in new.players[0].developed
    assert [e.responder for e in new.pending] == [1]


def test_event_civilization_tech_option_not_offered_when_unaffordable() -> None:
    db = build_card_db()
    p0 = _player("P0", science=3, hand_civil=("iron",))  # 5-1=4 > 3
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_civilization", "development_of_crafts"),
    )
    new = _reveal(db, state)
    legal = legal_actions(db, new)
    assert ChooseEventOption("tech") not in legal
    assert DeclineResponse() in legal


def test_event_civilization_population_option_settles() -> None:
    db = build_card_db()
    # 黄点 18 / 工人 1 / 食物 2(agriculture 上 2 蓝点)
    p0 = _player("P0", card_tokens={"agriculture": 2})
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_civilization", "development_of_crafts"),
    )
    new = _reveal(db, state)
    legal = legal_actions(db, new)
    assert ChooseEventOption("population") in legal
    # 选人口: 黄点 -1、工人 +1、食物 -1(事件固定价 1), 无子 pending
    new = apply(new, ChooseEventOption("population"), db)
    p = new.players[0]
    assert p.yellow_bank == 17
    assert p.worker_pool == 2
    assert p.card_tokens == {"agriculture": 1}
    assert p.blue_bank == 17  # 支付的蓝点放回供给区
    assert [e.responder for e in new.pending] == [1]
    assert new.pending[0].kind == events.KIND_EVENT_CIVILIZATION


def test_event_civilization_all_four_options_offered() -> None:
    db = build_card_db()
    # 人口(黄点+食物)、农场空槽、城市建筑资源、科技折扣研发 全部可行
    p0 = _player("P0", worker_pool=1, science=4, hand_civil=("iron",),
                 card_tokens={"agriculture": 1, "bronze": 2},
                 developed=_INITIAL_DEVELOPED + ("agriculture",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_civilization", "development_of_crafts"),
    )
    new = _reveal(db, state)
    legal = legal_actions(db, new)
    assert ChooseEventOption("population") in legal
    assert ChooseEventOption("farm_mine") in legal
    assert ChooseEventOption("urban") in legal
    assert ChooseEventOption("tech") in legal
    assert DeclineResponse() in legal


def test_event_civilization_population_not_offered_without_food() -> None:
    db = build_card_db()
    # 无食物(农场卡上无蓝点): 人口选项不出现, 其余选项照常
    p0 = _player("P0", worker_pool=1, card_tokens={"bronze": 2},
                 developed=_INITIAL_DEVELOPED + ("agriculture",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("development_of_civilization", "development_of_crafts"),
    )
    new = _reveal(db, state)
    legal = legal_actions(db, new)
    assert ChooseEventOption("population") not in legal
    assert ChooseEventOption("farm_mine") in legal
    assert DeclineResponse() in legal
