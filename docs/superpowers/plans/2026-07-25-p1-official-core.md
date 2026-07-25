# P1: 官方规则核心重铸 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 P0 骨架引擎重铸为符合官方规则的核心引擎：Token 资源模型（黄点人口轨道/蓝点供给区/卡上储存）、官方回合状态机、文明数值与效果框架，并录入全部官方内政牌（初始科技 + A/I/II/III 四时代，含领袖/奇迹/行动牌）。

**Architecture:** 沿用 P0 单向依赖与不可变状态。新增 `tracks.py`（版图轨道查询）、`economy.py`（资源支付）、`civ.py`（文明数值）、`effects.py`（卡牌特殊效果钩子）、`turn.py`（回合机）。军事系统（军事牌堆/政治阶段/事件/侵略/战争/条约/阵型/殖民）整体推迟到 P2，相关引擎路径为 no-op，卡牌互动效果标 `P2-DEFERRED`。

**Tech Stack:** Python 3.12（语法底线 3.10)、uv、pytest、ruff；零运行时第三方依赖。

**数据来源（全部已在本仓库）:**
- 中文官方规则书：`through-the-ages-new-story-rules-zh-s.pdf`（规则权威）
- 英文卡牌数值表：`Through_the_Ages_-_A_New_Story_of_Civilization_-_Card_Reference_v1.09.pdf`（卡牌数据权威，4 页）
- 研究汇总：`docs/research/tta-official-data.md`（轨道数值等，含可信度标注）

## Global Constraints

- Python `requires-python = ">=3.10"`；4 空格缩进；所有函数签名带类型注解；frozen dataclass；嵌套 dict 修改前整体复制
- engine 包不得 import `tta.agents` / `tta.orchestrator` / `tta.cli` / `tta.cards` 中任何模块
- RNG 一律走 `tta/engine/rng.py` 纯函数；引擎内禁止 `import random`；**任何引擎中途随机性（如洗牌）必须消费 `GameState.rng_state`**（保持确定性链）
- `apply(state, action, db)` 返回新状态；非法动作抛 `IllegalActionError`
- 测试命令：`uv run pytest <path> -v`;lint:`uv run ruff check tta tests`；每次 commit 前全量测试 + lint
- 本阶段清除全部 P0 的 RULES-AUDIT 标记；数值以规则书与卡牌数值表为准
- 军事相关延后到 P2 的，代码中用注释 `# P2-DEFERRED: <内容>` 标注；军事手牌恒空、政治阶段 no-op、抓军事牌 no-op
- P0 的 `tta/cards/minimal.py` 及其测试在本阶段删除（Task 13)，由正式牌库取代；黄金回归指纹在 Task 14 重建
- 支付/找零/储存的确定性简化（见 Task 4）是**有意的引擎约定**，在模块 docstring 中声明，后续不视为 bug

## 关键规则摘要（实现依据，全部来自规则书，已核对）

- 卡牌列 13 格：费用 5×1 / 4×2 / 4×3（左→右）；奇迹牌额外 +1 白点/每已完成奇迹
- 回合开始：弃最左 N 张（2/3/4 人 → 3/2/1 张）→ 左移 → 从当前时代牌堆补满；**第一轮不补牌**
- 时代 A 于第一次补牌时结束：剩余牌左移 → 用 A 堆补空位 → 弃掉 A 堆余牌 → 启用 I 堆
- 时代 I/II/III 于当前牌堆最后一张放上牌列时结束：过期（弃更老时代的手牌/领袖/未完成奇迹[蓝点退回供给区]/条约）→ **每人从黄点银行损失 2 黄点** → 切洗新牌堆继续补牌
- 时代 III 牌堆尽 → 时代 IV：若轮到起始玩家回合则本轮为最后轮，否则下轮为最后轮；终局计分（P1 无事件，仅文化）
- 黄点轨道 18 格 8 区段（左→右，需求/格数/增人口费/消耗）：(8,2,7,6)(7,2,7,4)(6,2,5,4)(5,2,5,3)(4,2,4,3)(3,2,4,2)(2,4,3,2)(1,2,2,1)
- 蓝点供给区 16 格 3 段（5+5+6)：腐败值：银行 ≥11→0;6-10→2;1-5→4;0→6
- 增人口费 = 最右被占用区段数字；消耗 = 最左未覆盖负值；幸福需求 = 最左被拿空区段数字；不满 = 需求 − 幸福（下限 0)；不满 > 空闲工人 → 起义跳过生产
- 生产阶段顺序：科技/文化按增速计分 → 腐败（资源支付，不足用食物补）→ 食物生产（每农场工人 1 蓝点，供给不足时高等级优先）→ 食物消耗（每缺 1 食物 −4 文化，文化下限 0)→ 资源生产（同食物）
- 升级付两张牌造价**差值**；支付可从高等级卡移 1 蓝点到同类型低等级卡用差值找零；可超额支付后从供给区找零
- 手牌上限：内政牌 < 总内政行动点（+亚历山大图书馆等加成）；军事牌 ≤ 总军事行动点（回合末弃多余）
- 第一回合：玩家依次只有 1/2/3/4 白点、无红点、只能拿牌、不抓军事牌
- 拿牌限制：手牌/场上已有同名科技牌不可再拿；已拥有过同时代领袖不可再拿该时代领袖；有未完成奇迹不可拿奇迹牌
- 回合末：弃多余军事牌 → 起义检定 → 生产 → 抓军事牌（剩余红点，≤3)→ 恢复全部行动点
- 行动卡引导的另一行动不耗行动点（只付费用）；打行动卡本身 1 白点
- 政府牌：和平演变 = 1 白点 + 高科技费；革命 = 全部剩余白点 + 低科技费

