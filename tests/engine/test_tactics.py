"""阵型与军力系统测试(P2-T4, 见 tta/engine/military.py 模块 docstring).

覆盖: 基础军力、完整组加成、残缺组无加成、多组、旧式减半、贪心填充
确定性、空军翻倍与"空军不能单独成军"、PlayTactics/CopyTactics 合法性与
结算、每回合限 1、回合开始强制公开、tactics_this_turn 行动点恢复时清零、
亚历山大/拿破仑静态加成叠加、civ_values 军力口径。
"""

import pytest

from tta.engine.actions import (
    CopyTactics,
    IllegalActionError,
    PassTurn,
    PlayTactics,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.civ import civ_values
from tta.engine.enums import Age, CardCategory, DeckType, Phase
from tta.engine.legal import legal_actions
from tta.engine.military import army_strength
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
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


def _tactics(card_id: str, age: Age, units: dict[str, int],
             strength: int, outdated: int = 0) -> CardDefinition:
    return _card(
        card_id, CardCategory.TACTICS, age, deck=DeckType.MILITARY,
        tactics_units=units, tactics_strength=strength,
        tactics_strength_outdated=outdated, quantities=(1, 1, 1))


def _db() -> CardDB:
    cards = {
        "despotism": _card(
            "despotism", CardCategory.GOVERNMENT,
            government=GovernmentStats(
                civil_actions=4, military_actions=2, urban_limit=2),
        ),
        # 军事单位(各时代, strength 见卡牌数值表)
        "warriors": _card("warriors", CardCategory.INFANTRY, Age.A, strength=1),
        "horsemen": _card("horsemen", CardCategory.CAVALRY, Age.A, strength=1),
        "swordsmen": _card(
            "swordsmen", CardCategory.INFANTRY, Age.I, strength=2),
        "knights": _card("knights", CardCategory.CAVALRY, Age.I, strength=2),
        "catapults": _card(
            "catapults", CardCategory.ARTILLERY, Age.I, strength=2),
        "modern_infantry": _card(
            "modern_infantry", CardCategory.INFANTRY, Age.III, strength=3),
        "tanks": _card("tanks", CardCategory.CAVALRY, Age.III, strength=3),
        "rockets": _card("rockets", CardCategory.ARTILLERY, Age.III, strength=3),
        "air_forces": _card("air_forces", CardCategory.AIR, Age.III, strength=5),
        # 阵型(数值同官方卡牌数值表)
        "fighting_band": _tactics("fighting_band", Age.I, {"INFANTRY": 2}, 1),
        "phalanx": _tactics(
            "phalanx", Age.I, {"INFANTRY": 2, "CAVALRY": 1}, 3),
        "classic_army": _tactics(
            "classic_army", Age.II, {"INFANTRY": 2, "CAVALRY": 2}, 8, 4),
        "modern_army": _tactics(
            "modern_army", Age.III,
            {"INFANTRY": 2, "CAVALRY": 1, "ARTILLERY": 1}, 13, 7),
        # 领袖(handler 已注册于 effects.STATIC_BONUS_HANDLERS)
        "alexander_the_great": _card(
            "alexander_the_great", CardCategory.LEADER,
            handler="alexander_the_great"),
        "napoleon_bonaparte": _card(
            "napoleon_bonaparte", CardCategory.LEADER, Age.II,
            handler="napoleon_bonaparte"),
    }
    for i in range(18):
        cards[f"xc{i}"] = _card(f"xc{i}", CardCategory.ACTION, Age.I)
    return CardDB(cards=cards, initial_tableau=(),
                  initial_government="despotism")


def _player(name: str, **overrides: object) -> PlayerState:
    base: dict = {"name": name}
    base.update(overrides)
    return PlayerState(**base)


def _state(**overrides: object) -> GameState:
    """默认: round 2 / 时代 I / P0 行动, ACTION 相位, 牌列满, 内政堆余 5 张."""
    base: dict = {
        "round": 2,
        "age": Age.I,
        "current_player": 0,
        "card_row": tuple(f"xc{i}" for i in range(ROW_SLOTS)),
        "civil_deck": tuple(f"xc{i}" for i in range(ROW_SLOTS, 18)),
        "future_decks": {},
        "discard": (),
        "removed": (),
        "players": (_player("P0"), _player("P1")),
        "rng_state": 7,
        "phase": Phase.ACTION,
    }
    base.update(overrides)
    return GameState(**base)


def _units(*entries: tuple[str, str, int]) -> dict[str, dict[str, int]]:
    """[(category_value, card_id, workers), ...] -> buildings dict."""
    buildings: dict[str, dict[str, int]] = {}
    for category_value, card_id, workers in entries:
        buildings.setdefault(category_value, {})[card_id] = workers
    return buildings


# --- army_strength: 基础与组军 ------------------------------------------------


def test_no_tactics_base_only() -> None:
    """无阵型: 军力 = Σ 单位工人数 × 卡 strength."""
    p = _player("P0", buildings=_units(
        ("infantry", "warriors", 2), ("cavalry", "knights", 1)))
    assert army_strength(_db(), p) == 2 * 1 + 2


def test_complete_group_bonus() -> None:
    """完整组: fighting_band {2 步兵} +2 战士 -> 基础 2 + 阵型 1."""
    p = _player("P0", tactics="fighting_band",
                buildings=_units(("infantry", "warriors", 2)))
    assert army_strength(_db(), p) == 3


def test_incomplete_group_no_bonus() -> None:
    """残缺组无加成: phalanx 需 2 步兵 + 1 骑兵, 仅有 2 步兵."""
    p = _player("P0", tactics="phalanx",
                buildings=_units(("infantry", "warriors", 2)))
    assert army_strength(_db(), p) == 2


def test_multiple_groups() -> None:
    """多组: fighting_band + 5 战士 -> 2 完整组, 基础 5 + 2."""
    p = _player("P0", tactics="fighting_band",
                buildings=_units(("infantry", "warriors", 5)))
    assert army_strength(_db(), p) == 7


def test_outdated_group_half_value() -> None:
    """旧式军队: Age A 单位比 Age II 阵型低 2 时代 -> 按 outdated 4 计."""
    p = _player("P0", tactics="classic_army",
                buildings=_units(("infantry", "warriors", 2),
                                 ("cavalry", "horsemen", 2)))
    # 基础 4 + 旧式 4(而非 8)
    assert army_strength(_db(), p) == 8


def test_modern_group_full_value() -> None:
    """低 1 时代不算旧式: Age I 单位配 Age II 阵型 -> 全额 8."""
    p = _player("P0", tactics="classic_army",
                buildings=_units(("infantry", "swordsmen", 2),
                                 ("cavalry", "knights", 2)))
    # 基础 8 + 8
    assert army_strength(_db(), p) == 16


def test_greedy_fill_deterministic() -> None:
    """贪心填充: 按 strength 降序(并列 card_id)成组, 新旧单位各自成组.

    classic_army 2 组: 第 1 组 Age I 单位(全额 8), 第 2 组 Age A 单位
    (旧式 4); 混编会使两组皆旧式(4+4), 贪心结果 8+4 更优且确定。
    """
    p = _player("P0", tactics="classic_army",
                buildings=_units(("infantry", "warriors", 2),
                                 ("infantry", "swordsmen", 2),
                                 ("cavalry", "horsemen", 2),
                                 ("cavalry", "knights", 2)))
    # 基础 12 + 8 + 4
    assert army_strength(_db(), p) == 24


# --- army_strength: 空军 -------------------------------------------------------


def test_air_doubles_group() -> None:
    """空军加入 1 支军队使其阵型军力翻倍(规则书 p9), 空军基础军力照计."""
    p = _player("P0", tactics="modern_army",
                buildings=_units(("infantry", "modern_infantry", 2),
                                 ("cavalry", "tanks", 1),
                                 ("artillery", "rockets", 1),
                                 ("air", "air_forces", 1)))
    # 基础 6+3+3+5=17 + 阵型 13 + 空军翻倍 13
    assert army_strength(_db(), p) == 43


def test_air_alone_forms_no_army() -> None:
    """空军不能单独成军: 仅有空军单位时无阵型加成, 仅计基础军力."""
    p = _player("P0", tactics="modern_army",
                buildings=_units(("air", "air_forces", 2)))
    assert army_strength(_db(), p) == 10


def test_air_count_limits_doubling() -> None:
    """空军单位数 < 军队数时仅部分组翻倍(每组至多 1 空军)."""
    p = _player("P0", tactics="classic_army",
                buildings=_units(("infantry", "swordsmen", 4),
                                 ("cavalry", "knights", 4),
                                 ("air", "air_forces", 1)))
    # 基础 21 + 两组 8+8 + 仅 1 组翻倍 +8
    assert army_strength(_db(), p) == 45


def test_air_doubles_outdated_group_by_smaller_value() -> None:
    """旧式军队含空军: 只对数值较小的旧式军力翻倍(规则书 p9)."""
    p = _player("P0", tactics="modern_army",
                buildings=_units(("infantry", "swordsmen", 2),
                                 ("cavalry", "knights", 1),
                                 ("artillery", "catapults", 1),
                                 ("air", "air_forces", 1)))
    # 基础 4+2+2+5=13 + 旧式 7 + 翻倍旧式 7
    assert army_strength(_db(), p) == 27


# --- civ_values 口径与领袖叠加 ---------------------------------------------------


def test_civ_strength_uses_army_strength() -> None:
    """civ_values.strength = army_strength + 静态加成."""
    p = _player("P0", tactics="fighting_band",
                buildings=_units(("infantry", "warriors", 2)))
    assert civ_values(_db(), p).strength == 3


def test_alexander_bonus_stacks() -> None:
    """亚历山大: 每军事单位(工人)+1 军力, 叠加于基础与阵型加成之上."""
    p = _player("P0", leader="alexander_the_great", tactics="fighting_band",
                buildings=_units(("infantry", "warriors", 2)))
    # army 3 + 亚历山大 2
    assert civ_values(_db(), p).strength == 5


def test_napoleon_bonus_stacks() -> None:
    """拿破仑: 每种军事单位类型 +2 军力(同种多工人只计 1 种)."""
    p = _player("P0", leader="napoleon_bonaparte",
                buildings=_units(("infantry", "warriors", 2),
                                 ("cavalry", "knights", 1)))
    # 基础 4 + 拿破仑 2 类型 × 2
    assert civ_values(_db(), p).strength == 8


# --- PlayTactics / CopyTactics 合法性 ------------------------------------------


def test_play_tactics_legal() -> None:
    """手牌中的阵型牌: 1 红点, ACTION 相位, 本回合未打出/复制过."""
    state = _state(players=(
        _player("P0", military_actions=3, hand_military=("fighting_band",)),
        _player("P1")))
    assert PlayTactics("fighting_band") in legal_actions(_db(), state)


def test_play_tactics_requires_military_action() -> None:
    """红点不足不可打出阵型."""
    state = _state(players=(
        _player("P0", military_actions=0, hand_military=("fighting_band",)),
        _player("P1")))
    assert PlayTactics("fighting_band") not in legal_actions(_db(), state)


def test_play_tactics_illegal_when_used_this_turn() -> None:
    """打出与复制合计每回合限 1 次."""
    state = _state(players=(
        _player("P0", military_actions=3, tactics_this_turn=True,
                hand_military=("fighting_band",)),
        _player("P1", tactics="phalanx", tactics_public=True)))
    actions = legal_actions(_db(), state)
    assert PlayTactics("fighting_band") not in actions
    assert CopyTactics("phalanx") not in actions


def test_copy_tactics_legal() -> None:
    """复制对手已公开阵型: 2 红点, 不消耗手牌."""
    state = _state(players=(
        _player("P0", military_actions=2),
        _player("P1", tactics="phalanx", tactics_public=True)))
    assert CopyTactics("phalanx") in legal_actions(_db(), state)


def test_copy_tactics_requires_public() -> None:
    """对手阵型未公开时不可复制."""
    state = _state(players=(
        _player("P0", military_actions=3),
        _player("P1", tactics="phalanx", tactics_public=False)))
    assert CopyTactics("phalanx") not in legal_actions(_db(), state)


def test_copy_tactics_requires_two_military_actions() -> None:
    """复制需 2 红点."""
    state = _state(players=(
        _player("P0", military_actions=1),
        _player("P1", tactics="phalanx", tactics_public=True)))
    assert CopyTactics("phalanx") not in legal_actions(_db(), state)


def test_copy_tactics_excludes_own_current() -> None:
    """已是自己当前阵型的卡不再枚举复制(无意义动作)."""
    state = _state(players=(
        _player("P0", military_actions=3, tactics="phalanx",
                tactics_public=True),
        _player("P1", tactics="phalanx", tactics_public=True)))
    assert CopyTactics("phalanx") not in legal_actions(_db(), state)


# --- PlayTactics / CopyTactics 结算 --------------------------------------------


def test_play_tactics_apply() -> None:
    """打出: 手牌移除, 扣 1 红点, 成为专属阵型(未公开), 本回合已用."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=3,
                hand_military=("fighting_band", "phalanx")),
        _player("P1")))
    state = apply(state, PlayTactics("fighting_band"), db)
    p = state.players[0]
    assert p.hand_military == ("phalanx",)
    assert p.military_actions == 2
    assert p.tactics == "fighting_band"
    assert p.tactics_public is False
    assert p.tactics_this_turn is True
    assert state.military_discard == ()


def test_play_tactics_replaces_old_to_removed() -> None:
    """已有旧阵型(已公开)时打出新阵型: 旧阵型入 removed, 不入军事弃牌堆.

    官方规则(规则书 p3): 已公开的阵型被替换后留公共阵型区, 重复卡从游戏
    中移除, 永不回流军事牌堆; SIMPLIFICATION: 不单独建模公共阵型区, 被
    替换的实体阵型卡均入 removed(T13, T4 审查交办)。
    """
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=3, tactics="phalanx",
                tactics_public=True, hand_military=("fighting_band",)),
        _player("P1")))
    state = apply(state, PlayTactics("fighting_band"), db)
    p = state.players[0]
    assert p.tactics == "fighting_band"
    assert p.tactics_public is False
    assert state.military_discard == ()
    assert state.removed == ("phalanx",)


def test_replace_unpublic_tactics_also_removed() -> None:
    """未公开的实体旧阵型被替换同样入 removed(简化口径, 不回流军事牌堆)."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=3, tactics="phalanx",
                tactics_public=False, hand_military=("fighting_band",)),
        _player("P1")))
    state = apply(state, PlayTactics("fighting_band"), db)
    assert state.military_discard == ()
    assert state.removed == ("phalanx",)


