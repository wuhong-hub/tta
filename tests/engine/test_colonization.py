"""殖民竞拍与地区牌测试(P2-T7).

覆盖(规则书 p7 殖民 + 卡牌数值表 p4 Territory 行):
- 揭示 TERRITORY -> pending kind="colonize_bid"(responder 从揭示者起顺时针
  轮转; context: territory/current_bid/leader/bidders);
- ColonizeBid 必须高于当前出价且不超过可承诺殖民军力上限(= 全部军事单位
  军力含阵型 + 殖民修正 + 手中殖民奖励牌总值); 无军事单位者不可出价
  (规则: 必须挑出至少 1 个军事单位);
- ColonizePass 退出; 仅剩 leader 时胜出; 全员 pass -> 流拍入 past_events;
- 胜者牺牲结算 pending kind="colonize_sacrifice": ColonizeSacrifice(元组,
  legal 仅给"全选"锚点, apply 独立校验: 所选单位军力(按当前阵型组军) +
  殖民修正 + 已出奖励 >= 出价; 每单位 1 工人回黄点银行)与
  ColonizePlayBonus(手中军事奖励牌补足, 入军事弃牌堆);
- 获得殖民地: colonies 追加; 永久黄/蓝标记先入银行(可为即时效果提供标记,
  负值下限 0), 再结算即时效果(science/culture/food/materials/population/
  military_card); 永久效果(yellow_token/blue_token 除外)接入 civ 合成。
"""

from dataclasses import replace

import pytest

from tta.cards import build_card_db
from tta.engine import politics
from tta.engine.actions import (
    ColonizeBid,
    ColonizePass,
    ColonizePlayBonus,
    ColonizeSacrifice,
    IllegalActionError,
    SeedEvent,
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
        "phase": Phase.ACTION,
    }
    base.update(overrides)
    return GameState(**base)


def _bid_pending(
    *, territory: str = "developed_territory_i", current_bid: int = 0,
    leader: int = -1, bidders: tuple[int, ...] = (0, 1), responder: int = 0,
) -> PendingEffect:
    return PendingEffect(
        politics.KIND_COLONIZE_BID, 0, responder=responder,
        context={
            "territory": territory,
            "current_bid": current_bid,
            "leader": leader,
            "bidders": ",".join(str(s) for s in bidders),
        })


def _sacrifice_pending(
    *, territory: str = "developed_territory_i", bid: int = 1, bonus: int = 0,
    responder: int = 0,
) -> PendingEffect:
    return PendingEffect(
        politics.KIND_COLONIZE_SACRIFICE, 0, responder=responder,
        context={"territory": territory, "bid": bid, "bonus": bonus})


def _bid_state(**overrides: object) -> GameState:
    """2 人局 + colonize_bid pending(responder=0)的通用状态."""
    overrides.setdefault("pending", (_bid_pending(),))
    return _state(**overrides)


def _sacrifice_state(*, player: PlayerState | None = None,
                     pending_kwargs: dict | None = None,
                     **overrides: object) -> GameState:
    """2 人局 + colonize_sacrifice pending(responder=0)的通用状态."""
    overrides["pending"] = (_sacrifice_pending(**(pending_kwargs or {})),)
    if player is not None:
        overrides["players"] = (player, _player("P1"))
    return _state(**overrides)


# --- 动作序列化 ------------------------------------------------------------


def test_colonization_actions_serialization_roundtrip() -> None:
    actions = [
        ColonizeBid(3),
        ColonizePass(),
        ColonizePlayBonus("defense_colonization_i"),
        ColonizeSacrifice(("warriors", "warriors", "swordsmen")),
    ]
    for action in actions:
        assert action_from_dict(action_to_dict(action)) == action


def test_colonize_sacrifice_normalizes_units_to_tuple() -> None:
    # 反序列化产物(list)归一为 tuple, 保证可哈希与相等性
    action = action_from_dict(
        {"type": "colonize_sacrifice", "units": ["warriors"]})
    assert action == ColonizeSacrifice(("warriors",))
    assert action.units == ("warriors",)


# --- 竞拍触发与轮转 ---------------------------------------------------------