---

### Task 1: 版图轨道查询（tracks.py)

**Files:**
- Create: `tta/engine/tracks.py`
- Test: `tests/engine/test_tracks.py`

**Interfaces:**
- Produces:
  - `population_cost(yellow_bank: int) -> int` — 最右被占用区段的增人口食物费；`yellow_bank == 0` 抛 `ValueError`
  - `consumption_value(yellow_bank: int) -> int` — 食物消耗（正数）;18 → 0
  - `happiness_required(yellow_bank: int) -> int` — 幸福需求；无区段被拿空 → 0
  - `corruption_value(blue_bank: int) -> int` — ≥11→0;6-10→2;1-5→4;0→6
- 轨道数据（左→右 8 区段）：需求 8..1，格数 (2,2,2,2,2,2,4,2)，增人口费 (7,7,5,5,4,4,3,2)，消耗 (6,4,4,3,3,2,2,1)

- [ ] **Step 1: 写失败测试**

```python
# tests/engine/test_tracks.py
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
```

注：以上期望值按区段边界（1 基位置）推导，实现者若发现期望值与区段数据矛盾，停下来报告，不要擅自改测试或数据。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/engine/test_tracks.py -v`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 实现 tracks.py**

```python
# tta/engine/tracks.py
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

# 蓝点供给区: 3 段(5+5+6), 各段最左格腐败值(正值)
_BLUE_SECTIONS: tuple[tuple[int, int], ...] = ((5, 6), (5, 4), (6, 2))


def _yellow_section_at(position: int) -> YellowSection:
    """返回 1 基位置所属区段."""
    left = 1
    for sec in YELLOW_SECTIONS:
        if left <= position < left + sec.spaces:
            return sec
        left += sec.spaces
    raise ValueError(f"position out of range: {position}")


def population_cost(yellow_bank: int) -> int:
    """增人口食物费 = 最右被占用区段下方数字."""
    if yellow_bank <= 0:
        raise ValueError("yellow bank is empty")
    return _yellow_section_at(yellow_bank).pop_cost


def consumption_value(yellow_bank: int) -> int:
    """食物消耗 = 最左未覆盖格所属区段的消耗值; 全覆盖为 0."""
    if yellow_bank >= YELLOW_SPACES:
        return 0
    return _yellow_section_at(yellow_bank + 1).consumption


def happiness_required(yellow_bank: int) -> int:
    """幸福需求 = 最左被整体拿空区段的需求数; 无则 0.

    区段整体拿空 <=> 该区段最左格位置 > yellow_bank.
    """
    left = 1
    for sec in YELLOW_SECTIONS:
        if left > yellow_bank:  # 该区段整体已空
            return sec.happiness_req
        left += sec.spaces
    return 0