def test_copy_tactics_apply() -> None:
    """复制: 扣 2 红点, 不消耗手牌, 成为自己的专属阵型(引用, 无实体卡)."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=3, hand_military=("fighting_band",)),
        _player("P1", tactics="phalanx", tactics_public=True)))
    state = apply(state, CopyTactics("phalanx"), db)
    p = state.players[0]
    assert p.military_actions == 1
    assert p.hand_military == ("fighting_band",)
    assert p.tactics == "phalanx"
    assert p.tactics_copied is True
    assert p.tactics_this_turn is True
    # 对手阵型不受影响
    assert state.players[1].tactics == "phalanx"


def test_replace_copied_tactics_no_phantom_card() -> None:
    """替换复制来的阵型: 仅丢弃引用, 不产生幻影卡入军事弃牌堆(卡牌守恒)."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=3, tactics="phalanx",
                tactics_copied=True, hand_military=("fighting_band",)),
        _player("P1", tactics="phalanx", tactics_public=True)))
    state = apply(state, PlayTactics("fighting_band"), db)
    p = state.players[0]
    assert p.tactics == "fighting_band"
    assert p.tactics_copied is False
    assert state.military_discard == ()


def test_replace_physical_tactics_when_copying() -> None:
    """复制时替换实体旧阵型: 旧阵型(实体卡)入 removed, 不入军事弃牌堆."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=3, tactics="fighting_band",
                tactics_public=True),
        _player("P1", tactics="phalanx", tactics_public=True)))
    state = apply(state, CopyTactics("phalanx"), db)
    p = state.players[0]
    assert p.tactics == "phalanx"
    assert p.tactics_copied is True
    assert state.military_discard == ()
    assert state.removed == ("fighting_band",)


def test_tactics_actions_unavailable_after_use() -> None:
    """打出后本回合不可再打出/复制; 再次打出抛 IllegalActionError."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=3,
                hand_military=("fighting_band", "phalanx")),
        _player("P1")))
    state = apply(state, PlayTactics("fighting_band"), db)
    assert PlayTactics("phalanx") not in legal_actions(db, state)
    with pytest.raises(IllegalActionError):
        apply(state, PlayTactics("phalanx"), db)


def test_action_serialization_round_trip() -> None:
    """新动作序列化/反序列化."""
    for action in (PlayTactics("fighting_band"), CopyTactics("phalanx")):
        assert action_from_dict(action_to_dict(action)) == action


# --- 回合开始强制公开与标志清零 ---------------------------------------------------


def test_reveal_tactics_at_turn_start() -> None:
    """回合开始阶段: 有未公开专属阵型的玩家必须公开(规则书 p3)."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=0),
        _player("P1", tactics="phalanx", tactics_public=False)))
    state = apply(state, PassTurn(), db)
    p1 = state.players[1]
    assert state.current_player == 1
    assert p1.tactics_public is True
    assert p1.tactics == "phalanx"


def test_tactics_this_turn_cleared_on_action_restore() -> None:
    """tactics_this_turn 在回合末行动点恢复时清零, 下一回合可再打出/复制."""
    db = _db()
    state = _state(players=(
        _player("P0", military_actions=0, tactics_this_turn=True),
        _player("P1")))
    state = apply(state, PassTurn(), db)
    p0 = state.players[0]
    assert p0.tactics_this_turn is False
    # 行动点已恢复为政体值
    assert p0.civil_actions == 4
    assert p0.military_actions == 2