def test_reveal_territory_starts_bid_pending() -> None:
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("developed_territory_i", "development_of_science"),
        phase=Phase.POLITICS,
    )
    new = apply(state, SeedEvent("development_of_crafts"), db)
    # 地区牌不入 past_events(等待竞拍结果), current_events 已弹出
    assert new.past_events == ()
    assert new.current_events == ("development_of_science",)
    assert new.phase is Phase.ACTION
    assert len(new.pending) == 1
    pending = new.pending[0]
    assert pending.kind == politics.KIND_COLONIZE_BID
    assert pending.responder == 0
    assert pending.context["territory"] == "developed_territory_i"
    assert int(pending.context["current_bid"]) == 0
    assert int(pending.context["leader"]) == -1
    assert pending.context["bidders"] == "0,1"


def test_bid_rotation_three_players() -> None:
    db = build_card_db()
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": 2}  # 上限 2, 支持出价到 2
    players = tuple(_player(f"P{i}", buildings=buildings) for i in range(3))
    state = _state(
        players=players, current_player=1,
        pending=(_bid_pending(bidders=(1, 2, 0), responder=1),))
    s1 = apply(state, ColonizeBid(1), db)
    p = s1.pending[0]
    assert p.kind == politics.KIND_COLONIZE_BID
    assert p.responder == 2
    assert int(p.context["current_bid"]) == 1
    assert int(p.context["leader"]) == 1
    s2 = apply(s1, ColonizeBid(2), db)
    assert s2.pending[0].responder == 0
    assert int(s2.pending[0].context["leader"]) == 2
    # P0 pass -> 回到 P1; P1 pass -> 仅剩 leader P2 -> P2 胜出
    s3 = apply(s2, ColonizePass(), db)
    assert s3.pending[0].kind == politics.KIND_COLONIZE_BID
    assert s3.pending[0].responder == 1
    assert s3.pending[0].context["bidders"] == "1,2"
    s4 = apply(s3, ColonizePass(), db)
    assert s4.pending[0].kind == politics.KIND_COLONIZE_SACRIFICE
    assert s4.pending[0].responder == 2
    assert int(s4.pending[0].context["bid"]) == 2
    assert int(s4.pending[0].context["bonus"]) == 0


def test_bid_must_exceed_current_bid_and_within_cap() -> None:
    db = build_card_db()
    state = _bid_state()
    legal = legal_actions(db, state)
    # P0 仅 1 武士(军力 1) -> 上限 1, 仅 ColonizeBid(1) 合法
    assert ColonizeBid(1) in legal
    assert ColonizeBid(2) not in legal
    assert ColonizeBid(0) not in legal
    assert ColonizePass() in legal
    with pytest.raises(IllegalActionError):
        apply(state, ColonizeBid(2), db)
    with pytest.raises(IllegalActionError):
        apply(state, ColonizeBid(0), db)
    # P0 出价 1 后, P1(同样上限 1)必须更高 -> 无合法出价, 只能 pass
    s1 = apply(state, ColonizeBid(1), db)
    legal1 = legal_actions(db, s1)
    assert ColonizePass() in legal1
    assert not [a for a in legal1 if isinstance(a, ColonizeBid)]


def test_all_pass_sends_territory_to_past_events() -> None:
    db = build_card_db()
    state = _bid_state()
    s1 = apply(state, ColonizePass(), db)
    # 无人出价时仅剩 1 人仍须做决定(出价或退出)
    assert s1.pending[0].kind == politics.KIND_COLONIZE_BID
    assert s1.pending[0].responder == 1
    s2 = apply(s1, ColonizePass(), db)
    assert s2.pending == ()
    assert s2.past_events == ("developed_territory_i",)
    assert all("developed_territory_i" not in p.colonies for p in s2.players)


def test_last_bidder_may_still_bid_after_others_pass() -> None:
    # 2 人局: 揭示者 pass 后, 对手可出价直接胜出(bidders == [leader])
    db = build_card_db()
    state = _bid_state()
    s1 = apply(state, ColonizePass(), db)
    s2 = apply(s1, ColonizeBid(1), db)
    assert s2.pending[0].kind == politics.KIND_COLONIZE_SACRIFICE
    assert s2.pending[0].responder == 1
    assert int(s2.pending[0].context["bid"]) == 1