def corruption_value(blue_bank: int) -> int:
    """腐败 = 最左未覆盖负值的绝对值; 全覆盖为 0."""
    if blue_bank >= BLUE_SPACES:
        return 0
    position = blue_bank + 1
    left = 1
    for spaces, value in _BLUE_SECTIONS:
        if left <= position < left + spaces:
            return value
        left += spaces
    raise ValueError(f"position out of range: {position}")
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/engine/test_tracks.py -v`
Expected: 全 PASS。注意 `happiness_required(17)` 按实现为 0（区段 17-18 未整体空），若测试期望与此冲突，以区段数据推演为准并报告。

- [ ] **Step 5: Commit**

```bash
git add tta/engine/tracks.py tests/engine/test_tracks.py
git commit -m "feat(engine): 黄点/蓝点版图轨道数值查询"
```

---

### Task 2: 卡牌模型重构（enums + model)

**Files:**
- Modify: `tta/engine/enums.py`（重写）
- Modify: `tta/engine/model.py`（重写）
- Test: `tests/engine/test_model.py`（重写）

**Interfaces:**
- Produces:
  - `CardCategory`: `FARM, MINE, LAB, TEMPLE, LIBRARY, THEATER, ARENA, INFANTRY, CAVALRY, ARTILLERY, AIR, GOVERNMENT, LEADER, WONDER, ACTION, SPECIAL`
  - `URBAN_CATEGORIES = frozenset({LAB, TEMPLE, LIBRARY, THEATER, ARENA})`;`UNIT_CATEGORIES = frozenset({INFANTRY, CAVALRY, ARTILLERY, AIR})`;`WORKER_CATEGORIES = URBAN | UNIT | {FARM, MINE}`（可放工人的类别；建筑槽位直接以 category.value 为键，`BuildingType` 删除）
  - `SpecialType`: `LAW, WARFARE, EXPLORATION, CONSTRUCTION`（特殊科技子类）
  - `GovernmentStats(civil_actions, military_actions, urban_limit, bonus: dict[str, int])`
  - `CardDefinition`（字段见下）;`CardDB(cards, initial_tableau, initial_government)` + `CardDB.deck_for(age: Age, num_players: int) -> tuple[str, ...]`（按 quantities 组牌）
- 说明：此任务会打破 P0 旧模型，属预期。**本任务必须同步清理旧产物，保证提交时 `uv run pytest -q` 全绿**:
  - 删除：`tta/cards/minimal.py`、`tests/cards/test_minimal.py`、`tests/engine/test_legal.py`、`tests/engine/test_apply.py`、`tests/engine/test_turn.py`、`tests/engine/test_setup.py`、`tests/orchestrator/test_runner.py`、`tests/cli/test_cli.py`、`tests/property/test_invariants.py`、`tests/golden/test_golden_game.py`
  - `tta/cli/main.py` 暂改为打印 `"P1 重构中， selfplay 暂不可用"`(Task 13/14 恢复）;`tta/agents/`、`tta/orchestrator/runner.py`、`tta/replay/` 保持不动（它们与卡牌模型无耦合）
  - 保留：`tests/engine/test_tracks.py`、`tests/engine/test_rng.py`；本任务重写 `tests/engine/test_model.py`
  - 后续任务逐步重建覆盖：T3 重写 test_state、T6 重写动作测试、T8 重写回合测试、T13 重写 test_setup 与 CLI、T14 重写属性/黄金/运行器测试

```python
# CardDefinition 字段(实现依据,测试逐项断言)
id: str
name: str                       # 中文名
name_en: str                    # 英文名(对照 Card Reference)
age: Age
deck: DeckType
category: CardCategory
text: str = ""                  # 效果文本(人类/LLM 阅读)
cost_science: int = 0           # 科技费(政府牌为和平演变费)
cost_science_revolution: int = 0  # 政府牌革命费
build_cost: int = 0             # 放置 1 工人的资源费
token_value: int = 0            # 农场/矿场: 每蓝点的食物/资源价值
urban_produces: dict[str, int] = field(default_factory=dict)  # 城市建筑每工人产出(science/culture/happiness)
strength: int = 0               # 军事单位每工人军力
government: GovernmentStats | None = None
special_type: SpecialType | None = None
wonder_stages: tuple[int, ...] = ()   # 奇迹各阶段资源费
wonder_bonus: dict[str, int] = field(default_factory=dict)  # 奇迹完成后静态文明加成
handler: str = ""                     # effects.py 特殊效果处理器名, 空=无
quantities: tuple[int, int, int] = (0, 0, 0)     # (2p, 3p, 4p) 张数
```

- [ ] **Step 1: 写失败测试** — 断言：16 个类别齐全；URBAN/UNIT/WORKER 集合正确；`deck_for` 按人数组牌（2p 取 quantities[0] 份）；GovernmentStats 默认 bonus `{}`；CardDefinition 默认值。

- [ ] **Step 2: 运行确认失败** — `uv run pytest tests/engine/test_model.py -v` → FAIL

- [ ] **Step 3: 实现 enums.py / model.py 重写**

- [ ] **Step 4: 运行确认通过** — `uv run pytest tests/engine/test_model.py tests/engine/test_tracks.py -v` PASS

- [ ] **Step 5: Commit** — `git commit -m "feat(engine): 卡牌模型重构(16 类别/政府/奇迹/特殊科技)"`

---

### Task 3: 状态模型重构（state.py)

**Files:**
- Modify: `tta/engine/state.py`（重写 PlayerState/GameState)
- Test: `tests/engine/test_state.py`（重写）

**Interfaces:**
- Produces（后续任务全部依赖）:

```python
@dataclass(frozen=True)
class PendingEffect:
    """行动卡等待结算的子行动."""
    kind: str        # "build_farm_mine" | "build_urban" | "wonder_stage"
    discount: int    # 资源费折扣

