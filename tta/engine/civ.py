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
   拿破仑每类型 +2 等经 "strength" 键叠加于 army_strength 之上)。

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

_COLONY_TOKEN_KEYS = ("yellow_token", "blue_token")
"""殖民地永久效果中的一次性银行标记键(不参与 civ 合成)."""


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


def civ_values(db: CardDB, p: PlayerState) -> CivValues:
    """合成玩家当前文明数值, 顺序见模块 docstring."""
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


def discontent(db: CardDB, p: PlayerState) -> int:
    """不满 = max(0, 黄点轨道幸福需求 - 当前幸福)."""
    return max(0, happiness_required(p.yellow_bank) - civ_values(db, p).happiness)


def is_uprising(db: CardDB, p: PlayerState) -> bool:
    """起义判定: 不满人数超过空闲工人池."""
    return discontent(db, p) > p.worker_pool


def hand_limit_civil(db: CardDB, p: PlayerState) -> int:
    """内政手牌上限 = 内政行动数 + civil_hand_extra(奇迹/effects 加成)."""
    civ = civ_values(db, p)
    return civ.civil_actions + civ.civil_hand_extra