def test_resigned_player_excluded_from_bidding() -> None:
    # 已体面退出的玩家不参与殖民竞拍(与轮换跳过座位同口径): bidders 不含
    # 其座位, 轮转跳过, 不可出价/胜出
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    resigned_p1 = replace(_player("P1"), resigned=True)
    state = _state(
        players=(p0, resigned_p1, _player("P2")),
        current_events=("developed_territory_i",),
        phase=Phase.POLITICS,
    )
    s1 = apply(state, SeedEvent("development_of_crafts"), db)
    pending = s1.pending[0]
    assert pending.kind == politics.KIND_COLONIZE_BID
    assert pending.context["bidders"] == "0,2"
    # P0 出价 1 -> 轮转跳过退出者 P1 到 P2 -> P2 退出 -> P0 胜出
    s2 = apply(s1, ColonizeBid(1), db)
    assert s2.pending[0].responder == 2
    s3 = apply(s2, ColonizePass(), db)
    assert s3.pending[0].kind == politics.KIND_COLONIZE_SACRIFICE
    assert s3.pending[0].responder == 0


# --- 可承诺殖民军力上限 ------------------------------------------------------


def test_cap_includes_tactics_colonization_and_bonus_cards() -> None:
    db = build_card_db()
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": 2}
    p0 = _player(
        "P0", buildings=buildings, tactics="fighting_band",
        wonders=("colossus",), hand_military=("defense_colonization_i",))
    # 上限 = 单位 2 + 阵型 1(战斗队) + 殖民修正 1(巨像) + 奖励牌 1 = 5
    assert politics.colonization_cap(db, p0) == 5
    state = _bid_state(players=(p0, _player("P1")))
    legal = legal_actions(db, state)
    assert ColonizeBid(5) in legal
    assert ColonizeBid(6) not in legal


def test_player_without_units_cannot_bid() -> None:
    # 规则: 必须挑出至少 1 个军事单位 -> 无单位者即使上限 > 0 也不可出价
    db = build_card_db()
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    del buildings["infantry"]
    p0 = _player(
        "P0", buildings=buildings, wonders=("colossus",),
        hand_military=("defense_colonization_i",))
    assert politics.colonization_cap(db, p0) == 2
    state = _bid_state(players=(p0, _player("P1")))
    legal = legal_actions(db, state)
    assert not [a for a in legal if isinstance(a, ColonizeBid)]
    assert ColonizePass() in legal


# --- 胜者牺牲结算 ------------------------------------------------------------


def test_sacrifice_returns_workers_to_yellow_bank_and_grants_colony() -> None:
    db = build_card_db()
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": 2}
    p0 = _player("P0", buildings=buildings, yellow_bank=10)
    state = _sacrifice_state(player=p0)
    new = apply(state, ColonizeSacrifice(("warriors",)), db)
    p = new.players[0]
    assert p.buildings["infantry"] == {"warriors": 1}
    # 牺牲 1 工人回黄点银行 + 发达地区永久 1 人口标记
    assert p.yellow_bank == 12
    assert p.blue_bank == 17  # 永久 1 资源标记
    assert p.colonies == ("developed_territory_i",)
    assert p.science == 3  # 即时 +3 科技
    assert new.pending == ()
    assert new.past_events == ()


def test_sacrifice_with_tactics_grouping() -> None:
    # 被挑出的单位按当前阵型组军(规则书 p7): 2 武士 + 战斗队 = 3 军力
    db = build_card_db()
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": 2}
    p0 = _player("P0", buildings=buildings, tactics="fighting_band")
    state = _sacrifice_state(player=p0, pending_kwargs={"bid": 3})
    legal = legal_actions(db, state)
    # 全选锚点: 3 >= 3 合法
    assert ColonizeSacrifice(("warriors", "warriors")) in legal
    new = apply(state, ColonizeSacrifice(("warriors", "warriors")), db)
    assert new.players[0].colonies == ("developed_territory_i",)
    assert new.players[0].buildings["infantry"] == {}
    # 仅牺牲 1 武士(军力 1)不足出价 3
    with pytest.raises(IllegalActionError):
        apply(state, ColonizeSacrifice(("warriors",)), db)