@dataclass(frozen=True)
class PlayerState:
    name: str
    culture: int = 0
    science: int = 0
    yellow_bank: int = 18
    blue_bank: int = 16
    worker_pool: int = 1
    buildings: dict[str, dict[str, int]] = field(default_factory=dict)  # category.value -> {card_id: workers}
    card_tokens: dict[str, int] = field(default_factory=dict)           # 农场/矿场 card_id -> 蓝点数
    developed: tuple[str, ...] = ()
    hand_civil: tuple[str, ...] = ()
    hand_military: tuple[str, ...] = ()        # P2-DEFERRED: 恒空
    government: str = "despotism"
    leader: str | None = None
    leader_ages: tuple[str, ...] = ()          # 曾拥有领袖的时代(Age.value)
    wonder_progress: tuple[str, int] | None = None   # (card_id, 已完成阶段数)
    wonders: tuple[str, ...] = ()              # 已完成奇迹
    civil_actions: int = 0
    military_actions: int = 0
    turn_discounts: dict[str, int] = field(default_factory=dict)  # 回合内折扣, 如 {"unit_build": 1}

@dataclass(frozen=True)
class GameState:
    round: int
    age: Age
    current_player: int          # 0 号位 = 起始玩家
    card_row: tuple[str | None, ...]
    civil_deck: tuple[str, ...]
    future_decks: dict[str, tuple[str, ...]]
    discard: tuple[str, ...]
    removed: tuple[str, ...]
    players: tuple[PlayerState, ...]
    rng_state: int
    pending: tuple[PendingEffect, ...] = ()
    last_round: bool = False
    terminal: bool = False
    final_scores: tuple[int, ...] | None = None
