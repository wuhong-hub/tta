"""版图轨道数值查询测试."""

import pytest

from tta.engine.tracks import (
    consumption_value,
    corruption_value,
    happiness_required,
    population_cost,
)


@pytest.mark.parametrize("bank,expected", [
    (18, 2), (17, 2), (16, 3), (15, 3), (14, 3), (13, 3),
    (12, 4), (11, 4), (10, 4), (9, 4), (8, 5), (7, 5),
    (6, 5), (5, 5), (4, 7), (3, 7), (2, 7), (1, 7),
])
def test_population_cost(bank: int, expected: int) -> None:
    # 区段边界(1 基位置): 1-2(费7), 3-4(费7), 5-6(费5), 7-8(费5),
    # 9-10(费4), 11-12(费4), 13-16(费3), 17-18(费2)
    assert population_cost(bank) == expected


def test_population_cost_empty_bank() -> None:
    with pytest.raises(ValueError):
        population_cost(0)


@pytest.mark.parametrize("bank", [19, 20, 25])
def test_yellow_bank_over_track_clamped(bank: int) -> None:
    # 殖民地永久效果/事件可给额外黄点(规则书 p10: 轨道填满后多余标记放到
    # 最右侧区域); 轨道查询按位置 18 区段处理, 不得抛 ValueError
    assert population_cost(bank) == 2
    assert consumption_value(bank) == 0
    assert happiness_required(bank) == 0


def test_yellow_bank_negative_still_raises() -> None:
    with pytest.raises(ValueError):
        population_cost(-1)


@pytest.mark.parametrize("bank,expected", [
    (18, 0), (17, 1), (16, 1), (15, 2), (14, 2), (13, 2),
    (12, 2), (11, 2), (10, 2), (9, 3), (8, 3), (7, 3),
    (6, 3), (5, 4), (4, 4), (3, 4), (2, 4), (1, 6), (0, 6),
])
def test_consumption(bank: int, expected: int) -> None:
    # 最左未覆盖格(位置 bank+1)所属区段的消耗值; 区段消耗(左→右): 6,4,4,3,3,2,2,1
    assert consumption_value(bank) == expected


@pytest.mark.parametrize("bank,expected", [
    (18, 0), (17, 0), (16, 1), (15, 1), (14, 1), (13, 1),
    (12, 2), (11, 2), (10, 3), (9, 3), (8, 4), (7, 4),
    (6, 5), (5, 5), (4, 6), (3, 6), (2, 7), (1, 7), (0, 8),
])
def test_happiness_required(bank: int, expected: int) -> None:
    # 最左被拿空区段的需求数; 全部被占则 0
    assert happiness_required(bank) == expected


@pytest.mark.parametrize("bank,expected", [
    (16, 0), (11, 0), (10, 2), (6, 2), (5, 4), (1, 4), (0, 6),
])
def test_corruption(bank: int, expected: int) -> None:
    assert corruption_value(bank) == expected
