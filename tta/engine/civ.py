"""文明数值合成系统: 科学/文化/军力/幸福/行动数等衍生值.

合成顺序(civ_values):
1. 政体 GovernmentStats(civil_actions / military_actions / urban_limit
   + bonus dict) 为基础;
2. 城市建筑(LAB / TEMPLE / LIBRARY / THEATER / ARENA)按工人数 ×
   urban_produces 累加 science / culture / happiness;
3. 军力 = military.army_strength(单位基础 + 阵型加成, 见 military.py)
   + 静态加成(政体/奇迹/领袖/特殊科技的 "strength" 键);
4. 已完成奇迹 wonders 的 wonder_bonus 同 bonus 语义累加;
5. 殖民地 territory_permanent 同语义累加(yellow_token/blue_token 为
   获得时一次性银行调整, 除外);
6. effects.static_bonuses 叠加领袖/特殊科技静态加成(亚历山大每单位 +1、
   拿破仑每类型 +2 等经 "strength" 键叠加于 army_strength 之上);
7. 条约静态/被动加成(P2-T10, pact_bonuses; 仅当 civ_values 调用给出
   players/index 时叠加)。

收益键映射: "science" -> science_rate, "culture" -> culture_rate,
"strength" -> strength, "happiness" -> happiness, "civil_actions" /
"military_actions" / "colonization" / "civil_hand_extra" /
"military_hand_extra" -> 同名值; 未映射的键忽略。

截断(官方规则): happiness 限制在 [0, 8]; science_rate / culture_rate /
strength 下限 0(负增速视作 0)。
"""

from dataclasses import dataclass

from tta.engine import effects, military
from tta.engine.enums import URBAN_CATEGORIES
from tta.engine.model import CardDB
from tta.engine.state import PlayerState
from tta.engine.tracks import happiness_required

MAX_HAPPINESS = 8
"""笑脸总数上限(官方规则 0-8)."""

FACEDOWN_WONDER_CULTURE = 2
"""翻面(面朝下)奇迹的文化增速(ravages_of_time: 效果失效, 转为生产 2 文化)."""

_COLONY_TOKEN_KEYS = ("yellow_token", "blue_token")
"""殖民地永久效果中的一次性银行标记键(不参与 civ 合成)."""

PACT_SIDE_A = "A"
PACT_SIDE_B = "B"

PACT_STATIC_BONUSES: dict[str, tuple[dict[str, int], dict[str, int]]] = {
    # 卡 id -> (A 侧加成, B 侧加成); 对称条约两侧相同。
    # 卡牌数值表 v1.09 p3 条约表; 键语义与 civ 收益键映射一致。
    # open_borders 的"攻击者 +2 军力"条件加成不入表(politics 攻击快照处理);
    # international_trade_agreement A 侧 +1 资源生产不入表(turn 生产钩子);
    # trade_routes_agreement / scientific_cooperation 为每回合选择类,
    # P3-DEFERRED(卡 text 保留完整描述), 无静态加成。
    "open_borders_agreement": (
        {"military_actions": 1}, {"military_actions": 1}),
    "acceptance_of_supremacy": ({"culture": 1}, {"culture": -1}),
    "international_trade_agreement": ({}, {"science": 1}),
    "promise_of_military_protection": (
        {"culture": 1}, {"strength": 4, "culture": -1}),
    "international_tourism": ({}, {}),  # 按对方已完成奇迹数, 见 pact_bonuses
    "loss_of_sovereignty": ({"happiness": 2}, {"happiness": -2}),
    "military_alliance": ({"strength": 3}, {"strength": 3}),
    "peace_treaty": ({"happiness": 1}, {"happiness": 1}),
}
"""条约静态/被动加成表(P2-T10): (A 侧, B 侧) 收益键 dict."""

PACT_INTERNATIONAL_TOURISM = "international_tourism"
"""国际旅游: 对方每拥有 1 个已完成奇迹, 本方 +1 文化增速."""


def pact_bonuses(players: tuple[PlayerState, ...], idx: int) -> dict[str, int]:
    """玩家 idx 生效中条约的静态/被动加成(P2-T10, 卡牌数值表 p3 条约表).

    条约缔约双方 pacts 各录 (卡 id, 本方侧); 国际旅游按缔约对方(同录同一
    卡 id 的另一玩家)已完成奇迹数计文化增速。
    """
    bonus: dict[str, int] = {}
    for card_id, side in players[idx].pacts:
        side_a, side_b = PACT_STATIC_BONUSES.get(card_id, ({}, {}))
        _add_all(bonus, side_a if side == PACT_SIDE_A else side_b)
        if card_id == PACT_INTERNATIONAL_TOURISM:
            partner = _pact_partner(players, idx, card_id)
            if partner is not None:
                _add_all(bonus, {"culture": len(players[partner].wonders)})
    return bonus