```

- 保留 `workers_total`、`replace_player`、`to_dict/from_dict`、`state_hash`（序列化覆盖全部新字段，含 pending/turn_discounts/wonder_progress 的 None 往返）

- [ ] **Step 1-5:** TDD：测试断言序列化往返（含 None wonder_progress、非空 pending、turn_discounts)、hash 稳定性、workers_total；实现；通过；commit `feat(engine): 状态模型重构(token 轨道/卡上储存/奇迹/领袖/pending)`

---

### Task 4: 资源支付引擎（economy.py)

**Files:**
- Create: `tta/engine/economy.py`
- Test: `tests/engine/test_economy.py`

**Interfaces:**
- Consumes: `CardDefinition.token_value`、`PlayerState.card_tokens`/`blue_bank`
- Produces:
  - `food_total(db: CardDB, p: PlayerState) -> int` / `resource_total(db, p) -> int` — Σ 卡上蓝点 × token_value（农场=食物，矿场=资源）
  - `pay(db: CardDB, p: PlayerState, kind: str, amount: int) -> PlayerState` — `kind` 为 `"food"` 或 `"resource"`；确定性支付（见下算法）;`amount > total` 抛 `ValueError`（合法性由 legal 保证）
  - `gain_tokens(db: CardDB, p: PlayerState, kind: str, count: int) -> PlayerState` — 从供给区向该类型**最低等级**卡放 count 个蓝点（供给不足则尽力；卡不存在则放弃）——用于行动卡收益等
  - `produce(db: CardDB, p: PlayerState, kind: str) -> PlayerState` — 生产：该类型每张有工人的卡各得 1 蓝点；供给不足时**高等级卡优先**（token_value 降序）

**确定性支付算法（引擎约定，写入模块 docstring):**
1. 反复从该类型卡中取 token_value 最小（并列取 card_id 字典序最小）的 1 个蓝点，直到累计 ≥ amount
2. 若超付（取出的蓝点价值 > 剩余应付额）：找零 = 超付额，从供给区向该类型最低等级卡放蓝点，每点抵该卡 token_value，直到找零尽或供给空；找不零的部分损失
3. 返回新 PlayerState（不改动入参）

- [ ] **Step 1: 写失败测试**（关键用例）

```python
# 夹具: 农场 agriculture(token_value=1) 2 蓝点, irrigation(token_value=2) 1 蓝点
# food_total == 4
# pay food 1 -> agriculture 剩 1 蓝点, irrigation 不动
# pay food 3 -> 先取 agriculture×2 (付2), 再取 irrigation (付2 超付0)... 恰好: agriculture 0, irrigation 0
# 超付用例: 仅 irrigation 1 蓝点(值2), pay food 1, blue_bank=3
#   -> irrigation 0 蓝点; 找零 1 -> 向最低等级农场(agriculture,值1)放 1 蓝点, blue_bank 2
# 找零损失用例: 同上但 blue_bank=0 -> irrigation 0, agriculture 0, 无补偿
# produce: agriculture 2 工人 irrigation 1 工人, blue_bank=2
#   -> 高等级优先: irrigation 得 1, agriculture 得 1(而非 2), blue_bank 0
# gain_tokens: 供给 16 -> 向最低等级矿场放 2 点
```

- [ ] **Step 2-5:** 确认失败 → 实现 → 通过 → commit `feat(engine): 资源支付与生产引擎(确定性找零)`

---

### Task 5: 文明数值系统（civ.py)

**Files:**
- Create: `tta/engine/civ.py`
- Test: `tests/engine/test_civ.py`

**Interfaces:**
- Produces:
  - `CivValues` frozen dataclass:`science_rate, culture_rate, strength, happiness, civil_actions, military_actions, urban_limit, civil_hand_extra, military_hand_extra, colonization`（全 int)
  - `civ_values(db: CardDB, p: PlayerState) -> CivValues` — 合成顺序：政府（含 bonus dict)→ 城市建筑每工人 urban_produces（实验室/寺庙/图书馆/剧院/竞技场）→ 军事单位每工人 strength → 已完成奇迹 wonder_bonus → effects.py 的领袖/特殊科技静态加成钩子 `static_bonuses(db, p) -> dict`
  - `discontent(db: CardDB, p: PlayerState) -> int` — max(0, happiness_required − happiness)
  - `is_uprising(db, p) -> bool` — discontent > worker_pool
  - `hand_limit_civil(db, p) -> int` — civ.civil_actions + civ.civil_hand_extra
- effects.py 在本任务仅建空注册表骨架（`static_bonuses` 返回政府/奇迹之外的领袖与特殊科技加成；无领袖时返回 {}),Task 9+ 填充

- [ ] **Step 1-5:** TDD（用例：专制+2农业+1哲学 → science_rate=1, civil=4, military=2, urban_limit=2；寺庙 1 工人 → happiness 包含其 urban_produces；完成金字塔 → civil_actions+1)；commit `feat(engine): 文明数值合成系统`

---

### Task 6: 动作系统重构（actions + legal + apply 动作分支）

**Files:**
- Modify: `tta/engine/actions.py`（重写）、`tta/engine/legal.py`（重写）、`tta/engine/apply.py`（重写动作分支，回合推进留 Task 8)
- Test: `tests/engine/test_actions_legal.py`、`tests/engine/test_actions_apply.py`（重写）

**Interfaces:**
- Produces 动作类型：

```python
TakeCard(row_index: int)                    # 含奇迹牌(拿取即入场, 不入队)
DevelopTech(card_id: str)                   # 科技/特殊科技/兵种: 1 白点(兵种 1 红点) + 科技费
DevelopGovernment(card_id: str, revolution: bool)  # 和平: 1 白点+高费; 革命: 全部剩余白点+低费
Build(card_id: str)                         # 从空闲池放工人: 1 白点(兵种 1 红点) + 全额造价
Upgrade(from_card_id: str, to_card_id: str) # 移工人到同类别高等级卡: 1 白点(兵种 1 红点) + 差值
Destroy(card_id: str)                       # 摧毁城市建筑/农场/矿场: 1 白点, 工人回池
Disband(card_id: str)                       # 解散军事单位: 1 红点, 工人回池
PlayLeader(card_id: str)                    # 1 白点; 替换旧领袖(弃置)并拿回 1 白点
BuildWonderStage()                          # 1 白点 + 左起下一未付阶段费; 蓝点从供给区盖上
PlayActionCard(card_id: str)                # 1 白点, 结算见 Task 7
PassTurn()
```

- legal 关键规则：手牌上限（civ 系统）；"同名科技牌不可再拿"（手牌+developed 查重）；领袖时代查重（leader_ages)；有未完成奇迹不可拿奇迹牌；奇迹拿牌费 = 位置费 + 已完成奇迹数；第一回合（state.round == 1)：只能 TakeCard;Build/Upgrade 要求 developed 有未占用副本；Upgrade 要求 to 比 from 等级高（token_value/build_cost 大或 age 大——用 `age` 然后 `build_cost` 排序，同级禁升）；城市建筑数量受 urban_limit 限制（按类别）
- pending 非空时：仅允许结算 pending 的动作（Task 7 接）；本任务 pending 恒空
- apply 关键：DevelopGovernment 替换旧政府入弃牌堆；BuildWonderStage 从 blue_bank 扣 1 蓝点（不足时依规则可用卡上蓝点——P1 简化：要求 blue_bank > 0 否则不可执行，注释 `# SIMPLIFICATION`)；完成阶段数 == len(wonder_stages) 时移入 wonders 并清空 wonder_progress;TakeCard 拿奇迹 → 置 wonder_progress=(card_id, 0)
- 本任务 `PassTurn` 暂 `raise NotImplementedError("Task 8")` 占位，Task 8 接入 turn.py

