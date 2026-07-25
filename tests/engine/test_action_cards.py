"""行动卡结算与 pending 子行动测试(见 tta/engine/effects.py / legal.py / apply.py).

三类行为分别由测试桩 handler 验证:
- stockpile(即时收益类): 食物/资源各 1 蓝点入最低级卡;
- rich_land(折扣子行动类): push PendingEffect("build_farm_mine", 3);
- patriotism(回合修饰类): 红点 +1 且 turn_discounts["unit_build"] = 3;
- engineering_genius(折扣子行动类奇迹变体): push PendingEffect("wonder_stage", 2).
"""

from dataclasses import replace

import pytest

from tta.engine import effects
from tta.engine.actions import (
    Build,
    BuildWonderStage,
    IllegalActionError,
    PassTurn,
    PlayActionCard,
    Upgrade,
)
from tta.engine.apply import apply
from tta.engine.economy import gain_tokens
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
    replace_player,
)


def _card(card_id: str, category: CardCategory, **overrides: object) -> CardDefinition:
    base: dict = {
        "id": card_id,
        "name": card_id,
        "name_en": card_id,
        "age": Age.A,
        "deck": DeckType.CIVIL,
        "category": category,
    }
    base.update(overrides)
    return CardDefinition(**base)


def _db() -> CardDB:
    cards = {
        "despotism": _card(
            "despotism", CardCategory.GOVERNMENT,
            government=GovernmentStats(civil_actions=4, military_actions=2,
                                       urban_limit=2),
        ),
        "agriculture": _card("agriculture", CardCategory.FARM, cost_science=2,
                             build_cost=2, token_value=1),
        "irrigation": _card("irrigation", CardCategory.FARM, age=Age.I,
                            cost_science=3, build_cost=3, token_value=2),
        "bronze": _card("bronze", CardCategory.MINE, cost_science=2,
                        build_cost=2, token_value=1),
        "philosophy": _card("philosophy", CardCategory.LAB, cost_science=3,
                            build_cost=3, urban_produces={"science": 1}),
        "warriors": _card("warriors", CardCategory.INFANTRY, cost_science=2,
                          build_cost=2, strength=1),
        "pyramids": _card("pyramids", CardCategory.WONDER,
                          wonder_stages=(3, 2)),
        "stockpile": _card("stockpile", CardCategory.ACTION, handler="stockpile"),
        "rich_land": _card("rich_land", CardCategory.ACTION, handler="rich_land"),
        "patriotism": _card("patriotism", CardCategory.ACTION, handler="patriotism"),
        "genius": _card("genius", CardCategory.ACTION, handler="engineering_genius"),
        "frugality": _card("frugality", CardCategory.ACTION, handler="frugality"),
        "mystery": _card("mystery", CardCategory.ACTION, handler="unregistered"),
    }
    return CardDB(cards=cards, initial_tableau=("agriculture", "philosophy"),
                  initial_government="despotism")


def _player(**overrides: object) -> PlayerState:
    base: dict = {"name": "P0", "civil_actions": 4, "military_actions": 2}
    base.update(overrides)
    return PlayerState(**base)


def _row(*ids: str | None) -> tuple[str | None, ...]:
    row = list(ids) + [None] * (ROW_SLOTS - len(ids))
    return tuple(row)


def _state(player: PlayerState, **overrides: object) -> GameState:
    base: dict = {
        "round": 2,
        "age": Age.A,
        "current_player": 0,
        "card_row": _row(),
        "civil_deck": (),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (player, _player(name="P1")),
        "rng_state": 0,
    }
    base.update(overrides)
    return GameState(**base)


def _stockpile_handler(
    state: GameState, player_index: int, db: CardDB, option: str = "",
) -> GameState:
    """即时收益类桩: 食物与资源各 1 蓝点入最低级卡."""
    p = state.players[player_index]
    p = gain_tokens(db, p, "food", 1)
    p = gain_tokens(db, p, "resource", 1)
    return replace_player(state, player_index, p)


def _rich_land_handler(
    state: GameState, player_index: int, db: CardDB, option: str = "",
) -> GameState:
    """折扣子行动类桩: 下一农场/矿场 Build/Upgrade 折扣 3 且 0 行动点."""
    return effects.push_pending(
        state, PendingEffect(effects.KIND_BUILD_FARM_MINE, 3))


