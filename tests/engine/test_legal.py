"""合法动作生成测试."""

from tta.engine.actions import (
    Build,
    Develop,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    TakeCard,
    action_from_dict,
    action_to_dict,
)
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import GameState, PlayerState

GOV = GovernmentStats(civil_actions=4, military_actions=2,
                      civil_hand_limit=2, military_hand_limit=2)


def _card(cid: str, cat: CardCategory, sci: int = 0, build: int = 0) -> CardDefinition:
    return CardDefinition(id=cid, name=cid, age=Age.A, deck=DeckType.CIVIL,
                          category=cat, cost_science=sci, build_cost=build)


def _db() -> CardDB:
    cards = {
        "despotism": CardDefinition(id="despotism", name="专制", age=Age.A,
                                    deck=DeckType.CIVIL,
                                    category=CardCategory.GOVERNMENT, government=GOV),
        "agriculture": _card("agriculture", CardCategory.FARM, sci=0, build=2),
        "iron": _card("iron", CardCategory.MINE, sci=2, build=2),
        "irrigation": _card("irrigation", CardCategory.FARM, sci=2, build=2),
        "swordsmen": _card("swordsmen", CardCategory.UNIT, sci=2, build=2),
        "monarchy": CardDefinition(id="monarchy", name="君主制", age=Age.A,
                                   deck=DeckType.CIVIL,
                                   category=CardCategory.GOVERNMENT, cost_science=2,
                                   government=GOV),
        "harvest_a": _card("harvest_a", CardCategory.ACTION),
    }
    return CardDB(cards=cards, civil_decks={Age.A: ()},
                  initial_tableau=(), initial_government="despotism")


def _state(p: PlayerState, row: tuple = (None,) * 13) -> GameState:
    return GameState(round=1, age=Age.A, current_player=0, card_row=row,
                     civil_deck=(), future_decks={}, discard=(), removed=(),
                     players=(p,), rng_state=1)


def test_terminal_state_has_no_actions() -> None:
    state = _state(PlayerState(name="P0"))
    done = GameState(**{**state.__dict__, "terminal": True})
    assert legal_actions(done, _db()) == []


def test_pass_always_available_and_last() -> None:
    p = PlayerState(name="P0", government="despotism")
    actions = legal_actions(_state(p), _db())
    assert actions[-1] == PassTurn()


def test_take_card_cost_and_hand_limit() -> None:
    row = ("irrigation", None) + (None,) * 11
    p = PlayerState(name="P0", government="despotism", civil_actions=1)
    assert TakeCard(0) in legal_actions(_state(p, row), _db())
    # 白点 0 不能拿; 手牌满(上限2)不能拿
    p0 = PlayerState(name="P0", government="despotism", civil_actions=0)
    assert TakeCard(0) not in legal_actions(_state(p0, row), _db())
    full = PlayerState(name="P0", government="despotism", civil_actions=1,
                       hand_civil=("irrigation", "iron"))
    assert TakeCard(0) not in legal_actions(_state(full, row), _db())


def test_develop_needs_science_and_action_color() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    military_actions=0, science=2,
                    hand_civil=("irrigation", "swordsmen", "monarchy"))
    actions = legal_actions(_state(p), _db())
    assert Develop("irrigation") in actions       # 白点科技
    assert Develop("monarchy") in actions         # 政体
    assert Develop("swordsmen") not in actions    # 兵种需红点


def test_build_requires_developed_copy_and_materials() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    materials=2, worker_pool=1, developed=("irrigation",))
    assert Build("irrigation") in legal_actions(_state(p), _db())
    poor = PlayerState(name="P0", government="despotism", civil_actions=1,
                       materials=1, worker_pool=1, developed=("irrigation",))
    assert Build("irrigation") not in legal_actions(_state(poor), _db())
    # 已研发 1 张且已放 1 工人 => 不能再建
    used = PlayerState(name="P0", government="despotism", civil_actions=1,
                       materials=5, worker_pool=1, developed=("irrigation",),
                       buildings={"farm": {"irrigation": 1}})
    assert Build("irrigation") not in legal_actions(_state(used), _db())


def test_build_worker_source_can_be_same_type_building() -> None:
    # 升级: 工人可从同类型低级建筑(agriculture)移到新建筑
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    materials=2, worker_pool=0,
                    developed=("agriculture", "irrigation"),
                    buildings={"farm": {"agriculture": 1}})
    assert Build("irrigation") in legal_actions(_state(p), _db())
    # 同名卡之间不构成工人来源: 池空且只有同名建筑上有工人 => 不可建
    p2 = PlayerState(name="P0", government="despotism", civil_actions=1,
                     materials=2, worker_pool=0,
                     developed=("irrigation", "irrigation"),
                     buildings={"farm": {"irrigation": 1}})
    assert Build("irrigation") not in legal_actions(_state(p2), _db())


def test_increase_population_conditions() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    food=2, yellow_bank=5)
    assert IncreasePopulation() in legal_actions(_state(p), _db())
    hungry = PlayerState(name="P0", government="despotism", civil_actions=1,
                         food=1, yellow_bank=5)
    assert IncreasePopulation() not in legal_actions(_state(hungry), _db())


def test_play_action_card() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    hand_civil=("harvest_a",))
    assert PlayActionCard("harvest_a") in legal_actions(_state(p), _db())


def test_action_dict_roundtrip() -> None:
    for a in (TakeCard(3), Develop("irrigation"), Build("iron"),
              IncreasePopulation(), PlayActionCard("harvest_a"), PassTurn()):
        assert action_from_dict(action_to_dict(a)) == a