- [ ] **Step 1-5:** TDD（用例覆盖：差价升级、同名科技查重、领袖时代查重、奇迹拿牌费加成、第一回合限制、革命费、urban_limit)；commit `feat(engine): 官方动作系统(差价升级/奇迹/领袖/革命)`

---

### Task 7: 行动卡结算与 pending 子行动

**Files:**
- Modify: `tta/engine/legal.py`、`tta/engine/apply.py`
- Create: `tta/engine/effects.py`（行动卡处理器 + 注册表骨架）
- Test: `tests/engine/test_action_cards.py`

**Interfaces:**
- 行动卡结算方式（effects.py 注册 `ACTION_HANDLERS: dict[str, Callable]`,key = card 基名如 `"rich_land"`,Age A 全 10 种 + I/II/III 同名不同 X):
  - 即时收益类（stockpile/frugality/cultural_heritage/reserves/revolutionary_idea/breakthrough 等）：直接改状态；breakthrough 类"以全费研发一科技再获 X 科技"→ pending kind `"develop_tech"` + 完成后再结算
  - 折扣子行动类（rich_land/urban_growth/efficient_upgrade/engineering_genius):push `PendingEffect(kind, discount)`；下动作必须是对应 Build/Upgrade/BuildWonderStage，享折扣、0 行动点；执行后 pop
  - 回合修饰类（patriotism/military_build_up/wave_of_nationalism):`turn_discounts` 写入 + 立即行动点调整
- legal:pending 非空 → 只生成能结算首个 pending 的动作（无合法解的情况由 PlayActionCard 的合法性前置排除：无对应可建目标时不可打出该行动卡）
- PlayActionCard 合法性：对应子行动至少存在一个合法解（如 rich_land 要求存在可支付的农场/矿场建造或升级）

- [ ] **Step 1-5:** TDD（用例：stockpile 收益入最低级卡、rich_land pending 流程全链、patriotism 当回合折扣、无目标时不可打出）；commit `feat(engine): 行动卡结算与 pending 子行动`

---

### Task 8: 官方回合机（turn.py)

**Files:**
- Create: `tta/engine/turn.py`
- Modify: `tta/engine/apply.py`(PassTurn 调 turn 机）
- Test: `tests/engine/test_turn_machine.py`（重写原 test_turn.py)

**Interfaces:**
- Produces:
  - `advance(state: GameState, db: CardDB) -> GameState` — PassTurn 后的完整流程：回合末阶段 → 推进到下一位玩家的回合开始阶段
- 回合末阶段顺序：弃多余军事牌（P2-DEFERRED no-op)→ 起义检定（is_uprising → 跳过生产）→ 生产（增速计分 → 腐败 → 食物生产 → 食物消耗（每缺 1 −4 文化，文化下限 0)→ 资源生产）→ 抓军事牌（P2 no-op)→ 恢复行动点（= civ 总值）→ 清空 turn_discounts
- 回合开始阶段（advance 内，对下一位玩家）:round==1 全部跳过；否则：弃最左 N(2/3/4 人 → 3/2/1）位卡牌 → 左移 → 补牌；补牌中当前牌堆尽 → 时代结束序列（过期处理：弃更老时代手牌、移除过期领袖并清 leader/leader_ages 保留、移除过期未完成奇迹[蓝点退回供给区]→ 每人 yellow_bank −2（下限 0)→ 切新牌堆继续补）;III 堆尽 → 时代 IV:last_round 规则（起始玩家回合开启 IV → 本轮最后；否则下轮最后）
- 时代 A 结束特判：第一次补牌 = 起始玩家第二回合开始：左移 → A 堆补空位 → A 堆余牌入 removed → 启用 I 堆（无过期，但每人 −2 黄点仍执行）
- 终局：last_round 轮结束 → terminal,final_scores = 各玩家 culture（事件终局计分 P2)