def _patriotism_handler(
    state: GameState, player_index: int, db: CardDB, option: str = "",
) -> GameState:
    """回合修饰类桩: 红点 +1, 本回合兵种建造折扣 3."""
    p = state.players[player_index]
    discounts = dict(p.turn_discounts)
    discounts["unit_build"] = 3
    p = replace(p, military_actions=p.military_actions + 1,
                turn_discounts=discounts)
    return replace_player(state, player_index, p)


def _genius_handler(
    state: GameState, player_index: int, db: CardDB, option: str = "",
) -> GameState:
    """折扣子行动类桩(奇迹): 下一奇迹阶段折扣 2 且 0 行动点."""
    return effects.push_pending(
        state, PendingEffect(effects.KIND_WONDER_STAGE, 2))


@pytest.fixture
def handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(effects.ACTION_HANDLERS, "stockpile", _stockpile_handler)
    monkeypatch.setitem(effects.ACTION_HANDLERS, "rich_land", _rich_land_handler)
    monkeypatch.setitem(effects.ACTION_HANDLERS, "patriotism", _patriotism_handler)
    monkeypatch.setitem(effects.ACTION_HANDLERS, "engineering_genius", _genius_handler)
    monkeypatch.setitem(effects.PENDING_SPECS, "rich_land",
                        PendingEffect(effects.KIND_BUILD_FARM_MINE, 3))
    monkeypatch.setitem(effects.PENDING_SPECS, "engineering_genius",
                        PendingEffect(effects.KIND_WONDER_STAGE, 2))


@pytest.mark.usefixtures("handlers")
def test_stockpile_instant_gain_and_discard() -> None:
    db = _db()
    p = _player(hand_civil=("stockpile",), developed=("agriculture", "bronze"),
                blue_bank=16)
    new = apply(_state(p), PlayActionCard("stockpile"), db)
    p0 = new.players[0]
    # 收益入账(各自最低级卡), 卡入弃牌堆, 手牌移除, 扣 1 白点
    assert p0.card_tokens == {"agriculture": 1, "bronze": 1}
    assert p0.blue_bank == 14
    assert new.discard == ("stockpile",)
    assert p0.hand_civil == ()
    assert p0.civil_actions == 3
    assert new.pending == ()


@pytest.mark.usefixtures("handlers")
def test_rich_land_pending_full_flow() -> None:
    db = _db()
    # 打出后白点归零: 子行动必须 0 行动点; 0 资源时折扣后费用为 0
    p = _player(hand_civil=("rich_land",), civil_actions=1,
                developed=("agriculture", "philosophy"), worker_pool=1)
    new = apply(_state(p), PlayActionCard("rich_land"), db)
    assert new.pending == (PendingEffect("build_farm_mine", 3),)
    assert new.players[0].civil_actions == 0
    assert new.discard == ("rich_land",)

    # pending 时仅生成可结算 pending 的动作 + PassTurn; 城市建筑被排除
    legal = legal_actions(db, new)
    assert Build("agriculture") in legal
    assert Build("philosophy") not in legal
    assert legal[-1] == PassTurn()
    assert all(
        isinstance(a, (Build, Upgrade, PassTurn)) for a in legal
    )

    # 0 白点 + 折扣结算, pending pop 后恢复正常
    new2 = apply(new, Build("agriculture"), db)
    p2 = new2.players[0]
    assert new2.pending == ()
    assert p2.civil_actions == 0  # 子行动不扣行动点
    assert p2.card_tokens == {}   # 费用 max(0, 2-3) = 0
    assert p2.worker_pool == 0
    assert p2.buildings == {"farm": {"agriculture": 1}}


@pytest.mark.usefixtures("handlers")
def test_rich_land_upgrade_with_discount() -> None:
    db = _db()
    p = _player(hand_civil=("rich_land",), civil_actions=1, worker_pool=0,
                developed=("agriculture", "irrigation"),
                buildings={"farm": {"agriculture": 1}}, card_tokens={})
    new = apply(_state(p), PlayActionCard("rich_land"), db)
    legal = legal_actions(db, new)
    # 差价 max(0, 3-2)=1, 折扣 3 后为 0; 无空闲工人故无 Build
    assert legal == [Upgrade("agriculture", "irrigation"), PassTurn()]
    new2 = apply(new, Upgrade("agriculture", "irrigation"), db)
    p2 = new2.players[0]
    assert new2.pending == ()
    assert p2.buildings == {"farm": {"irrigation": 1}}
    assert p2.card_tokens == {}
    assert p2.civil_actions == 0


