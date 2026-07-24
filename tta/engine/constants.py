"""引擎数值常量.

所有标注 RULES-AUDIT 的数值为 P0 骨架取值, P2 需对照官方规则书核对修正.
"""

ROW_SLOTS = 13
ROW_COSTS: tuple[int, ...] = (1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3)  # RULES-AUDIT: 各格拿牌白点
BASE_HAPPINESS = 2          # RULES-AUDIT: 基础满意容量
FOOD_PER_WORKER = 1         # RULES-AUDIT: 每工人每回合食物消耗
POP_FOOD_COST = 2           # RULES-AUDIT: 增加 1 人口的食物花费
STARVATION_CULTURE = 4      # RULES-AUDIT: 每短缺 1 食物损失的文化
INITIAL_YELLOW = 25         # RULES-AUDIT: 每人黄点总数(人口守恒基准)
INITIAL_FOOD = 2            # RULES-AUDIT: 开局食物
INITIAL_MATERIALS = 2       # RULES-AUDIT: 开局资源
MAX_STEPS = 100_000         # 单局动作数上限(防引擎死循环)