- [ ] **Step 1-5:** TDD（用例：第一轮不补牌、2 人弃 3 张、时代 A 结束序列、时代结束 −2 黄点与过期、腐败/消耗/起义顺序、时代 IV 两种 last_round 时机）；commit `feat(engine): 官方回合状态机(补牌/时代结束/生产/终局)`

---

### Task 9: 初始科技 + 时代 A 牌库 + effects 钩子

**Files:**
- Create: `tta/cards/initial.py`、`tta/cards/age_a.py`
- Modify: `tta/engine/effects.py`（领袖/奇迹钩子）
- Test: `tests/cards/test_initial_age_a.py`

**Interfaces:**
- 初始科技（数值已核实，见 docs/research/tta-official-data.md §3):agriculture(2 造， 值1)×2 工人、bronze(2 造， 值1)×2、philosophy(3 造， 1 科技/工人）×1、religion(3 造， 1 文化+1 笑脸）×0、warriors(2 造， 1 军力）×1、despotism(4 白 2 红， 上限 2)
- Age A 20 张：6 领袖 + 4 奇迹 + 10 行动牌，数据以卡牌数值表 PDF 第 1-2 页为准（实现者直接 Read 该 PDF 转录；research 文档 §4 作交叉核对，冲突以 PDF 为准并报告）
- effects.py 钩子（Age A 领袖）:`moses`（增人口 −1 食物）、`hammurabi`（拿领袖 −1 白点；每回合一次红点当白点——SIMPLIFICATION:P1 实现为"白点不足时可用红点支付白点费用"，注释说明）、`aristotle`（拿科技牌 +1 科技，on_take_card 钩子）、`homer`(+1 笑脸静态；每回合军事建造折扣 1，经 turn_discounts 在回合开始注入）、`alexander`（每军事单位 +1 军力；政治能力 P2-DEFERRED)、`julius_caesar`(+1 军力 +1 红点静态；双政治行动 P2-DEFERRED)
- 奇迹 wonder_bonus:hanging_gardens {culture:1, happiness:2}、pyramids {civil_actions:1}、colossus {strength:2, colonization:1}、library_of_alexandria {civil_hand_extra:1, military_hand_extra:1}
- `tta/cards/__init__.py` 导出 `build_card_db() -> CardDB`（后续任务逐时代扩充）

- [ ] **Step 1-5:** TDD（用例：牌库 20 张、初始台面、每个领袖钩子行为、奇迹 bonus 入 civ)；commit `feat(cards): 初始科技与时代 A 官方牌库`

---

### Task 10-12: 时代 I / II / III 内政牌转录

**Files:**
- Create: `tta/cards/age_i.py`、`tta/cards/age_ii.py`、`tta/cards/age_iii.py`
- Modify: `tta/engine/effects.py`（逐时代补钩子）、`tta/cards/__init__.py`
- Test: `tests/cards/test_age_i.py` 等

**转录规范（三个任务同构）:**
- 数据源：卡牌数值表 PDF 第 1 页（科技/政府/奇迹）、第 2 页（领袖全表 + 行动牌全表，含各时代 X 加成与 2p/3p/4p 张数）
- 每张牌：id（英文小写下划线 + 时代后缀，如 `printing_press`)、中文名（参照规则书附录/通行译名）、name_en、类别、科技费/建造费/产出/quantities、text（效果英文直译）、handler（需要时）
- 领袖与特殊科技的特殊效果：静态加成入 civ 钩子；互动效果（殖民/军事/政治相关）标 `# P2-DEFERRED` 并在 text 保留完整描述
- 行动牌按时代实例化（如 `engineering_genius_a/i/ii/iii`,X 分别为 2/3/4/5)，复用 Task 7 处理器
- 验证测试：该时代牌数 = Σ quantities(2p/3p/4p 分别断言，数值从 PDF 转录后由实现者计算填入并在报告中列出）；科技/政府/奇迹/领袖/行动类别计数；每牌字段非空检查

- [ ] **Step 1-5（每时代）:** 转录 → 测试 → 全量回归 → commit `feat(cards): 时代 I/II/III 官方内政牌库`

---

### Task 13: new_game 官方化 + 删除 minimal

**Files:**
- Modify: `tta/engine/setup.py`（重写）、`tta/engine/__init__.py`、`tta/cli/main.py`（恢复 selfplay，改用正式牌库）
- Test: `tests/engine/test_setup.py`（重写）、`tests/cli/test_cli.py`（重建）

**Interfaces:**
- `new_game(db, num_players, seed)`:A 堆 20 张洗匀发 13 张牌列（余 7 张为当前牌堆）,I/II/III 堆按人数组牌洗匀入 future_decks；玩家：黄点 18 银行 + 1 池 + 6 初始工人（农业 2/铜矿 2/哲学 1/战士 1)、蓝点 16、政府 despotism；第一回合行动点：座位 i → 白点 i+1、红点 0
- CLI/orchestrator 改用 `tta.cards.build_card_db()`