@pytest.mark.usefixtures("handlers")
def test_pending_pass_turn_discards_pending() -> None:
    db = _db()
    p = _player(hand_civil=("rich_land",), developed=("agriculture",),
                worker_pool=1)
    new = apply(_state(p), PlayActionCard("rich_land"), db)
    assert PassTurn() in legal_actions(db, new)
    # SIMPLIFICATION: 官方行动卡效果为强制; 引擎允许 PassTurn 放弃 pending
    new2 = apply(new, PassTurn(), db)
    assert new2.pending == ()


@pytest.mark.usefixtures("handlers")
def test_rich_land_unplayable_without_target() -> None:
    db = _db()
    # 无任何已研发农场/矿场: 无合法子行动, 折扣卡不可打出
    p = _player(hand_civil=("rich_land",), developed=("philosophy",),
                worker_pool=1)
    state = _state(p)
    assert PlayActionCard("rich_land") not in legal_actions(db, state)
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("rich_land"), db)


@pytest.mark.usefixtures("handlers")
def test_unregistered_action_card_unplayable() -> None:
    db = _db()
    p = _player(hand_civil=("mystery",))
    state = _state(p)
    assert PlayActionCard("mystery") not in legal_actions(db, state)
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("mystery"), db)


@pytest.mark.usefixtures("handlers")
def test_patriotism_turn_modifier() -> None:
    db = _db()
    p = _player(hand_civil=("patriotism",), military_actions=1,
                developed=("warriors",), worker_pool=1, card_tokens={})
    new = apply(_state(p), PlayActionCard("patriotism"), db)
    p0 = new.players[0]
    assert p0.military_actions == 2          # 红点立即 +1
    assert p0.turn_discounts == {"unit_build": 3}
    assert p0.civil_actions == 3
    assert new.discard == ("patriotism",)

    # 本回合兵种建造享折扣: 0 资源也可建(费用 max(0, 2-3) = 0)
    assert Build("warriors") in legal_actions(db, new)
    new2 = apply(new, Build("warriors"), db)
    p2 = new2.players[0]
    assert p2.military_actions == 1          # 正常建造仍扣 1 红点
    assert p2.card_tokens == {}
    assert p2.buildings == {"infantry": {"warriors": 1}}


@pytest.mark.usefixtures("handlers")
def test_engineering_genius_wonder_stage() -> None:
    db = _db()
    p = _player(hand_civil=("genius",), wonder_progress=("pyramids", 0),
                card_tokens={"bronze": 1}, blue_bank=16)
    new = apply(_state(p), PlayActionCard("genius"), db)
    assert new.pending == (PendingEffect("wonder_stage", 2),)
    # 阶段费 3 折扣 2 后为 1, 恰可支付; 0 行动点
    assert legal_actions(db, new) == [BuildWonderStage(), PassTurn()]
    new2 = apply(new, BuildWonderStage(), db)
    p2 = new2.players[0]
    assert new2.pending == ()
    assert p2.wonder_progress == ("pyramids", 1)
    assert p2.card_tokens == {}
    # 支付 1 蓝点放回供给区 (16+1), 再从供给区盖 1 蓝点上奇迹 (-1)
    assert p2.blue_bank == 16
    assert p2.civil_actions == 3  # 仅打出卡扣 1 白点, 子行动不扣


def test_frugality_reuses_shared_increase_population() -> None:
    """frugality 回归: 真实注册 handler 复用增人口共用结算(付人口费), 再 +1 食物."""
    db = _db()
    p = _player(hand_civil=("frugality",), developed=("agriculture",),
                card_tokens={"agriculture": 2}, yellow_bank=18, worker_pool=1,
                blue_bank=16)
    state = _state(p)
    assert PlayActionCard("frugality") in legal_actions(db, state)
    new = apply(state, PlayActionCard("frugality"), db)
    p0 = new.players[0]
    assert p0.yellow_bank == 17
    assert p0.worker_pool == 2
    assert p0.card_tokens == {"agriculture": 1}  # 付人口费 2 再得 1
    assert p0.civil_actions == 3
    assert new.discard == ("frugality",)


@pytest.mark.usefixtures("handlers")
def test_genius_unplayable_without_wonder() -> None:
    db = _db()
    p = _player(hand_civil=("genius",))
    state = _state(p)
    assert PlayActionCard("genius") not in legal_actions(db, state)
    with pytest.raises(IllegalActionError):
        apply(state, PlayActionCard("genius"), db)