def test_sacrifice_invalid_inputs_raise() -> None:
    db = build_card_db()
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": 2}
    p0 = _player("P0", buildings=buildings)
    state = _sacrifice_state(player=p0, pending_kwargs={"bid": 1})
    with pytest.raises(IllegalActionError):
        apply(state, ColonizeSacrifice(()), db)  # 至少 1 个单位
    with pytest.raises(IllegalActionError):
        apply(state, ColonizeSacrifice(("bronze",)), db)  # 非军事单位
    with pytest.raises(IllegalActionError):
        apply(state, ColonizeSacrifice(("warriors",) * 3), db)  # 超出工人数
    # 无 colonize_sacrifice pending 时同样非法
    with pytest.raises(IllegalActionError):
        apply(_bid_state(), ColonizeSacrifice(("warriors",)), db)


def test_sacrifice_unknown_card_id_raises_illegal_action() -> None:
    # 未知卡 id 统一抛 IllegalActionError(而非 db.get 的 KeyError), 消息含卡 id
    db = build_card_db()
    state = _sacrifice_state(pending_kwargs={"bid": 1})
    with pytest.raises(IllegalActionError, match="no_such_card"):
        apply(state, ColonizeSacrifice(("no_such_card",)), db)


def test_yellow_bank_over_18_legal_actions_ok() -> None:
    # 黄点银行 18(轨道已满) + 牺牲回 1 工人 + 殖民地永久 +1 黄点 -> 20,
    # 超出轨道合法(规则书 p10); 后续 legal_actions 不得因轨道查询崩溃
    db = build_card_db()
    p0 = _player("P0", yellow_bank=18)
    state = _sacrifice_state(player=p0, pending_kwargs={"bid": 1})
    new = apply(state, ColonizeSacrifice(("warriors",)), db)
    assert new.players[0].yellow_bank == 20
    legal = legal_actions(db, new)
    assert legal  # 非空且不抛异常



    db = build_card_db()
    state = _sacrifice_state(pending_kwargs={"bid": 2})
    with pytest.raises(IllegalActionError):
        apply(state, ColonizeSacrifice(("warriors",)), db)


def test_canonical_all_units_sacrifice_in_legal() -> None:
    db = build_card_db()
    buildings = {k: dict(v) for k, v in _INITIAL_BUILDINGS.items()}
    buildings["infantry"] = {"warriors": 2}
    p0 = _player("P0", buildings=buildings)
    state = _sacrifice_state(player=p0, pending_kwargs={"bid": 2})
    assert ColonizeSacrifice(("warriors", "warriors")) in legal_actions(db, state)


def test_colonization_modifier_counts_toward_fulfillment() -> None:
    # 殖民修正(巨像 +1)计入履约: 1 武士(1) + 修正(1) >= 出价 2
    db = build_card_db()
    p0 = _player("P0", wonders=("colossus",))
    state = _sacrifice_state(player=p0, pending_kwargs={"bid": 2})
    assert ColonizeSacrifice(("warriors",)) in legal_actions(db, state)
    new = apply(state, ColonizeSacrifice(("warriors",)), db)
    assert new.players[0].colonies == ("developed_territory_i",)


def test_bonus_cards_make_up_shortfall() -> None:
    db = build_card_db()
    p0 = _player("P0", hand_military=("defense_colonization_i",))
    state = _sacrifice_state(player=p0, pending_kwargs={"bid": 2})
    legal = legal_actions(db, state)
    # 1 武士(1) + 修正(0) + 已出奖励(0) < 2 -> 全选锚点不可用, 先出奖励牌
    assert not [a for a in legal if isinstance(a, ColonizeSacrifice)]
    assert ColonizePlayBonus("defense_colonization_i") in legal
    s1 = apply(state, ColonizePlayBonus("defense_colonization_i"), db)
    assert s1.players[0].hand_military == ()
    assert s1.military_discard == ("defense_colonization_i",)
    assert int(s1.pending[0].context["bonus"]) == 1
    # 1 + 0 + 1 >= 2 -> 牺牲成功
    assert ColonizeSacrifice(("warriors",)) in legal_actions(db, s1)
    s2 = apply(s1, ColonizeSacrifice(("warriors",)), db)
    assert s2.players[0].colonies == ("developed_territory_i",)