- [ ] **Step 1-5:** TDD;commit `feat: 官方开局设置与正式牌库接入`

---

### Task 14: 属性测试与黄金回归重建

**Files:**
- Modify: `tests/property/test_invariants.py`（重写）、`tests/golden/test_golden_game.py`（重建指纹）
- Test: `tests/orchestrator/test_runner.py`（修复）

**不变量（重写）:**
- 黄点守恒（每人）:yellow_bank + worker_pool + 建筑工人 = 25 − 2×（已结束时代数） − 其他损失
- 蓝点守恒（每人）:blue_bank + Σ card_tokens + 奇迹上蓝点 = 16（奇迹完成时退回）
- 资源非负、行动点非负、文化/科技 ≥ 0
- 卡牌守恒：牌列+牌堆+future+手牌+developed+奇迹（进行中/完成）+领袖+弃牌+removed ≡ 全集
- 序列化往返：每步 `from_dict(to_dict(state)) == state`
- 黄金回归：随机玩家 2 人 seed 42，跑通后回填指纹（scores/rounds/steps + 终局 state_hash)

- [ ] **Step 1-5:** 实现 → 全量 `uv run pytest -q` + `uv run ruff check tta tests` → `uv run tta selfplay --players 4 --games 3` 冒烟 → commit `test: 官方规则属性测试与黄金回归`

---

## P1 完成判定

- [ ] 全测试绿 + lint 干净；4 人 3 局 CLI 冒烟通过；同种子确定性一致
- [ ] 代码中无 RULES-AUDIT 残留；军事延后项均有 P2-DEFERRED 标注
- [ ] 全部内政牌（初始 6 + A 20 + I/II/III）经卡牌数值表转录并由用户抽查
- [ ] `grep -r "from tta.cards" tta/engine/` 为空

## 用户抽查清单（P1 验收时进行）

1. 黄点轨道 8 区段数值（tracks.py vs 实体版图）
2. 时代 A 20 张牌（age_a.py vs 实体牌）
3. 随机抽 5 张 I/II/III 科技牌 + 3 张领袖 + 2 张奇迹对照数值
4. 时代结束 −2 黄点、升级付差价、腐败分段值（规则书 p3/p6)

## 后续阶段衔接

> **执行期修正记录（P1 终审确认，均已落地并锁定测试）:**
> 1. 时代 A 结束**不执行** −2 黄点与过期（英文 Code of Laws 明确 "nothing else happens")；时代 I/II/**III** 结束均执行过期 + −2 黄点（本计划 Task 8 原遗漏 III，已补）
> 2. 时代 IV 回合开始**继续弃最左 N 张**但不补牌（本计划原文"停补"未明确弃牌，已补）
> 3. 首次打出领袖净耗 1 白点；仅替换旧领袖才拿回 1 白点
> 4. 同类型特殊科技只留等级高者（低者入 removed)；同名政体（含当前政体）不可再拿/变更
> 5. hammurabi 红点垫付为每回合一次 1 点（非无限 1:1)
> 6. 蓝点生命周期闭环：支付/消耗/腐败移除的蓝点放回供给区，奇迹完成退回盖点
> 7. tracks.py 的 corruption_value 正确语义为"最左未覆盖的**印刷负数**"（负数只印在段首格），参考实现已改为分档
> 8. IncreasePopulation 独立动作（本计划 Task 6 动作清单遗漏，已补）
>
> **P2 开工前注意：** ① PendingEffect 需泛化 owner/target（防御方响应发生在对手回合）;② 回合需加相位字段（政治阶段在行动阶段前）;③ 军事牌堆洗牌必须先约定 rng_state 消费规范；④ shakespeare 配对文化、j_s_bach 每剧院 +1 文化属内政静态加成，P2 第一批处理；⑤ sid_meier/leonardo/newton "按已研发卡计"与官方"按工人/产出计"口径差列入 P2/P3 规则保真 pass。

- P2：军事系统（军事牌堆/政治阶段/事件/侵略/战争/条约/阵型/殖民 + pending 响应队列）；数据源已就绪（卡牌数值表第 3-4 页）
- P2 开工前注意：事件/军事牌抽取须先约定 rng_state 消费规范；侵略/战争的玩家响应走 pending 队列（Task 7 已打底）
