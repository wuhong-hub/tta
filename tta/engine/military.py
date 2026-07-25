"""阵型与军力系统(规则书 p9 阵型牌节).

army_strength(db, p) 合成玩家军力:

1. 基础 = Σ 军事单位卡工人数 × 卡 strength(INFANTRY/CAVALRY/ARTILLERY/AIR
   各类别, 空军基础军力照计);
2. 阵型加成(有 tactics 时): 按 tactics_units 贪心组军——各类别单位按
   (strength 降序, 并列按 card_id) 排序, 依次填充阵型槽位; 每凑满一组
   (各类别数量全满足) → +tactics_strength; 引擎约定贪心即官方"总是以获得
   最大军力的方式组建"的确定性实现;
3. 旧式军队(规则书 p9): 组内任一单位的卡牌等级比阵型卡低 2 级或更多 →
   该组按 tactics_strength_outdated 计(数值较小的那个);
4. 空军(规则书 p9 与卡牌数值表 air_forces 5* 星注): 空军不能单独成军,
   不参与阵型槽位; 每支已组成的军队可加入 1 个空军单位使其阵型军力翻倍
   (旧式军队含空军只对较小的旧式军力翻倍); 空军单位数少于军队数时优先
   翻倍加成较高的组(最大军力组军原则)。

静态加成(领袖亚历山大每单位 +1、拿破仑每类型 +2、奇迹/政府 bonus)
不在本模块, 由 civ.py 经 effects.static_bonuses 叠加于 army_strength 之上。

draw_military(state, idx, count) 为军事牌堆抓牌的共用实现(事件效果与
回合末抓牌同一官方口径, 规则书 p7): 从军事牌堆顶抓 count 张入 idx 手;
牌堆空则切洗当前时代军事弃牌堆重置牌堆继续抓, 弃牌堆也空则抓不到;
时代 IV 无军事牌堆, 不抓。
"""

from dataclasses import replace

from tta.engine.enums import UNIT_CATEGORIES, Age, CardCategory
from tta.engine.model import CardDB, CardDefinition
from tta.engine.rng import rng_shuffle
from tta.engine.state import GameState, PlayerState, replace_player

_AGE_ORDER = (Age.A, Age.I, Age.II, Age.III)
"""时代等级序(IV 为终局标记, 卡牌不出现)."""

OUTDATED_AGE_GAP = 2
"""旧式军队判定: 单位比阵型卡低的时代级数阈值(规则书 p9 "低两级或更多")."""


def _age_index(age: Age) -> int:
    return _AGE_ORDER.index(age)


def army_strength(db: CardDB, p: PlayerState) -> int:
    """玩家当前军力 = 基础军力 + 阵型加成(组军规则见模块 docstring)."""
    base = 0
    pools: dict[CardCategory, list[CardDefinition]] = {}
    air_workers = 0
    for category in UNIT_CATEGORIES:
        units: list[CardDefinition] = []
        for card_id, workers in sorted(
                p.buildings.get(category.value, {}).items()):
            if workers <= 0:
                continue
            card = db.get(card_id)
            base += card.strength * workers
            if category is CardCategory.AIR:
                # 空军不能单独成军, 不参与阵型槽位(基础军力已计)
                air_workers += workers
                continue
            units.extend([card] * workers)
        # 贪心填充顺序: strength 降序, 并列按 card_id(确定性)
        units.sort(key=lambda c: (-c.strength, c.id))
        pools[category] = units

    if p.tactics is None:
        return base
    tactics = db.get(p.tactics)
    required = {
        CardCategory[name]: count
        for name, count in tactics.tactics_units.items()
    }

    group_values: list[int] = []
    while all(len(pools[cat]) >= n for cat, n in required.items()):
        group: list[CardDefinition] = []
        for cat, n in required.items():
            group.extend(pools[cat][:n])
            del pools[cat][:n]
        outdated = any(
            _age_index(tactics.age) - _age_index(card.age) >= OUTDATED_AGE_GAP
            for card in group
        )
        group_values.append(
            tactics.tactics_strength_outdated if outdated
            else tactics.tactics_strength)

    # 空军翻倍: 每支军队至多加入 1 个空军单位; 优先翻倍加成较高的组
    bonus = sum(group_values)
    group_values.sort(reverse=True)
    bonus += sum(group_values[:air_workers])
    return base + bonus


def units_strength(
    db: CardDB, p: PlayerState, unit_card_ids: tuple[str, ...],
) -> int:
    """所选军事单位(卡 id 可重复, 每个条目 = 1 个单位)按 p 当前阵型组军的军力.

    用于殖民牺牲结算(规则书 p7): 被挑出的军事单位可根据玩家当前的阵型
    组成军队, 组军方式与军力等级计算无关(独立贪心组军)。实现: 构造仅含
    所选单位的伪 PlayerState 复用 army_strength。
    """
    buildings: dict[str, dict[str, int]] = {}
    for card_id in unit_card_ids:
        category = db.get(card_id).category.value
        slots = buildings.setdefault(category, {})
        slots[card_id] = slots.get(card_id, 0) + 1
    return army_strength(db, replace(p, buildings=buildings))


def draw_military(state: GameState, idx: int, count: int) -> GameState:
    """从军事牌堆抓 count 张入 idx 手(牌堆空切洗军事弃牌堆; 时代 IV 不抓).

    官方口径(规则书 p7): 抓到军事牌堆最后一张时, 切洗当前时代的军事
    弃牌堆重置牌堆继续抓; 弃牌堆也空则抓不到。事件效果与回合末抓牌
    共用本实现。
    """
    if state.age is Age.IV or count <= 0:
        return state
    deck = list(state.military_deck)
    discard = list(state.military_discard)
    hand = list(state.players[idx].hand_military)
    rng = state.rng_state
    for _ in range(count):
        if not deck:
            if not discard:
                break
            rng, deck = rng_shuffle(rng, discard)
            discard = []
        hand.append(deck.pop(0))
    state = replace(state, military_deck=tuple(deck),
                    military_discard=tuple(discard), rng_state=rng)
    return replace_player(
        state, idx, replace(state.players[idx], hand_military=tuple(hand)))