# --- 即时/永久效果 -----------------------------------------------------------


def _win_colony(
    db, state: GameState, territory: str, *, bid: int = 1,
) -> GameState:
    """以 responder=0 直接完成牺牲(1 武士 + 0 修正 >= bid=1)获得殖民地."""
    pending = _sacrifice_pending(territory=territory, bid=bid)
    return apply(
        replace(state, pending=(pending,)),
        ColonizeSacrifice(("warriors",)), db)


def test_immediate_population() -> None:
    db = build_card_db()
    p0 = _player("P0", yellow_bank=10, worker_pool=1)
    new = _win_colony(db, _state(players=(p0, _player("P1"))),
                      "inhabited_territory_i")
    p = new.players[0]
    # 牺牲 +1 -> 11; 永久 2 人口标记 -> 13; 即时 +1 人口 -> 12, 空闲工人 +1
    assert p.yellow_bank == 12
    assert p.worker_pool == 2


def test_immediate_military_cards_and_permanent_strength() -> None:
    db = build_card_db()
    state = _state(
        age=Age.I,
        military_deck=("raid_i", "enslave_i", "plunder_i", "raid_i"),
    )
    new = _win_colony(db, state, "strategic_territory_i")
    p = new.players[0]
    # 即时 +3 张军事牌(忽略手牌上限)
    assert p.hand_military == ("raid_i", "enslave_i", "plunder_i")
    assert new.military_deck == ("raid_i",)
    # 永久 +2 军力入 civ 合成(唯一武士已牺牲, 单位军力 0)
    assert civ_values(db, p).strength == 2


def test_immediate_food_and_negative_blue_token() -> None:
    db = build_card_db()
    p0 = _player("P0", yellow_bank=10, blue_bank=10)
    new = _win_colony(db, _state(players=(p0, _player("P1"))),
                      "vast_territory_i")
    p = new.players[0]
    assert p.yellow_bank == 14  # 牺牲 +1, 永久 3 人口标记
    # 永久 -1 资源标记 -> 9; 即时 +3 食物(3 蓝点上农场)-> 6
    assert p.blue_bank == 6
    assert p.card_tokens == {"agriculture": 3}


def test_negative_blue_token_floors_at_zero() -> None:
    db = build_card_db()
    p0 = _player("P0", blue_bank=0)
    new = _win_colony(db, _state(players=(p0, _player("P1"))),
                      "vast_territory_i")
    p = new.players[0]
    assert p.blue_bank == 0  # 负值下限 0; 供给空 -> 即时食物无法获得
    assert p.card_tokens == {}


def test_permanent_happiness_enters_civ() -> None:
    db = build_card_db()
    new = _win_colony(db, _state(), "historic_territory_i")
    p = new.players[0]
    assert p.culture == 6  # 即时 +6 文化
    assert civ_values(db, p).happiness == 1  # 永久 +1 笑脸


def test_two_player_full_auction_flow() -> None:
    # 2 人局全流程: 揭示 -> 轮转出价 -> 牺牲 -> 获得殖民地
    db = build_card_db()
    p0 = _player("P0", hand_military=("development_of_crafts",))
    state = _state(
        players=(p0, _player("P1")),
        current_events=("historic_territory_i",),
        phase=Phase.POLITICS,
    )
    s1 = apply(state, SeedEvent("development_of_crafts"), db)
    assert s1.pending[0].kind == politics.KIND_COLONIZE_BID
    s2 = apply(s1, ColonizeBid(1), db)      # P0 出价 1
    s3 = apply(s2, ColonizePass(), db)      # P1 退出 -> P0 胜出
    assert s3.pending[0].kind == politics.KIND_COLONIZE_SACRIFICE
    assert s3.pending[0].responder == 0
    s4 = apply(s3, ColonizeSacrifice(("warriors",)), db)
    assert s4.pending == ()
    assert s4.players[0].colonies == ("historic_territory_i",)
    assert s4.past_events == ()
