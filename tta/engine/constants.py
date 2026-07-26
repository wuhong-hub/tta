"""引擎数值常量."""

MAX_STEPS = 100_000
"""单局最大步数(runner 防死循环上限; 超出说明引擎疑似死循环)."""

ROW_COSTS: tuple[int, ...] = (1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3)
"""卡牌列各位置拿牌白点费(0-4 号位 1 点, 5-9 号位 2 点, 10-12 号位 3 点)."""

FOOD_SHORTAGE_CULTURE_PENALTY = 4
"""食物消耗每缺 1 点损失的文化(turn 生产阶段与 events.economic_progress 共用,
T11 重复声明于 T13 收敛至此)."""
