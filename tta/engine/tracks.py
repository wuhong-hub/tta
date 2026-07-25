"""玩家版图轨道数值查询(官方规则).

黄点人口轨道 18 格, 左→右 8 个区段; 蓝点供给区 16 格 3 段。
位置采用 1 基: 位置 1 为最左格。token 从右端取出(增人口), 从左端填入。
"""

from dataclasses import dataclass

YELLOW_SPACES = 18
BLUE_SPACES = 16


@dataclass(frozen=True)
class YellowSection:
    """黄点轨道区段."""

    happiness_req: int   # 该区段被拿空时的幸福需求
    spaces: int
    pop_cost: int        # 增人口食物费
    consumption: int     # 食物消耗(正值)


# 左→右: 需求 8→1
YELLOW_SECTIONS: tuple[YellowSection, ...] = (
    YellowSection(8, 2, 7, 6),
    YellowSection(7, 2, 7, 4),
    YellowSection(6, 2, 5, 4),
    YellowSection(5, 2, 5, 3),
    YellowSection(4, 2, 4, 3),
    YellowSection(3, 2, 4, 2),
    YellowSection(2, 4, 3, 2),
    YellowSection(1, 2, 2, 1),
)

# 蓝点供给区: 按剩余 token 数分档的腐败值(正值), (下限, 值) 降序
_CORRUPTION_TIERS: tuple[tuple[int, int], ...] = ((11, 0), (6, 2), (1, 4), (0, 6))


def _yellow_section_at(position: int) -> YellowSection:
    """返回 1 基位置所属区段."""
    left = 1
    for sec in YELLOW_SECTIONS:
        if left <= position < left + sec.spaces:
            return sec
        left += sec.spaces
    raise ValueError(f"position out of range: {position}")


def _clamp_yellow(yellow_bank: int) -> int:
    """黄点银行钳制到轨道格数.

    殖民地永久效果/事件可给玩家额外黄点, 银行可超过轨道格数(规则书 p10:
    轨道填满后多余标记放到最右侧区域); 轨道查询按最右侧区段处理。
    """
    return min(yellow_bank, YELLOW_SPACES)


def population_cost(yellow_bank: int) -> int:
    """增人口食物费 = 最右被占用区段下方数字; 超过轨道按位置 18 区段."""
    if yellow_bank <= 0:
        raise ValueError("yellow bank is empty")
    return _yellow_section_at(_clamp_yellow(yellow_bank)).pop_cost


def consumption_value(yellow_bank: int) -> int:
    """食物消耗 = 最左未覆盖格所属区段的消耗值; 全覆盖(含超额)为 0."""
    if yellow_bank >= YELLOW_SPACES:
        return 0
    return _yellow_section_at(yellow_bank + 1).consumption


def happiness_required(yellow_bank: int) -> int:
    """幸福需求 = 最左被整体拿空区段的需求数; 无则(含超额)0.

    区段整体拿空 <=> 该区段最左格位置 > yellow_bank.
    """
    yellow_bank = _clamp_yellow(yellow_bank)
    left = 1
    for sec in YELLOW_SECTIONS:
        if left > yellow_bank:  # 该区段整体已空
            return sec.happiness_req
        left += sec.spaces
    return 0


def corruption_value(blue_bank: int) -> int:
    """腐败 = 剩余 token 数对应档位的负值绝对值.

    档位: >=11 -> 0; 6-10 -> 2; 1-5 -> 4; 0 -> 6.
    """
    if blue_bank < 0:
        raise ValueError(f"blue bank out of range: {blue_bank}")
    for min_bank, value in _CORRUPTION_TIERS:
        if blue_bank >= min_bank:
            return value
    raise AssertionError("unreachable")