def _pact_partner(
    players: tuple[PlayerState, ...], idx: int, card_id: str,
) -> int | None:
    """同录同一条约卡 id 的另一玩家座位(缔约对方); 无则 None."""
    for j, other in enumerate(players):
        if j != idx and any(cid == card_id for cid, _ in other.pacts):
            return j
    return None


@dataclass(frozen=True)
class CivValues:
    """文明衍生数值(全 int, 由 civ_values 合成)."""

    science_rate: int
    culture_rate: int
    strength: int
    happiness: int
    civil_actions: int
    military_actions: int
    urban_limit: int
    civil_hand_extra: int
    military_hand_extra: int
    colonization: int


def _add_all(bonus: dict[str, int], gains: dict[str, int], scale: int = 1) -> None:
    """把 gains 的各键值 × scale 累加进 bonus."""
    for key, value in gains.items():
        bonus[key] = bonus.get(key, 0) + value * scale


def civ_values(
    db: CardDB,
    p: PlayerState,
    players: tuple[PlayerState, ...] | None = None,
    index: int | None = None,
) -> CivValues:
    """合成玩家当前文明数值, 顺序见模块 docstring.

    players/index 同时给出时叠加条约静态/被动加成(P2-T10, pact_bonuses);
    缺省(仅 db, p)不含条约加成(单玩家口径, 测试与无上下文调用用)。
    """
    government = db.get(p.government).government
    if government is None:
        msg = f"政体卡 {p.government!r} 缺少 government 数值"
        raise ValueError(msg)

    bonus: dict[str, int] = {}
    _add_all(bonus, government.bonus)

    for category in URBAN_CATEGORIES:
        for card_id, workers in p.buildings.get(category.value, {}).items():
            if workers > 0:
                _add_all(bonus, db.get(card_id).urban_produces, scale=workers)

    for card_id in p.wonders:
        if card_id in p.wonders_facedown:
            # 翻面奇迹(ravages_of_time): 效果失效, 转为 +2 文化增速
            _add_all(bonus, {"culture": FACEDOWN_WONDER_CULTURE})
        else:
            _add_all(bonus, db.get(card_id).wonder_bonus)

    # 殖民地永久效果(yellow_token/blue_token 为获得时一次性银行调整,
    # 不入合成, 见 politics._grant_colony); 可含负值(如 vast_territory)
    for card_id in p.colonies:
        permanent = db.get(card_id).territory_permanent
        _add_all(bonus, {
            key: value for key, value in permanent.items()
            if key not in _COLONY_TOKEN_KEYS
        })

    _add_all(bonus, effects.static_bonuses(db, p))

    if players is not None and index is not None:
        # 条约静态/被动加成(P2-T10)
        _add_all(bonus, pact_bonuses(players, index))

    # 军力 = army_strength(单位基础 + 阵型加成) + 静态加成("strength" 键)
    strength = military.army_strength(db, p) + bonus.get("strength", 0)

    return CivValues(
        science_rate=max(0, bonus.get("science", 0)),
        culture_rate=max(0, bonus.get("culture", 0)),
        strength=max(0, strength),
        happiness=min(MAX_HAPPINESS, max(0, bonus.get("happiness", 0))),
        civil_actions=government.civil_actions + bonus.get("civil_actions", 0),
        military_actions=government.military_actions + bonus.get("military_actions", 0),
        urban_limit=government.urban_limit,
        civil_hand_extra=bonus.get("civil_hand_extra", 0),
        military_hand_extra=bonus.get("military_hand_extra", 0),
        colonization=bonus.get("colonization", 0),
    )


def discontent(
    db: CardDB,
    p: PlayerState,
    players: tuple[PlayerState, ...] | None = None,
    index: int | None = None,
) -> int:
    """不满 = max(0, 黄点轨道幸福需求 - 当前幸福)."""
    happiness = civ_values(db, p, players, index).happiness
    return max(0, happiness_required(p.yellow_bank) - happiness)


def is_uprising(
    db: CardDB,
    p: PlayerState,
    players: tuple[PlayerState, ...] | None = None,
    index: int | None = None,
) -> bool:
    """起义判定: 不满人数超过空闲工人池."""
    return discontent(db, p, players, index) > p.worker_pool


def hand_limit_civil(db: CardDB, p: PlayerState) -> int:
    """内政手牌上限 = 内政行动数 + civil_hand_extra(奇迹/effects 加成)."""
    civ = civ_values(db, p)
    return civ.civil_actions + civ.civil_hand_extra
