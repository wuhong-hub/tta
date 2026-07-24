# P0: 引擎核心 + 随机玩家最小对局 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建项目骨架与确定性规则引擎核心（状态模型 / 合法动作生成 / 动作结算 / 回合状态机 / 种子随机 / JSON 序列化），使随机玩家能跑通一局最小规则 2-4 人对局并产出 JSONL 棋谱。

**Architecture:** 单向依赖 `cli → orchestrator → agents → engine → (无)`；卡牌数据经 `CardDB` 在 `new_game` 时注入，engine 不 import 任何卡牌库文件。`apply` 返回新状态（不可变式），RNG 为纯函数式 SplitMix64（状态是单个 int)，整局可凭 seed 精确重放。

**Tech Stack:** Python 3.12（语法底线 3.10)、uv、pytest、ruff；零运行时第三方依赖。

## Global Constraints

- Python `requires-python = ">=3.10"`；4 空格缩进；所有函数签名带类型注解；优先 f-string、`pathlib`、`dataclasses`
- engine 包（`tta/engine/`）不得 import `tta.agents` / `tta.orchestrator` / `tta.cli` / `tta.cards` 中任何模块
- 所有状态数据类 `@dataclass(frozen=True)`；嵌套 dict 只读不写（修改前整体复制）——由不可变性测试守护
- RNG 一律走 `tta/engine/rng.py` 的纯函数；禁止 `import random`（agents 包内的随机玩家除外，它有自己的 `random.Random`）
- P0 数值常量一律标注 `# RULES-AUDIT: ...`，表示 P2 需对照官方规则书核对；P0 只要求机制可运转，不要求数值官方精确
- P0 明确排除（在后续阶段落地，不在本计划范围）：政治行动/事件牌、侵略与战争、奇观、领袖、殖民、腐败、军事牌堆、 pending 响应队列、城市建筑上限、革命、效果原语框架（P1)
- 测试命令统一：`uv run pytest <path> -v`；lint:`uv run ruff check tta tests`
- 每次 commit 前跑 `uv run pytest` 全量 + `uv run ruff check tta tests`

## 名词约定（全计划一致）

- 白点 = civil actions（内政行动点）, 红点 = military actions（军事行动点）
- 黄点 = yellow tokens（人口标记）, 蓝点在 P0 简化为 `materials`/`food` 两个整数（资源/食物库存）
- `ROW_SLOTS = 13`（卡牌列格数）;`ROW_COSTS` 为每格拿牌所需白点

---

### Task 1: 项目骨架与打包

**Files:**
- Create: `pyproject.toml`
- Create: `tta/__init__.py`
- Create: `tta/engine/__init__.py`, `tta/cards/__init__.py`, `tta/agents/__init__.py`, `tta/orchestrator/__init__.py`, `tta/replay/__init__.py`, `tta/cli/__init__.py`
- Create: `tests/__init__.py`, `tests/engine/__init__.py`, `tests/cards/__init__.py`, `tests/agents/__init__.py`, `tests/orchestrator/__init__.py`, `tests/property/__init__.py`, `tests/golden/__init__.py`
- Create: `.gitignore`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: 可 `uv sync` 安装的项目；`tta.__version__ == "0.1.0"`；后续所有任务在此骨架上添文件

- [ ] **Step 1: 写冒烟测试**

```python
# tests/test_smoke.py
"""项目骨架冒烟测试."""

import tta


def test_version() -> None:
    assert tta.__version__ == "0.1.0"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: ERROR / FAIL（项目尚未安装，`tta` 包不存在）

- [ ] **Step 3: 写 pyproject 与包骨架**

```toml
# pyproject.toml
[project]
name = "tta"
version = "0.1.0"
description = "Through the Ages AI self-play strategy research tool"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
tta = "tta.cli.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["tta"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
]

[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# tta/__init__.py
"""Through the Ages AI self-play strategy research tool."""

__version__ = "0.1.0"
```

其余 `__init__.py` 暂时为空文件（`tta/cli/__init__.py` 等）。注意 `pyproject.toml` 声明了入口点 `tta.cli.main:main`，该文件在 Task 10 创建；为使 `uv sync` 在 Task 1 即可通过，先创建占位：

```python
# tta/cli/__init__.py
"""命令行入口包."""
```

```python
# tta/cli/main.py（占位, Task 10 替换）
"""命令行入口."""

def main() -> None:
    """CLI 入口占位."""
    print("tta CLI placeholder")
```

```gitignore
# .gitignore
.venv/
__pycache__/
*.pyc
.ruff_cache/
.pytest_cache/
replays/
dist/
```

- [ ] **Step 4: 安装并运行测试**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS（1 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tta tests .gitignore uv.lock
git commit -m "chore: 项目骨架与打包配置"
```

---

### Task 2: 枚举与卡牌数据模型

**Files:**
- Create: `tta/engine/enums.py`
- Create: `tta/engine/model.py`
- Create: `tta/engine/constants.py`
- Test: `tests/engine/test_model.py`

**Interfaces:**
- Produces（后续任务全部依赖）:
  - `Age(A/I/II/III)`，含 `Age.next() -> Age | None`
  - `DeckType(CIVIL/MILITARY)`、`CardCategory(FARM/MINE/LAB/TEMPLE/UNIT/GOVERNMENT/ACTION)`、`BuildingType(FARM/MINE/LAB/TEMPLE/UNIT)`
  - `CATEGORY_TO_BUILDING: dict[CardCategory, BuildingType]`
  - `GovernmentStats(civil_actions, military_actions, civil_hand_limit, military_hand_limit)`
  - `CardDefinition(id, name, age, deck, category, text, cost_science, build_cost, produces, government, gains)`
  - `CardDB(cards, civil_decks, initial_tableau, initial_government)`，含 `get(card_id) -> CardDefinition`
  - 常量：`ROW_SLOTS=13`, `ROW_COSTS`, `BASE_HAPPINESS`, `FOOD_PER_WORKER`, `POP_FOOD_COST`, `STARVATION_CULTURE`, `INITIAL_YELLOW`, `INITIAL_FOOD`, `INITIAL_MATERIALS`, `MAX_STEPS`

- [ ] **Step 1: 写失败测试**

```python
# tests/engine/test_model.py
"""枚举与卡牌数据模型测试."""

from tta.engine.constants import ROW_COSTS, ROW_SLOTS
from tta.engine.enums import Age, CardCategory, BuildingType, CATEGORY_TO_BUILDING
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.enums import DeckType


def test_age_next() -> None:
    assert Age.A.next() is Age.I
    assert Age.I.next() is Age.II
    assert Age.II.next() is Age.III
    assert Age.III.next() is None


def test_row_costs_length() -> None:
    assert len(ROW_COSTS) == ROW_SLOTS == 13
    assert all(c in (1, 2, 3) for c in ROW_COSTS)


def test_category_to_building_covers_buildings() -> None:
    assert CATEGORY_TO_BUILDING[CardCategory.FARM] is BuildingType.FARM
    assert CATEGORY_TO_BUILDING[CardCategory.UNIT] is BuildingType.UNIT
    assert CardCategory.GOVERNMENT not in CATEGORY_TO_BUILDING
    assert CardCategory.ACTION not in CATEGORY_TO_BUILDING


def _gov() -> GovernmentStats:
    return GovernmentStats(civil_actions=4, military_actions=2,
                           civil_hand_limit=4, military_hand_limit=2)


def test_card_db_get() -> None:
    card = CardDefinition(id="despotism", name="专制", age=Age.A,
                          deck=DeckType.CIVIL, category=CardCategory.GOVERNMENT,
                          government=_gov())
    db = CardDB(cards={"despotism": card}, civil_decks={Age.A: ()},
                initial_tableau=(), initial_government="despotism")
    assert db.get("despotism") is card


def test_card_definition_defaults() -> None:
    card = CardDefinition(id="x", name="x", age=Age.A,
                          deck=DeckType.CIVIL, category=CardCategory.ACTION)
    assert card.cost_science == 0
    assert card.produces == {}
    assert card.government is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/engine/test_model.py -v`
Expected: FAIL(ModuleNotFoundError: tta.engine.enums)

- [ ] **Step 3: 实现 enums.py / model.py / constants.py**

```python
# tta/engine/enums.py
"""引擎核心枚举."""

from enum import Enum


class Age(Enum):
    """时代."""

    A = "A"
    I = "I"
    II = "II"
    III = "III"

    def next(self) -> "Age | None":
        """返回下一时代, III 之后为 None."""
        order = [Age.A, Age.I, Age.II, Age.III]
        idx = order.index(self)
        return order[idx + 1] if idx + 1 < len(order) else None


class DeckType(Enum):
    """牌堆类型."""

    CIVIL = "civil"
    MILITARY = "military"


class CardCategory(Enum):
    """卡牌类别."""

    FARM = "farm"
    MINE = "mine"
    LAB = "lab"
    TEMPLE = "temple"
    UNIT = "unit"
    GOVERNMENT = "government"
    ACTION = "action"


class BuildingType(Enum):
    """建筑槽位类型(与单位共用一套工人放置机制)."""

    FARM = "farm"
    MINE = "mine"
    LAB = "lab"
    TEMPLE = "temple"
    UNIT = "unit"


CATEGORY_TO_BUILDING: dict[CardCategory, BuildingType] = {
    CardCategory.FARM: BuildingType.FARM,
    CardCategory.MINE: BuildingType.MINE,
    CardCategory.LAB: BuildingType.LAB,
    CardCategory.TEMPLE: BuildingType.TEMPLE,
    CardCategory.UNIT: BuildingType.UNIT,
}
```

```python
# tta/engine/model.py
"""卡牌定义与卡牌数据库(纯数据, 无行为)."""

from dataclasses import dataclass, field

from tta.engine.enums import Age, CardCategory, DeckType


@dataclass(frozen=True)
class GovernmentStats:
    """政体数值."""

    civil_actions: int
    military_actions: int
    civil_hand_limit: int
    military_hand_limit: int


@dataclass(frozen=True)
class CardDefinition:
    """一张卡的静态定义.

    produces/gains 的键为资源名字符串:
    "food" / "materials" / "science" / "culture" / "strength" / "happiness".
    """

    id: str
    name: str
    age: Age
    deck: DeckType
    category: CardCategory
    text: str = ""
    cost_science: int = 0        # 研发所需科技点(政体/科技类)
    build_cost: int = 0          # 在其上放置 1 个工人所需资源
    produces: dict[str, int] = field(default_factory=dict)   # 每工人产出
    government: GovernmentStats | None = None                # 政体卡专有
    gains: dict[str, int] = field(default_factory=dict)      # 行动卡一次性收益


@dataclass(frozen=True)
class CardDB:
    """一套牌库: 卡牌定义 + 各时代牌堆(卡牌 id, 可重复表示多张)."""

    cards: dict[str, CardDefinition]
    civil_decks: dict[Age, tuple[str, ...]]
    initial_tableau: tuple[str, ...]   # 每名玩家开局已研发的建筑卡 id(含重复)
    initial_government: str            # 开局政体卡 id

    def get(self, card_id: str) -> CardDefinition:
        """按 id 取卡牌定义."""
        return self.cards[card_id]
```

```python
# tta/engine/constants.py
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
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/engine/test_model.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: Commit**

```bash
git add tta/engine/enums.py tta/engine/model.py tta/engine/constants.py tests/engine/test_model.py
git commit -m "feat(engine): 枚举、卡牌数据模型与数值常量"
```

---

### Task 3: 纯函数式 RNG(SplitMix64)

**Files:**
- Create: `tta/engine/rng.py`
- Test: `tests/engine/test_rng.py`

**Interfaces:**
- Produces:
  - `rng_below(state: int, bound: int) -> tuple[int, int]` — 返回（新状态， [0, bound) 随机数）
  - `rng_shuffle(state: int, items: Sequence[str]) -> tuple[int, list[str]]` — Fisher-Yates，返回（新状态， 洗牌后新列表）
- 说明：GameState.rng_state 即这里的 `state`；所有随机性必须经此二函数

- [ ] **Step 1: 写失败测试**

```python
# tests/engine/test_rng.py
"""SplitMix64 纯函数随机数测试."""

import pytest

from tta.engine.rng import rng_below, rng_shuffle


def test_deterministic() -> None:
    assert rng_below(42, 100) == rng_below(42, 100)


def test_state_advances() -> None:
    s1, _ = rng_below(42, 100)
    s2, _ = rng_below(s1, 100)
    assert s1 != 42 and s2 != s1


def test_bound() -> None:
    state = 7
    for _ in range(200):
        state, v = rng_below(state, 6)
        assert 0 <= v < 6


def test_invalid_bound() -> None:
    with pytest.raises(ValueError):
        rng_below(1, 0)


def test_shuffle_is_permutation_and_deterministic() -> None:
    items = [f"c{i}" for i in range(20)]
    s1, a = rng_shuffle(42, items)
    s2, b = rng_shuffle(42, items)
    assert (s1, a) == (s2, b)
    assert sorted(a) == sorted(items)
    assert a != items  # 20 个元素原序概率可忽略


def test_shuffle_empty_and_single() -> None:
    _, empty = rng_shuffle(1, [])
    assert empty == []
    _, one = rng_shuffle(1, ["x"])
    assert one == ["x"]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/engine/test_rng.py -v`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 实现 rng.py**

```python
# tta/engine/rng.py
"""SplitMix64 纯函数随机数发生器.

状态为单个 64 位整数, 可直接放入 GameState 序列化;
同一 (state, bound) 输入必得同一输出, 保证棋谱可凭 seed 精确重放.
"""

from collections.abc import Sequence

MASK64 = (1 << 64) - 1
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15


def _step(state: int) -> tuple[int, int]:
    """推进状态并输出一个 64 位随机值."""
    state = (state + _GOLDEN_GAMMA) & MASK64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return state, (z ^ (z >> 31)) & MASK64


def rng_below(state: int, bound: int) -> tuple[int, int]:
    """返回 (新状态, [0, bound) 内随机整数). 取模偏差对桌游场景可忽略."""
    if bound <= 0:
        raise ValueError(f"bound must be positive, got {bound}")
    state, z = _step(state)
    return state, z % bound


def rng_shuffle(state: int, items: Sequence[str]) -> tuple[int, list[str]]:
    """Fisher-Yates 洗牌, 返回 (新状态, 新列表), 不改动入参."""
    result = list(items)
    for i in range(len(result) - 1, 0, -1):
        state, j = rng_below(state, i + 1)
        result[i], result[j] = result[j], result[i]
    return state, result
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/engine/test_rng.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: Commit**

```bash
git add tta/engine/rng.py tests/engine/test_rng.py
git commit -m "feat(engine): SplitMix64 纯函数 RNG"
```

---

### Task 4: 游戏状态模型 + JSON 序列化 + state_hash

**Files:**
- Create: `tta/engine/state.py`
- Test: `tests/engine/test_state.py`

**Interfaces:**
- Consumes: Task 2 的 `Age`、`CardDB`;Task 3 的 rng 概念（此处仅存 `rng_state: int`)
- Produces:
  - `PlayerState`（字段见下）、`GameState`（字段见下）
  - `workers_total(p: PlayerState) -> int`
  - `to_dict(state: GameState) -> dict`、`from_dict(data: dict) -> GameState`
  - `state_hash(state: GameState) -> str`(sha256 hex，规范化 JSON)
  - `replace_player(state: GameState, index: int, player: PlayerState) -> GameState`
- 约定：`PlayerState.buildings` 结构为 `{BuildingType.value: {card_id: 工人数}}`；嵌套 dict 永就整体复制，不原地改

- [ ] **Step 1: 写失败测试**

```python
# tests/engine/test_state.py
"""游戏状态模型与序列化测试."""

from tta.engine.enums import Age, BuildingType
from tta.engine.state import (
    GameState,
    PlayerState,
    from_dict,
    replace_player,
    state_hash,
    to_dict,
    workers_total,
)


def _player(name: str = "P0") -> PlayerState:
    return PlayerState(
        name=name,
        culture=3,
        science=5,
        materials=2,
        food=4,
        yellow_bank=21,
        worker_pool=1,
        buildings={"farm": {"agriculture": 2}, "mine": {"bronze": 1}},
        developed=("agriculture", "agriculture", "bronze"),
        hand_civil=("irrigation",),
        government="despotism",
        civil_actions=4,
        military_actions=2,
    )


def _state() -> GameState:
    return GameState(
        round=2,
        age=Age.A,
        current_player=1,
        card_row=("irrigation", None, "iron") + (None,) * 10,
        civil_deck=("alchemy", "monarchy"),
        future_decks={"I": ("coal",), "II": (), "III": ("oil",)},
        discard=("harvest_a",),
        removed=(),
        players=(_player("P0"), _player("P1")),
        rng_state=12345,
    )


def test_workers_total() -> None:
    # pool 1 + farm 2 + mine 1 = 4
    assert workers_total(_player()) == 4


def test_serialization_roundtrip() -> None:
    state = _state()
    assert from_dict(to_dict(state)) == state


def test_state_hash_stable_and_sensitive() -> None:
    state = _state()
    assert state_hash(state) == state_hash(state)
    other = replace_player(state, 0, PlayerState(name="P0", culture=99))
    assert state_hash(state) != state_hash(other)


def test_terminal_fields_roundtrip() -> None:
    state = _state()
    done = GameState(**{**state.__dict__, "terminal": True, "final_scores": (10, 20)})
    assert from_dict(to_dict(done)) == done


def test_replace_player_does_not_mutate() -> None:
    state = _state()
    before = state.players[0]
    _ = replace_player(state, 0, PlayerState(name="X"))
    assert state.players[0] is before
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/engine/test_state.py -v`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 实现 state.py**

```python
# tta/engine/state.py
"""游戏状态: 纯数据树, 可完整 JSON 序列化.

不可变约定: 所有 dataclass frozen; 嵌套 dict(buildings)修改前整体复制,
由 tests/engine/test_apply.py 的不可变性测试守护.
"""

import hashlib
import json
from dataclasses import dataclass, field, replace

from tta.engine.constants import ROW_SLOTS
from tta.engine.enums import Age


@dataclass(frozen=True)
class PlayerState:
    """单个玩家状态.

    buildings: {BuildingType.value: {card_id: 工人数}}.
    developed: 已研发(置于场上)的建筑/兵种卡 id, 可重复(每张即一个建筑槽).
    """

    name: str
    culture: int = 0
    science: int = 0
    materials: int = 0
    food: int = 0
    yellow_bank: int = 0
    worker_pool: int = 0
    buildings: dict[str, dict[str, int]] = field(default_factory=dict)
    developed: tuple[str, ...] = ()
    hand_civil: tuple[str, ...] = ()
    government: str = ""
    civil_actions: int = 0
    military_actions: int = 0


@dataclass(frozen=True)
class GameState:
    """整局状态. card_row 中 None 表示空格; civil_deck 顶部为索引 0."""

    round: int
    age: Age
    current_player: int
    card_row: tuple[str | None, ...]
    civil_deck: tuple[str, ...]
    future_decks: dict[str, tuple[str, ...]]   # Age.value -> 牌堆
    discard: tuple[str, ...]
    removed: tuple[str, ...]
    players: tuple[PlayerState, ...]
    rng_state: int
    last_round: bool = False
    terminal: bool = False
    final_scores: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if len(self.card_row) != ROW_SLOTS:
            raise ValueError(f"card_row must have {ROW_SLOTS} slots")


def workers_total(p: PlayerState) -> int:
    """玩家工人总数 = 空闲 + 各建筑上的工人."""
    placed = sum(n for slots in p.buildings.values() for n in slots.values())
    return p.worker_pool + placed


def replace_player(state: GameState, index: int, player: PlayerState) -> GameState:
    """替换指定位置玩家, 返回新 GameState."""
    players = list(state.players)
    players[index] = player
    return replace(state, players=tuple(players))


def _player_to_dict(p: PlayerState) -> dict:
    return {
        "name": p.name,
        "culture": p.culture,
        "science": p.science,
        "materials": p.materials,
        "food": p.food,
        "yellow_bank": p.yellow_bank,
        "worker_pool": p.worker_pool,
        "buildings": {k: dict(v) for k, v in sorted(p.buildings.items())},
        "developed": list(p.developed),
        "hand_civil": list(p.hand_civil),
        "government": p.government,
        "civil_actions": p.civil_actions,
        "military_actions": p.military_actions,
    }


def _player_from_dict(d: dict) -> PlayerState:
    return PlayerState(
        name=d["name"],
        culture=d["culture"],
        science=d["science"],
        materials=d["materials"],
        food=d["food"],
        yellow_bank=d["yellow_bank"],
        worker_pool=d["worker_pool"],
        buildings={k: dict(v) for k, v in d["buildings"].items()},
        developed=tuple(d["developed"]),
        hand_civil=tuple(d["hand_civil"]),
        government=d["government"],
        civil_actions=d["civil_actions"],
        military_actions=d["military_actions"],
    )


def to_dict(state: GameState) -> dict:
    """序列化为 JSON 可编码 dict."""
    return {
        "round": state.round,
        "age": state.age.value,
        "current_player": state.current_player,
        "card_row": list(state.card_row),
        "civil_deck": list(state.civil_deck),
        "future_decks": {k: list(v) for k, v in sorted(state.future_decks.items())},
        "discard": list(state.discard),
        "removed": list(state.removed),
        "players": [_player_to_dict(p) for p in state.players],
        "rng_state": state.rng_state,
        "last_round": state.last_round,
        "terminal": state.terminal,
        "final_scores": list(state.final_scores) if state.final_scores else None,
    }


def from_dict(data: dict) -> GameState:
    """从 to_dict 产物还原 GameState."""
    return GameState(
        round=data["round"],
        age=Age(data["age"]),
        current_player=data["current_player"],
        card_row=tuple(data["card_row"]),
        civil_deck=tuple(data["civil_deck"]),
        future_decks={k: tuple(v) for k, v in data["future_decks"].items()},
        discard=tuple(data["discard"]),
        removed=tuple(data["removed"]),
        players=tuple(_player_from_dict(d) for d in data["players"]),
        rng_state=data["rng_state"],
        last_round=data["last_round"],
        terminal=data["terminal"],
        final_scores=tuple(data["final_scores"]) if data["final_scores"] else None,
    )


def state_hash(state: GameState) -> str:
    """规范化 JSON 的 sha256, 用于棋谱链式校验."""
    blob = json.dumps(to_dict(state), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/engine/test_state.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: Commit**

```bash
git add tta/engine/state.py tests/engine/test_state.py
git commit -m "feat(engine): 游戏状态模型与 JSON 序列化"
```

---

### Task 5: 动作类型 + legal_actions

**Files:**
- Create: `tta/engine/actions.py`
- Create: `tta/engine/legal.py`
- Test: `tests/engine/test_legal.py`

**Interfaces:**
- Consumes: Task 2/4 全部；`ROW_COSTS`、`POP_FOOD_COST`、`CATEGORY_TO_BUILDING`
- Produces:
  - 动作类型：`TakeCard(row_index)`、`Develop(card_id)`、`Build(card_id)`、`IncreasePopulation()`、`PlayActionCard(card_id)`、`PassTurn()`;`Action = Union[...]`
  - `IllegalActionError(Exception)`
  - `action_to_dict(a: Action) -> dict`、`action_from_dict(d: dict) -> Action`
  - `legal_actions(state: GameState, db: CardDB) -> list[Action]` — `PassTurn()` 恒在且总在列表末尾
- 规则（P0 骨架，均已标 RULES-AUDIT 处见代码注释）:
  - 拿牌：白点 ≥ ROW_COSTS[i] 且内政手牌 < 政体手牌上限； ACTION 类卡也走手牌
  - 研发（Develop)：科技/政体花 1 白点 + science；兵种花 1 红点 + science；政体研发即更换（和平演变）
  - 建造（Build)：建筑花 1 白点，兵种花 1 红点；需 materials ≥ build_cost；需该卡已研发数 > 已放置工人数；工人来源为空闲池或同类型低处建筑（来源选择在 apply 中确定性处理）
  - 增加人口：1 白点 + POP_FOOD_COST 食物 + yellow_bank > 0

- [ ] **Step 1: 写失败测试**

```python
# tests/engine/test_legal.py
"""合法动作生成测试."""

import pytest

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
from tta.engine.enums import Age, BuildingType, CardCategory, DeckType
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
    actions = legal_actions(_state(PlayerState(name="P0")), _db())
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/engine/test_legal.py -v`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 实现 actions.py / legal.py**

```python
# tta/engine/actions.py
"""动作类型: 扁平、可序列化."""

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class TakeCard:
    """从卡牌列拿牌."""

    row_index: int


@dataclass(frozen=True)
class Develop:
    """研发手牌中的科技/政体/兵种卡(付科技点)."""

    card_id: str


@dataclass(frozen=True)
class Build:
    """在已研发建筑/兵种卡上放置 1 个工人(付资源)."""

    card_id: str


@dataclass(frozen=True)
class IncreasePopulation:
    """增加 1 个人口(付食物)."""


@dataclass(frozen=True)
class PlayActionCard:
    """打出手牌中的行动卡."""

    card_id: str


@dataclass(frozen=True)
class PassTurn:
    """结束本回合行动阶段."""


Action = Union[TakeCard, Develop, Build, IncreasePopulation, PlayActionCard, PassTurn]

_ACTION_TYPES: dict[str, type] = {
    "take_card": TakeCard,
    "develop": Develop,
    "build": Build,
    "increase_population": IncreasePopulation,
    "play_action_card": PlayActionCard,
    "pass": PassTurn,
}
_TYPE_NAMES: dict[type, str] = {v: k for k, v in _ACTION_TYPES.items()}


class IllegalActionError(Exception):
    """动作不合法或时机错误."""


def action_to_dict(action: Action) -> dict:
    """序列化动作."""
    data = {"type": _TYPE_NAMES[type(action)]}
    data.update(vars(action))
    return data


def action_from_dict(data: dict) -> Action:
    """反序列化动作."""
    cls = _ACTION_TYPES[data["type"]]
    kwargs = {k: v for k, v in data.items() if k != "type"}
    return cls(**kwargs)  # type: ignore[call-arg]
```

```python
# tta/engine/legal.py
"""合法动作生成: 引擎的规则门面."""

from tta.engine.actions import (
    Action,
    Build,
    Develop,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    TakeCard,
)
from tta.engine.constants import POP_FOOD_COST, ROW_COSTS
from tta.engine.enums import CATEGORY_TO_BUILDING, CardCategory
from tta.engine.model import CardDB
from tta.engine.state import GameState


def legal_actions(state: GameState, db: CardDB) -> list[Action]:
    """枚举当前玩家的全部合法动作; PassTurn 恒在且位于末尾."""
    if state.terminal:
        return []
    p = state.players[state.current_player]
    gov = db.get(p.government).government
    if gov is None:
        raise ValueError(f"current government {p.government} has no stats")

    actions: list[Action] = []

    # 拿牌: 白点付位置费用, 内政手牌不超上限
    if len(p.hand_civil) < gov.civil_hand_limit:
        for i, card_id in enumerate(state.card_row):
            if card_id is not None and p.civil_actions >= ROW_COSTS[i]:
                actions.append(TakeCard(i))

    # 研发 / 打行动卡
    for card_id in sorted(set(p.hand_civil)):
        card = db.get(card_id)
        if card.category is CardCategory.ACTION:
            if p.civil_actions >= 1:
                actions.append(PlayActionCard(card_id))
        elif card.category is CardCategory.GOVERNMENT:
            if p.science >= card.cost_science and p.civil_actions >= 1:
                actions.append(Develop(card_id))
        elif card.category is CardCategory.UNIT:
            if p.science >= card.cost_science and p.military_actions >= 1:
                actions.append(Develop(card_id))
        else:
            if p.science >= card.cost_science and p.civil_actions >= 1:
                actions.append(Develop(card_id))

    # 建造: 已研发副本数 > 已放置工人数; 兵种用红点
    for card_id in sorted(set(p.developed)):
        card = db.get(card_id)
        btype = CATEGORY_TO_BUILDING.get(card.category)
        if btype is None:
            continue
        placed = p.buildings.get(btype.value, {}).get(card_id, 0)
        if p.developed.count(card_id) <= placed:
            continue
        is_unit = card.category is CardCategory.UNIT
        has_action = p.military_actions >= 1 if is_unit else p.civil_actions >= 1
        slots = p.buildings.get(btype.value, {})
        # 工人来源: 空闲池, 或同类型异名建筑上的工人(升级); 同名卡互移无意义
        has_worker_source = p.worker_pool > 0 or any(
            n > 0 for cid, n in slots.items() if cid != card_id)
        if has_action and p.materials >= card.build_cost and has_worker_source:
            actions.append(Build(card_id))

    # 增加人口
    if p.civil_actions >= 1 and p.yellow_bank > 0 and p.food >= POP_FOOD_COST:
        actions.append(IncreasePopulation())

    actions.append(PassTurn())
    return actions
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/engine/test_legal.py -v`
Expected: PASS(9 passed)

- [ ] **Step 5: Commit**

```bash
git add tta/engine/actions.py tta/engine/legal.py tests/engine/test_legal.py
git commit -m "feat(engine): 动作类型与合法动作生成"
```

---

### Task 6: apply —— 动作结算（不含回合推进）

**Files:**
- Create: `tta/engine/apply.py`
- Test: `tests/engine/test_apply.py`

**Interfaces:**
- Consumes: Task 2-5 全部
- Produces:
  - `apply(state: GameState, action: Action, db: CardDB) -> GameState` — 先校验 `action in legal_actions`，非法抛 `IllegalActionError`;`PassTurn` 走 Task 7 的 `_end_turn`（本任务内同文件实现占位调用，Task 7 补全）
- 关键确定性简化（RULES-AUDIT):`Build` 的工人来源——若同类型建筑上有工人，取「时代最小、id 字典序最小」的卡移出 1 工人（升级），否则从空闲池取

- [ ] **Step 1: 写失败测试**

```python
# tests/engine/test_apply.py
"""动作结算测试(回合推进见 test_turn.py)."""

import copy

import pytest

from tta.engine.actions import (
    Build,
    Develop,
    IllegalActionError,
    IncreasePopulation,
    PlayActionCard,
    TakeCard,
)
from tta.engine.apply import apply
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import GameState, PlayerState

GOV = GovernmentStats(civil_actions=4, military_actions=2,
                      civil_hand_limit=4, military_hand_limit=2)


def _db() -> CardDB:
    def gov_card(cid: str, sci: int = 0) -> CardDefinition:
        return CardDefinition(id=cid, name=cid, age=Age.A, deck=DeckType.CIVIL,
                              category=CardCategory.GOVERNMENT, cost_science=sci,
                              government=GOV)

    def bld(cid: str, cat: CardCategory, sci: int, build: int,
            produces: dict | None = None) -> CardDefinition:
        return CardDefinition(id=cid, name=cid, age=Age.A, deck=DeckType.CIVIL,
                              category=cat, cost_science=sci, build_cost=build,
                              produces=produces or {})

    cards = {
        "despotism": gov_card("despotism"),
        "monarchy": gov_card("monarchy", sci=2),
        "agriculture": bld("agriculture", CardCategory.FARM, 0, 2, {"food": 2}),
        "irrigation": bld("irrigation", CardCategory.FARM, 2, 2, {"food": 2}),
        "swordsmen": bld("swordsmen", CardCategory.UNIT, 2, 2, {"strength": 2}),
        "harvest_a": CardDefinition(id="harvest_a", name="丰收", age=Age.A,
                                    deck=DeckType.CIVIL, category=CardCategory.ACTION,
                                    gains={"food": 3}),
    }
    return CardDB(cards=cards, civil_decks={Age.A: ()},
                  initial_tableau=(), initial_government="despotism")


def _state(p: PlayerState, row: tuple = (None,) * 13) -> GameState:
    return GameState(round=1, age=Age.A, current_player=0, card_row=row,
                     civil_deck=(), future_decks={}, discard=(), removed=(),
                     players=(p,), rng_state=1)


def test_illegal_action_raises() -> None:
    with pytest.raises(IllegalActionError):
        apply(_state(PlayerState(name="P0")), TakeCard(0), _db())


def test_take_card() -> None:
    row = ("irrigation",) + (None,) * 12
    p = PlayerState(name="P0", government="despotism", civil_actions=2)
    s = apply(_state(p, row), TakeCard(0), _db())
    assert s.players[0].hand_civil == ("irrigation",)
    assert s.players[0].civil_actions == 1
    assert s.card_row[0] is None


def test_develop_tech_and_government() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=2,
                    science=4, hand_civil=("irrigation", "monarchy"))
    s = apply(_state(p), Develop("irrigation"), _db())
    assert s.players[0].developed == ("irrigation",)
    assert s.players[0].science == 2 and s.players[0].civil_actions == 1
    s2 = apply(s, Develop("monarchy"), _db())
    assert s2.players[0].government == "monarchy"
    assert "despotism" in s2.discard
    assert s2.players[0].science == 0


def test_develop_unit_uses_military_action() -> None:
    p = PlayerState(name="P0", government="despotism", military_actions=1,
                    science=2, hand_civil=("swordsmen",))
    s = apply(_state(p), Develop("swordsmen"), _db())
    assert s.players[0].military_actions == 0
    assert s.players[0].developed == ("swordsmen",)


def test_build_from_pool_and_upgrade() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=2,
                    materials=4, worker_pool=1,
                    developed=("agriculture", "irrigation"))
    s = apply(_state(p), Build("agriculture"), _db())
    assert s.players[0].buildings == {"farm": {"agriculture": 1}}
    assert s.players[0].worker_pool == 0 and s.players[0].materials == 2
    # 第二次建造: 池空, 从同类型低级建筑升级(工人 agriculture -> irrigation)
    s2 = apply(s, Build("irrigation"), _db())
    assert s2.players[0].buildings == {"farm": {"irrigation": 1}}
    assert s2.players[0].materials == 0


def test_build_unit_uses_military_action() -> None:
    p = PlayerState(name="P0", government="despotism", military_actions=1,
                    materials=2, worker_pool=1, developed=("swordsmen",))
    s = apply(_state(p), Build("swordsmen"), _db())
    assert s.players[0].buildings == {"unit": {"swordsmen": 1}}
    assert s.players[0].military_actions == 0


def test_increase_population() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    food=3, yellow_bank=5)
    s = apply(_state(p), IncreasePopulation(), _db())
    assert s.players[0].food == 1
    assert s.players[0].yellow_bank == 4
    assert s.players[0].worker_pool == 1


def test_play_action_card_gains_and_discards() -> None:
    p = PlayerState(name="P0", government="despotism", civil_actions=1,
                    food=0, hand_civil=("harvest_a",))
    s = apply(_state(p), PlayActionCard("harvest_a"), _db())
    assert s.players[0].food == 3
    assert s.players[0].hand_civil == ()
    assert s.discard == ("harvest_a",)


def test_apply_does_not_mutate_input() -> None:
    row = ("irrigation",) + (None,) * 12
    p = PlayerState(name="P0", government="despotism", civil_actions=2,
                    materials=4, worker_pool=1, developed=("irrigation",),
                    buildings={"farm": {"agriculture": 1}})
    state = _state(p, row)
    snapshot = copy.deepcopy(state)
    _ = apply(state, TakeCard(0), _db())
    _ = apply(state, Build("irrigation"), _db())
    assert state == snapshot
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/engine/test_apply.py -v`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 实现 apply.py（本任务先实现六个动作分支；`_end_turn` 暂 `raise NotImplementedError`,Task 7 补全）**

```python
# tta/engine/apply.py
"""动作结算: apply(state, action, db) -> 新状态."""

from dataclasses import replace

from tta.engine.actions import (
    Action,
    Build,
    Develop,
    IllegalActionError,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    TakeCard,
)
from tta.engine.constants import POP_FOOD_COST, ROW_COSTS
from tta.engine.enums import CATEGORY_TO_BUILDING, Age, CardCategory
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB
from tta.engine.state import GameState, PlayerState, replace_player


def apply(state: GameState, action: Action, db: CardDB) -> GameState:
    """校验并结算一个动作, 返回新状态; 非法动作抛 IllegalActionError."""
    if state.terminal:
        raise IllegalActionError("game is over")
    if action not in legal_actions(state, db):
        raise IllegalActionError(f"illegal action: {action!r}")
    idx = state.current_player
    p = state.players[idx]
    if isinstance(action, TakeCard):
        return _take_card(state, idx, p, action)
    if isinstance(action, Develop):
        return _develop(state, idx, p, action, db)
    if isinstance(action, Build):
        return _build(state, idx, p, action, db)
    if isinstance(action, IncreasePopulation):
        return _increase_population(state, idx, p)
    if isinstance(action, PlayActionCard):
        return _play_action_card(state, idx, p, action, db)
    if isinstance(action, PassTurn):
        return _end_turn(state, db)
    raise IllegalActionError(f"unknown action: {action!r}")


def _take_card(state: GameState, idx: int, p: PlayerState, a: TakeCard) -> GameState:
    card_id = state.card_row[a.row_index]
    if card_id is None:
        raise IllegalActionError("empty row slot")
    row = list(state.card_row)
    row[a.row_index] = None
    p = replace(p, civil_actions=p.civil_actions - ROW_COSTS[a.row_index],
                hand_civil=p.hand_civil + (card_id,))
    return replace_player(replace(state, card_row=tuple(row)), idx, p)


def _develop(state: GameState, idx: int, p: PlayerState, a: Develop,
             db: CardDB) -> GameState:
    card = db.get(a.card_id)
    hand = list(p.hand_civil)
    hand.remove(a.card_id)
    p = replace(p, science=p.science - card.cost_science,
                hand_civil=tuple(hand))
    if card.category is CardCategory.GOVERNMENT:
        old = p.government
        p = replace(p, civil_actions=p.civil_actions - 1, government=a.card_id)
        state = replace(state, discard=state.discard + (old,))
        return replace_player(state, idx, p)
    if card.category is CardCategory.UNIT:
        p = replace(p, military_actions=p.military_actions - 1)
    else:
        p = replace(p, civil_actions=p.civil_actions - 1)
    p = replace(p, developed=p.developed + (a.card_id,))
    return replace_player(state, idx, p)


def _build(state: GameState, idx: int, p: PlayerState, a: Build,
           db: CardDB) -> GameState:
    card = db.get(a.card_id)
    btype = CATEGORY_TO_BUILDING[card.category].value
    if card.category is CardCategory.UNIT:
        p = replace(p, military_actions=p.military_actions - 1)
    else:
        p = replace(p, civil_actions=p.civil_actions - 1)
    p = replace(p, materials=p.materials - card.build_cost)

    buildings = {k: dict(v) for k, v in p.buildings.items()}
    slots = buildings.setdefault(btype, {})
    # RULES-AUDIT: 工人来源确定性选择——同类型异名建筑中时代最小、id 最小者;
    # 无升级来源时从空闲池取(legal_actions 已保证二者必有其一)
    sources = sorted(
        (cid for cid, n in slots.items() if n > 0 and cid != a.card_id),
        key=lambda cid: (list(Age).index(db.get(cid).age), cid),
    )
    if sources:
        src = sources[0]
        slots[src] -= 1
        if slots[src] == 0:
            del slots[src]
    else:
        p = replace(p, worker_pool=p.worker_pool - 1)
    slots[a.card_id] = slots.get(a.card_id, 0) + 1
    p = replace(p, buildings=buildings)
    return replace_player(state, idx, p)


def _increase_population(state: GameState, idx: int, p: PlayerState) -> GameState:
    p = replace(p, civil_actions=p.civil_actions - 1,
                food=p.food - POP_FOOD_COST,
                yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1)
    return replace_player(state, idx, p)


def _play_action_card(state: GameState, idx: int, p: PlayerState,
                      a: PlayActionCard, db: CardDB) -> GameState:
    card = db.get(a.card_id)
    hand = list(p.hand_civil)
    hand.remove(a.card_id)
    p = replace(p, civil_actions=p.civil_actions - 1, hand_civil=tuple(hand),
                food=p.food + card.gains.get("food", 0),
                materials=p.materials + card.gains.get("materials", 0),
                science=p.science + card.gains.get("science", 0),
                culture=p.culture + card.gains.get("culture", 0))
    return replace_player(replace(state, discard=state.discard + (a.card_id,)), idx, p)


def _end_turn(state: GameState, db: CardDB) -> GameState:
    """回合末结算与推进. Task 7 实现."""
    raise NotImplementedError("Task 7")
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/engine/test_apply.py -v`
Expected: PASS(10 passed；不含 PassTurn 路径）

- [ ] **Step 5: Commit**

```bash
git add tta/engine/apply.py tests/engine/test_apply.py
git commit -m "feat(engine): 六类动作结算(不含回合推进)"
```

---

### Task 7: 回合末结算 + 回合/时代推进 + 游戏结束

**Files:**
- Modify: `tta/engine/apply.py`（替换 `_end_turn` 的 NotImplementedError)
- Test: `tests/engine/test_turn.py`

**Interfaces:**
- Consumes: Task 2-6 全部；`BASE_HAPPINESS`、`FOOD_PER_WORKER`、`STARVATION_CULTURE`、`ROW_SLOTS`
- Produces:
  - `_end_turn(state, db) -> GameState`（模块内私有；外部仍只调 `apply`)
  - `happiness(db: CardDB, p: PlayerState) -> int`、`strength(db: CardDB, p: PlayerState) -> int`（公开，放在 `apply.py` 并 re-export 到 `tta/engine/__init__.py`)
- 推进规则（P0 骨架）:
  - 结算：不满（worker_pool > happiness)→ 起义，跳过生产；否则农场产食物/矿场产资源/实验室产科技/神庙产文化；然后每工人消耗 FOOD_PER_WORKER 食物，短缺每点扣 STARVATION_CULTURE 文化（下限 0)
  - 重置行动点为当前政体值；补满卡牌列空格（牌堆顶顺序）
  - 下一位玩家；回到 0 号位 = 新一轮：若 `last_round` 则终局；否则 round+1，移除卡牌列最左一张入 `removed`，整体左移（去 None 紧凑），再补满
  - 补牌时若当前牌堆空：有下一时代则切换（age 前进，启用下一牌堆）;III 时代牌堆也空 → 置 `last_round=True`，停止补牌
  - 终局：`final_scores = 各玩家 culture`，胜者在 orchestrator 计算

- [ ] **Step 1: 写失败测试**

```python
# tests/engine/test_turn.py
"""回合结算、时代推进与游戏结束测试."""

from tta.engine.actions import PassTurn
from tta.engine.apply import apply, happiness, strength
from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.state import GameState, PlayerState

GOV = GovernmentStats(civil_actions=4, military_actions=2,
                      civil_hand_limit=4, military_hand_limit=2)


def _db() -> CardDB:
    def bld(cid: str, cat: CardCategory, produces: dict) -> CardDefinition:
        return CardDefinition(id=cid, name=cid, age=Age.A, deck=DeckType.CIVIL,
                              category=cat, build_cost=2, produces=produces)

    cards = {
        "despotism": CardDefinition(id="despotism", name="专制", age=Age.A,
                                    deck=DeckType.CIVIL,
                                    category=CardCategory.GOVERNMENT, government=GOV),
        "agriculture": bld("agriculture", CardCategory.FARM, {"food": 2}),
        "bronze": bld("bronze", CardCategory.MINE, {"materials": 1}),
        "philosophy": bld("philosophy", CardCategory.LAB, {"science": 1}),
        "religion": bld("religion", CardCategory.TEMPLE, {"happiness": 1, "culture": 1}),
        "swordsmen": bld("swordsmen", CardCategory.UNIT, {"strength": 2}),
    }
    return CardDB(cards=cards, civil_decks={Age.A: ()},
                  initial_tableau=(), initial_government="despotism")


def _state(players: tuple, **kw) -> GameState:
    base = dict(round=1, age=Age.A, current_player=0,
                card_row=(None,) * 13, civil_deck=(), future_decks={},
                discard=(), removed=(), players=players, rng_state=1)
    base.update(kw)
    return GameState(**base)


def _farmer(**kw) -> PlayerState:
    base = dict(name="P0", government="despotism", food=0,
                buildings={"farm": {"agriculture": 2},
                           "mine": {"bronze": 1},
                           "lab": {"philosophy": 1}})
    base.update(kw)
    return PlayerState(**base)


def test_production_and_consumption() -> None:
    # 产: food+4, materials+1, science+1; 4 工人吃 4 => food 不变
    s = apply(_state((_farmer(),)), PassTurn(), _db())
    p = s.players[0]
    assert p.food == 0 and p.materials == 1 and p.science == 1


def test_starvation_penalty() -> None:
    # 产 2 食物需 4, 缺 2 => 文化 10 - 2*STARVATION_CULTURE = 2, 食物归零
    p = _farmer(culture=10, food=0,
                buildings={"farm": {"agriculture": 1}, "mine": {"bronze": 3}})
    s = apply(_state((p,)), PassTurn(), _db())
    assert s.players[0].culture == 2 and s.players[0].food == 0


def test_uprising_skips_production() -> None:
    # 空闲工人 3 > 满意容量 2 => 起义: 无生产
    p = _farmer(worker_pool=3)
    s = apply(_state((p,)), PassTurn(), _db())
    assert s.players[0].materials == 0 and s.players[0].science == 0


def test_happiness_and_strength() -> None:
    p = _farmer(buildings={"temple": {"religion": 2}, "unit": {"swordsmen": 3}})
    assert happiness(_db(), p) == 2 + 2  # BASE_HAPPINESS=2
    assert strength(_db(), p) == 6


def test_actions_refill_and_next_player() -> None:
    p0 = _farmer(civil_actions=0, military_actions=0)
    p1 = _farmer(name="P1")
    s = apply(_state((p0, p1)), PassTurn(), _db())
    assert s.current_player == 1
    assert s.players[0].civil_actions == 4 and s.players[0].military_actions == 2


def test_round_wrap_removes_leftmost_and_refills() -> None:
    row = ("religion", "swordsmen") + (None,) * 11
    deck = ("agriculture", "bronze", "philosophy")
    p0 = _farmer()
    s = apply(_state((p0,), card_row=row, civil_deck=deck), PassTurn(), _db())
    assert s.round == 2 and s.current_player == 0
    assert s.removed == ("religion",)
    assert s.card_row[0] == "swordsmen"
    assert s.card_row[1] == "agriculture" and s.card_row[3] == "philosophy"
    assert s.civil_deck == ()


def test_age_transition_on_empty_deck() -> None:
    row = ("swordsmen",) + (None,) * 12
    p0 = _farmer()
    s = apply(_state((p0,), card_row=row, civil_deck=(),
                     future_decks={"I": ("religion", "bronze")}), PassTurn(), _db())
    assert s.age is Age.I
    assert s.removed == ("swordsmen",)
    assert s.card_row[0] == "religion" and s.card_row[1] == "bronze"
    assert "I" not in s.future_decks


def test_last_round_then_terminal() -> None:
    p0 = _farmer(culture=10)
    # III 时代且牌堆已空: 本轮结束后终局
    s = apply(_state((p0,), age=Age.III), PassTurn(), _db())
    assert s.last_round is True
    s2 = apply(s, PassTurn(), _db())
    assert s2.terminal is True
    assert s2.final_scores == (10,)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/engine/test_turn.py -v`
Expected: FAIL(NotImplementedError: Task 7)

- [ ] **Step 3: 在 apply.py 中实现 `_end_turn` 及辅助函数**

在 `tta/engine/apply.py` 顶部 import 追加：`from tta.engine.constants import BASE_HAPPINESS, FOOD_PER_WORKER, ROW_SLOTS, STARVATION_CULTURE`、`from tta.engine.enums import BuildingType`、`from tta.engine.state import workers_total`，并用以下实现替换 `_end_turn` 占位：

```python
def happiness(db: CardDB, p: PlayerState) -> int:
    """满意容量 = 基础值 + 神庙类建筑产出."""
    total = BASE_HAPPINESS
    for cid, n in p.buildings.get(BuildingType.TEMPLE.value, {}).items():
        total += db.get(cid).produces.get("happiness", 0) * n
    return total


def strength(db: CardDB, p: PlayerState) -> int:
    """军力 = 兵种建筑产出之和(P0 无战术/领袖加成)."""
    total = 0
    for cid, n in p.buildings.get(BuildingType.UNIT.value, {}).items():
        total += db.get(cid).produces.get("strength", 0) * n
    return total


def _produce(p: PlayerState, db: CardDB, btype: BuildingType, key: str) -> int:
    return sum(db.get(cid).produces.get(key, 0) * n
               for cid, n in p.buildings.get(btype.value, {}).items())


def _settle(p: PlayerState, db: CardDB) -> PlayerState:
    """回合末: 起义判定 -> 生产 -> 食物消耗/饥荒."""
    if p.worker_pool > happiness(db, p):
        return p  # RULES-AUDIT: 起义则本回合无生产
    p = replace(p,
                food=p.food + _produce(p, db, BuildingType.FARM, "food"),
                materials=p.materials + _produce(p, db, BuildingType.MINE, "materials"),
                science=p.science + _produce(p, db, BuildingType.LAB, "science"),
                culture=p.culture + _produce(p, db, BuildingType.TEMPLE, "culture"))
    need = FOOD_PER_WORKER * workers_total(p)
    if p.food >= need:
        return replace(p, food=p.food - need)
    deficit = need - p.food
    return replace(p, food=0,
                   culture=max(0, p.culture - STARVATION_CULTURE * deficit))


def _refill_row(state: GameState) -> GameState:
    """用当前牌堆补满卡牌列空格; 牌堆空则切时代; III 空则 last_round."""
    row = list(state.card_row)
    deck = list(state.civil_deck)
    future = dict(state.future_decks)
    age = state.age
    last_round = state.last_round
    for i in range(ROW_SLOTS):
        if row[i] is not None:
            continue
        while not deck and not last_round:
            nxt = age.next()
            if nxt is None:
                last_round = True
                break
            age = nxt
            deck = list(future.pop(nxt.value, ()))
        if deck:
            row[i] = deck.pop(0)
    return replace(state, card_row=tuple(row), civil_deck=tuple(deck),
                   future_decks=future, age=age, last_round=last_round)


def _end_turn(state: GameState, db: CardDB) -> GameState:
    idx = state.current_player
    p = _settle(state.players[idx], db)
    gov = db.get(p.government).government
    if gov is None:
        raise ValueError(f"government {p.government} has no stats")
    p = replace(p, civil_actions=gov.civil_actions,
                military_actions=gov.military_actions)
    state = replace_player(state, idx, p)

    nxt = (idx + 1) % len(state.players)
    state = replace(state, current_player=nxt)
    if nxt != 0:
        return _refill_row(state)
    # 新一轮
    if state.last_round:
        scores = tuple(pl.culture for pl in state.players)
        return replace(state, terminal=True, final_scores=scores)
    row = [c for c in state.card_row if c is not None]
    removed = state.removed
    if row:
        removed = removed + (row.pop(0),)     # RULES-AUDIT: 每轮移除最左 1 张
    row += [None] * (ROW_SLOTS - len(row))
    state = replace(state, round=state.round + 1, card_row=tuple(row),
                    removed=removed)
    return _refill_row(state)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/engine/test_turn.py -v && uv run pytest -q`
Expected: PASS(8 passed)；全量通过

- [ ] **Step 5: Commit**

```bash
git add tta/engine/apply.py tests/engine/test_turn.py
git commit -m "feat(engine): 回合末结算、时代推进与游戏结束"
```

---

### Task 8: 最小牌库 + new_game 开局

**Files:**
- Create: `tta/cards/minimal.py`
- Create: `tta/engine/setup.py`
- Create: `tta/engine/__init__.py`（填充导出）
- Test: `tests/cards/test_minimal.py`, `tests/engine/test_setup.py`

**Interfaces:**
- Consumes: Task 2-7 全部；`rng_shuffle`;`INITIAL_*` 常量
- Produces:
  - `MINIMAL_DB: CardDB` — 4 时代内政牌堆各 17 张；起始台面 `("agriculture","agriculture","bronze","philosophy")`；起始政体 `"despotism"`
  - `new_game(db: CardDB, num_players: int, seed: int) -> GameState` — 洗各时代牌堆（A 为当前牌堆），发 13 张卡牌列，按起始台面初始化玩家
- 约定：起始放置工人 = farm 2 / mine 1 / lab 1（共 4),`yellow_bank = INITIAL_YELLOW - 4`,`worker_pool = 0`，行动点为起始政体值

- [ ] **Step 1: 写失败测试**

```python
# tests/cards/test_minimal.py
"""最小牌库结构测试."""

from collections import Counter

from tta.cards.minimal import MINIMAL_DB
from tta.engine.enums import Age, CardCategory


def test_deck_sizes() -> None:
    assert set(MINIMAL_DB.civil_decks) == {Age.A, Age.I, Age.II, Age.III}
    for deck in MINIMAL_DB.civil_decks.values():
        assert len(deck) == 17


def test_all_deck_cards_defined() -> None:
    for deck in MINIMAL_DB.civil_decks.values():
        for cid in deck:
            assert cid in MINIMAL_DB.cards


def test_initial_tableau_defined() -> None:
    for cid in MINIMAL_DB.initial_tableau:
        assert cid in MINIMAL_DB.cards
    assert MINIMAL_DB.initial_government in MINIMAL_DB.cards


def test_each_age_has_one_government() -> None:
    for age, deck in MINIMAL_DB.civil_decks.items():
        govs = [cid for cid in deck
                if MINIMAL_DB.cards[cid].category is CardCategory.GOVERNMENT]
        assert len(govs) == 1, age


def test_card_ids_unique_definitions() -> None:
    assert len(MINIMAL_DB.cards) == len(set(MINIMAL_DB.cards))
    counts = Counter(cid for deck in MINIMAL_DB.civil_decks.values() for cid in deck)
    assert sum(counts.values()) == 68
```

```python
# tests/engine/test_setup.py
"""开局测试."""

from tta.cards.minimal import MINIMAL_DB
from tta.engine.constants import INITIAL_YELLOW, ROW_SLOTS
from tta.engine.enums import Age
from tta.engine.setup import new_game
from tta.engine.state import workers_total


def test_new_game_basic() -> None:
    s = new_game(MINIMAL_DB, 2, seed=42)
    assert len(s.players) == 2
    assert s.age is Age.A and s.round == 1 and s.current_player == 0
    assert len(s.card_row) == ROW_SLOTS
    assert all(c is not None for c in s.card_row)
    assert len(s.civil_deck) == 17 - ROW_SLOTS  # 4
    assert set(s.future_decks) == {"I", "II", "III"}


def test_new_game_deterministic() -> None:
    assert new_game(MINIMAL_DB, 3, seed=7) == new_game(MINIMAL_DB, 3, seed=7)
    assert new_game(MINIMAL_DB, 3, seed=7) != new_game(MINIMAL_DB, 3, seed=8)


def test_player_initial_state() -> None:
    s = new_game(MINIMAL_DB, 2, seed=1)
    for p in s.players:
        assert p.government == "despotism"
        assert workers_total(p) == 4
        assert p.yellow_bank + workers_total(p) == INITIAL_YELLOW
        assert p.civil_actions == 4 and p.military_actions == 2


def test_supports_2_to_4_players() -> None:
    for n in (2, 3, 4):
        assert len(new_game(MINIMAL_DB, n, seed=1).players) == n
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/cards/test_minimal.py tests/engine/test_setup.py -v`
Expected: FAIL(ModuleNotFoundError: tta.cards.minimal)

- [ ] **Step 3: 实现 minimal.py / setup.py / engine 导出**

```python
# tta/cards/minimal.py
"""P0 最小牌库: 仅供引擎骨架验证, 非官方数值(全部 RULES-AUDIT).

每时代 17 张: 农场×3 矿场×3 实验室×2 神庙×2 兵种×2 政体×1 行动卡×4.
P1 将被正式牌库与效果原语框架取代; P2 对照规则书核对全部数值.
"""

from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDB, CardDefinition, GovernmentStats

_C = DeckType.CIVIL


def _gov(cid: str, name: str, age: Age, sci: int,
         ca: int, ma: int, hc: int, hm: int) -> CardDefinition:
    # RULES-AUDIT: 政体数值
    return CardDefinition(id=cid, name=name, age=age, deck=_C,
                          category=CardCategory.GOVERNMENT, cost_science=sci,
                          government=GovernmentStats(ca, ma, hc, hm))


def _bld(cid: str, name: str, age: Age, cat: CardCategory,
         sci: int, build: int, **produces: int) -> CardDefinition:
    # RULES-AUDIT: 造价/产出数值
    return CardDefinition(id=cid, name=name, age=age, deck=_C, category=cat,
                          cost_science=sci, build_cost=build, produces=produces)


def _act(cid: str, name: str, age: Age, **gains: int) -> CardDefinition:
    # RULES-AUDIT: 行动卡收益
    return CardDefinition(id=cid, name=name, age=age, deck=_C,
                          category=CardCategory.ACTION, gains=gains)


_CARDS: list[CardDefinition] = [
    # 起始台面(不入牌堆)
    _bld("agriculture", "农业", Age.A, CardCategory.FARM, 0, 2, food=2),
    _bld("bronze", "青铜", Age.A, CardCategory.MINE, 0, 2, materials=1),
    _bld("philosophy", "哲学", Age.A, CardCategory.LAB, 0, 3, science=1),
    _gov("despotism", "专制", Age.A, 0, 4, 2, 4, 2),
    # 时代 A
    _bld("irrigation", "灌溉", Age.A, CardCategory.FARM, 2, 2, food=2),
    _bld("iron", "铁器", Age.A, CardCategory.MINE, 2, 2, materials=2),
    _bld("alchemy", "炼金术", Age.A, CardCategory.LAB, 2, 3, science=2),
    _bld("religion", "宗教", Age.A, CardCategory.TEMPLE, 2, 3, happiness=1),
    _bld("swordsmen", "剑士", Age.A, CardCategory.UNIT, 2, 2, strength=2),
    _gov("monarchy", "君主制", Age.A, 2, 5, 3, 5, 3),
    _act("harvest_a", "丰收", Age.A, food=3),
    _act("quarry_a", "采石", Age.A, materials=3),
    # 时代 I
    _bld("selective_breeding", "选育", Age.I, CardCategory.FARM, 4, 3, food=3),
    _bld("coal", "煤炭", Age.I, CardCategory.MINE, 4, 3, materials=3),
    _bld("printing_press", "印刷术", Age.I, CardCategory.LAB, 4, 4, science=3),
    _bld("theology", "神学", Age.I, CardCategory.TEMPLE, 4, 4, happiness=1, culture=1),
    _bld("knights", "骑士", Age.I, CardCategory.UNIT, 4, 3, strength=3),
    _gov("constitutional", "君主立宪", Age.I, 4, 6, 3, 6, 3),
    _act("inspiration_i", "灵感", Age.I, science=3),
    _act("festival_i", "文化节", Age.I, culture=3),
    # 时代 II
    _bld("mechanized_agri", "机械化农业", Age.II, CardCategory.FARM, 7, 4, food=4),
    _bld("oil", "石油", Age.II, CardCategory.MINE, 7, 4, materials=4),
    _bld("scientific_method", "科学方法", Age.II, CardCategory.LAB, 7, 5, science=4),
    _bld("organized_religion", "建制宗教", Age.II, CardCategory.TEMPLE, 7, 5,
         happiness=2, culture=1),
    _bld("riflemen", "步枪兵", Age.II, CardCategory.UNIT, 7, 4, strength=5),
    _gov("republic", "共和制", Age.II, 7, 7, 2, 7, 2),
    _act("harvest_ii", "大丰收", Age.II, food=5),
    _act("industry_ii", "工业化", Age.II, materials=5),
    # 时代 III
    _bld("gmo_food", "基因作物", Age.III, CardCategory.FARM, 10, 5, food=6),
    _bld("synthetics", "合成材料", Age.III, CardCategory.MINE, 10, 5, materials=6),
    _bld("computers", "计算机", Age.III, CardCategory.LAB, 10, 6, science=6),
    _bld("mass_media", "大众传媒", Age.III, CardCategory.TEMPLE, 10, 6,
         happiness=2, culture=2),
    _bld("modern_army", "现代军队", Age.III, CardCategory.UNIT, 10, 5, strength=8),
    _gov("democracy", "民主制", Age.III, 10, 8, 3, 8, 4),
    _act("breakthrough_iii", "科技突破", Age.III, science=6),
    _act("olympics_iii", "奥林匹克", Age.III, culture=6),
]


def _deck(age: Age) -> tuple[str, ...]:
    farm = {Age.A: "irrigation", Age.I: "selective_breeding",
            Age.II: "mechanized_agri", Age.III: "gmo_food"}[age]
    mine = {Age.A: "iron", Age.I: "coal", Age.II: "oil", Age.III: "synthetics"}[age]
    lab = {Age.A: "alchemy", Age.I: "printing_press",
           Age.II: "scientific_method", Age.III: "computers"}[age]
    temple = {Age.A: "religion", Age.I: "theology",
              Age.II: "organized_religion", Age.III: "mass_media"}[age]
    unit = {Age.A: "swordsmen", Age.I: "knights",
            Age.II: "riflemen", Age.III: "modern_army"}[age]
    gov = {Age.A: "monarchy", Age.I: "constitutional",
           Age.II: "republic", Age.III: "democracy"}[age]
    acts = {Age.A: ("harvest_a", "quarry_a"), Age.I: ("inspiration_i", "festival_i"),
            Age.II: ("harvest_ii", "industry_ii"),
            Age.III: ("breakthrough_iii", "olympics_iii")}[age]
    return ((farm,) * 3 + (mine,) * 3 + (lab,) * 2 + (temple,) * 2
            + (unit,) * 2 + (gov,) + (acts[0],) * 2 + (acts[1],) * 2)


MINIMAL_DB = CardDB(
    cards={c.id: c for c in _CARDS},
    civil_decks={age: _deck(age) for age in (Age.A, Age.I, Age.II, Age.III)},
    initial_tableau=("agriculture", "agriculture", "bronze", "philosophy"),
    initial_government="despotism",
)
```

```python
# tta/engine/setup.py
"""开局构造."""

from tta.engine.constants import INITIAL_FOOD, INITIAL_MATERIALS, INITIAL_YELLOW, ROW_SLOTS
from tta.engine.enums import CATEGORY_TO_BUILDING, Age
from tta.engine.model import CardDB
from tta.engine.rng import rng_shuffle
from tta.engine.state import GameState, PlayerState


def new_game(db: CardDB, num_players: int, seed: int) -> GameState:
    """洗牌并发牌, 返回初始 GameState.

    Raises:
        ValueError: 玩家数不在 2-4.
    """
    if not 2 <= num_players <= 4:
        raise ValueError(f"players must be 2-4, got {num_players}")
    rng = seed
    decks: dict[Age, tuple[str, ...]] = {}
    for age in (Age.A, Age.I, Age.II, Age.III):
        rng, shuffled = rng_shuffle(rng, db.civil_decks[age])
        decks[age] = tuple(shuffled)

    deck_a = list(decks[Age.A])
    row = tuple(deck_a[:ROW_SLOTS])
    rest = tuple(deck_a[ROW_SLOTS:])
    future = {a.value: decks[a] for a in (Age.I, Age.II, Age.III)}

    gov = db.get(db.initial_government).government
    if gov is None:
        raise ValueError("initial government has no stats")
    placed = len(db.initial_tableau)
    buildings: dict[str, dict[str, int]] = {}
    for cid in db.initial_tableau:
        btype = CATEGORY_TO_BUILDING[db.get(cid).category].value
        slots = buildings.setdefault(btype, {})
        slots[cid] = slots.get(cid, 0) + 1

    players = tuple(
        PlayerState(
            name=f"P{i}",
            food=INITIAL_FOOD,
            materials=INITIAL_MATERIALS,
            yellow_bank=INITIAL_YELLOW - placed,
            worker_pool=0,
            buildings={k: dict(v) for k, v in buildings.items()},
            developed=db.initial_tableau,
            government=db.initial_government,
            civil_actions=gov.civil_actions,
            military_actions=gov.military_actions,
        )
        for i in range(num_players)
    )
    return GameState(round=1, age=Age.A, current_player=0, card_row=row,
                     civil_deck=rest, future_decks=future, discard=(), removed=(),
                     players=players, rng_state=rng)
```

```python
# tta/engine/__init__.py
"""规则引擎公开接口."""

from tta.engine.actions import (
    Action,
    Build,
    Develop,
    IllegalActionError,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    TakeCard,
)
from tta.engine.apply import apply, happiness, strength
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.setup import new_game
from tta.engine.state import GameState, PlayerState, state_hash, to_dict, from_dict

__all__ = [
    "Action", "Build", "CardDB", "CardDefinition", "Develop", "GameState",
    "GovernmentStats", "IllegalActionError", "IncreasePopulation", "PassTurn",
    "PlayActionCard", "PlayerState", "TakeCard", "apply", "from_dict",
    "happiness", "legal_actions", "new_game", "state_hash", "strength", "to_dict",
]
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest -q`
Expected: 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add tta/cards/minimal.py tta/engine/setup.py tta/engine/__init__.py tests/cards/test_minimal.py tests/engine/test_setup.py
git commit -m "feat: P0 最小牌库与开局构造"
```

---

### Task 9: 玩家接口 + 随机玩家 + 对局运行器 + 棋谱记录

**Files:**
- Create: `tta/agents/base.py`, `tta/agents/random_agent.py`
- Create: `tta/replay/recorder.py`
- Create: `tta/orchestrator/runner.py`
- Test: `tests/agents/test_random_agent.py`, `tests/orchestrator/test_runner.py`, `tests/replay/test_recorder.py`

**Interfaces:**
- Consumes: 之前全部
- Produces:
  - `Player` Protocol:`choose(state: GameState, legal: list[Action], db: CardDB) -> Action`
  - `RandomPlayer(seed: int)`（内部 `random.Random`，仅 agents 包可用 stdlib random)
  - `ReplayRecorder(path: Path)`:`write_meta(meta: dict)` / `write_decision(round, player, state_hash, legal_count, action)` / `write_result(result: GameResult)`；上下文管理器
  - `GameResult(scores: tuple[int, ...], winners: tuple[int, ...], rounds: int, steps: int)`
  - `run_game(db: CardDB, players: Sequence[Player], seed: int, recorder: ReplayRecorder | None = None) -> GameResult` — 超 `MAX_STEPS` 抛 `RuntimeError`；玩家返回非法动作抛 `IllegalActionError`

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/test_random_agent.py
"""随机玩家测试."""

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.engine import legal_actions, new_game


def test_choose_returns_legal_action() -> None:
    state = new_game(MINIMAL_DB, 2, seed=1)
    legal = legal_actions(state, MINIMAL_DB)
    agent = RandomPlayer(seed=99)
    for _ in range(20):
        assert agent.choose(state, legal, MINIMAL_DB) in legal


def test_deterministic() -> None:
    state = new_game(MINIMAL_DB, 2, seed=1)
    legal = legal_actions(state, MINIMAL_DB)
    a = RandomPlayer(seed=5)
    b = RandomPlayer(seed=5)
    assert [a.choose(state, legal, MINIMAL_DB) for _ in range(10)] == \
           [b.choose(state, legal, MINIMAL_DB) for _ in range(10)]
```

```python
# tests/orchestrator/test_runner.py
"""对局运行器测试."""

import pytest

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.engine import IllegalActionError
from tta.orchestrator.runner import GameResult, run_game


def _players(n: int, seed: int) -> list[RandomPlayer]:
    return [RandomPlayer(seed=seed + i) for i in range(n)]


def test_full_game_completes() -> None:
    result = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    assert isinstance(result, GameResult)
    assert len(result.scores) == 2
    assert result.winners
    assert result.rounds > 1 and result.steps > 0
    assert all(s >= 0 for s in result.scores)


def test_deterministic_same_seed() -> None:
    r1 = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    r2 = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    assert r1 == r2


def test_different_seed_differs() -> None:
    r1 = run_game(MINIMAL_DB, _players(2, 100), seed=42)
    r2 = run_game(MINIMAL_DB, _players(2, 100), seed=43)
    assert r1 != r2


def test_four_players() -> None:
    result = run_game(MINIMAL_DB, _players(4, 7), seed=1)
    assert len(result.scores) == 4


def test_agent_illegal_action_raises() -> None:
    from tta.engine import TakeCard

    class Cheater:
        def choose(self, state, legal, db):  # type: ignore[no-untyped-def]
            return TakeCard(99)

    with pytest.raises(IllegalActionError):
        run_game(MINIMAL_DB, [Cheater(), RandomPlayer(seed=1)], seed=1)
```

```python
# tests/replay/test_recorder.py
"""棋谱记录器测试."""

import json
from pathlib import Path

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.orchestrator.runner import GameResult, run_game
from tta.replay.recorder import ReplayRecorder


def test_replay_file_structure(tmp_path: Path) -> None:
    path = tmp_path / "game.jsonl"
    with ReplayRecorder(path) as rec:
        result = run_game(MINIMAL_DB, [RandomPlayer(1), RandomPlayer(2)],
                          seed=42, recorder=rec)
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert lines[0]["type"] == "meta"
    assert lines[0]["seed"] == 42
    assert lines[-1]["type"] == "result"
    assert lines[-1]["scores"] == list(result.scores)
    decisions = [x for x in lines if x["type"] == "decision"]
    assert len(decisions) == result.steps
    for d in decisions:
        assert {"round", "player", "state_hash", "legal_count", "action"} <= set(d)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/agents tests/orchestrator tests/replay -v`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 实现四个文件**

```python
# tta/agents/base.py
"""玩家抽象接口."""

from typing import Protocol

from tta.engine.actions import Action
from tta.engine.model import CardDB
from tta.engine.state import GameState


class Player(Protocol):
    """玩家协议: 面对状态与合法动作表, 返回一个动作."""

    def choose(self, state: GameState, legal: list[Action], db: CardDB) -> Action:
        """选择动作; 必须返回 legal 中的元素."""
        ...
```

```python
# tta/agents/random_agent.py
"""随机玩家: 基线与引擎模糊测试用."""

import random

from tta.engine.actions import Action
from tta.engine.model import CardDB
from tta.engine.state import GameState


class RandomPlayer:
    """均匀随机选择合法动作."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def choose(self, state: GameState, legal: list[Action], db: CardDB) -> Action:
        """从合法动作中均匀随机选一个."""
        return self._rng.choice(legal)
```

```python
# tta/replay/recorder.py
"""JSONL 棋谱记录器."""

import json
from pathlib import Path
from types import TracebackType
from typing import Any

from tta.engine.actions import action_to_dict


class ReplayRecorder:
    """逐行写入棋谱事件; 每行一个 JSON 对象, 带 type 字段."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w", encoding="utf-8")

    def __enter__(self) -> "ReplayRecorder":
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def close(self) -> None:
        """关闭文件句柄."""
        if not self._fh.closed:
            self._fh.close()

    def _write(self, obj: dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._fh.flush()

    def write_meta(self, meta: dict[str, Any]) -> None:
        """写入对局元信息(seed/模型/手册版本等)."""
        self._write({"type": "meta", **meta})

    def write_decision(self, *, round_: int, player: int, state_hash: str,
                       legal_count: int, action: Any) -> None:
        """写入一次决策."""
        self._write({
            "type": "decision",
            "round": round_,
            "player": player,
            "state_hash": state_hash,
            "legal_count": legal_count,
            "action": action_to_dict(action),
        })

    def write_result(self, result: Any) -> None:
        """写入终局结果(GameResult)."""
        self._write({
            "type": "result",
            "scores": list(result.scores),
            "winners": list(result.winners),
            "rounds": result.rounds,
            "steps": result.steps,
        })
```

```python
# tta/orchestrator/runner.py
"""对局运行器: 驱动引擎与玩家完成一整局."""

from dataclasses import dataclass
from typing import Sequence

from tta.agents.base import Player
from tta.engine.actions import IllegalActionError
from tta.engine.apply import apply
from tta.engine.constants import MAX_STEPS
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB
from tta.engine.setup import new_game
from tta.engine.state import state_hash
from tta.replay.recorder import ReplayRecorder


@dataclass(frozen=True)
class GameResult:
    """终局结果."""

    scores: tuple[int, ...]
    winners: tuple[int, ...]
    rounds: int
    steps: int


def run_game(db: CardDB, players: Sequence[Player], seed: int,
             recorder: ReplayRecorder | None = None) -> GameResult:
    """运行一整局.

    Raises:
        IllegalActionError: 玩家返回了非法动作.
        RuntimeError: 超过 MAX_STEPS(引擎疑似死循环).
    """
    state = new_game(db, len(players), seed)
    if recorder:
        recorder.write_meta({
            "seed": seed,
            "players": [p.name for p in state.players],
            "agents": [type(a).__name__ for a in players],
        })
    steps = 0
    while not state.terminal:
        if steps >= MAX_STEPS:
            raise RuntimeError(f"step limit {MAX_STEPS} exceeded")
        legal = legal_actions(state, db)
        actor = players[state.current_player]
        action = actor.choose(state, legal, db)
        if action not in legal:
            raise IllegalActionError(
                f"agent {type(actor).__name__} returned illegal action {action!r}")
        if recorder:
            recorder.write_decision(round_=state.round,
                                    player=state.current_player,
                                    state_hash=state_hash(state),
                                    legal_count=len(legal), action=action)
        state = apply(state, action, db)
        steps += 1

    if state.final_scores is None:
        raise RuntimeError("terminal state without final scores")
    scores = state.final_scores
    best = max(scores)
    result = GameResult(scores=scores,
                        winners=tuple(i for i, s in enumerate(scores) if s == best),
                        rounds=state.round, steps=steps)
    if recorder:
        recorder.write_result(result)
    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest -q`
Expected: 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add tta/agents tta/replay tta/orchestrator tests/agents tests/orchestrator tests/replay
git commit -m "feat: 玩家接口、随机玩家、运行器与棋谱记录"
```

---

### Task 10: CLI + 属性测试 + 黄金回归

**Files:**
- Modify: `tta/cli/main.py`（替换占位）
- Test: `tests/cli/__init__.py`, `tests/cli/test_cli.py`
- Test: `tests/property/test_invariants.py`
- Test: `tests/golden/test_golden_game.py`

**Interfaces:**
- Consumes: 之前全部
- Produces:
  - CLI:`tta selfplay [--players 2..4] [--seed N] [--games N] [--out DIR]`、`tta replay FILE`
  - 不变量断言函数 `assert_invariants(state, db, universe)`(property 测试内定义，后续阶段复用思路）

- [ ] **Step 1: 写失败测试**

```python
# tests/cli/test_cli.py
"""CLI 冒烟测试."""

import json
from pathlib import Path

from tta.cli.main import main


def test_selfplay_writes_replay(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    main(["selfplay", "--players", "2", "--seed", "42", "--games", "1",
          "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert "winner" in out
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    first = json.loads(files[0].read_text().splitlines()[0])
    assert first["type"] == "meta"


def test_replay_command(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    main(["selfplay", "--players", "2", "--seed", "42", "--games", "1",
          "--out", str(tmp_path)])
    capsys.readouterr()
    file = next(tmp_path.glob("*.jsonl"))
    main(["replay", str(file)])
    out = capsys.readouterr().out
    assert "scores" in out and "seed: 42" in out
```

```python
# tests/property/test_invariants.py
"""属性测试: 任意随机对局中引擎不变量恒成立."""

from collections import Counter

import pytest

from tta.cards.minimal import MINIMAL_DB
from tta.engine import apply, legal_actions, new_game
from tta.engine.constants import INITIAL_YELLOW, ROW_SLOTS
from tta.engine.state import GameState, workers_total


def _universe() -> tuple[Counter, Counter]:
    """全部卡牌(牌堆合计)与每名玩家的起始卡牌."""
    deck_total: Counter = Counter()
    for deck in MINIMAL_DB.civil_decks.values():
        deck_total.update(deck)
    per_player: Counter = Counter(MINIMAL_DB.initial_tableau)
    per_player[MINIMAL_DB.initial_government] += 1
    return deck_total, per_player


def _cards_in_state(state: GameState) -> Counter:
    c: Counter = Counter()
    c.update(x for x in state.card_row if x is not None)
    c.update(state.civil_deck)
    for deck in state.future_decks.values():
        c.update(deck)
    c.update(state.discard)
    c.update(state.removed)
    for p in state.players:
        c.update(p.hand_civil)
        c.update(p.developed)
        c[p.government] += 1
    return c


def _assert_invariants(state: GameState, expected_cards: Counter) -> None:
    assert len(state.card_row) == ROW_SLOTS
    for p in state.players:
        assert p.materials >= 0 and p.food >= 0
        assert p.science >= 0 and p.culture >= 0
        assert p.civil_actions >= 0 and p.military_actions >= 0
        assert p.yellow_bank >= 0 and p.worker_pool >= 0
        assert p.yellow_bank + workers_total(p) == INITIAL_YELLOW
    assert _cards_in_state(state) == expected_cards


@pytest.mark.parametrize("seed", range(10))
def test_random_game_invariants(seed: int) -> None:
    import random

    rng = random.Random(seed)
    state = new_game(MINIMAL_DB, 2, seed=seed)
    deck_total, per_player = _universe()
    expected = deck_total + per_player + per_player  # 2 名玩家
    _assert_invariants(state, expected)
    while not state.terminal:
        legal = legal_actions(state, MINIMAL_DB)
        state = apply(state, rng.choice(legal), MINIMAL_DB)
        _assert_invariants(state, expected)
    assert state.final_scores is not None
```

```python
# tests/golden/test_golden_game.py
"""黄金回归: 固定种子对局的终局指纹不得变化."""

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.orchestrator.runner import run_game

# 首次实现后按 Step 4 跑一次实际对局, 将输出的 (scores, rounds, steps) 回填
EXPECTED_SCORES = (0, 0)      # PLACEHOLDER-ON-FIRST-RUN
EXPECTED_ROUNDS = 0           # PLACEHOLDER-ON-FIRST-RUN
EXPECTED_STEPS = 0            # PLACEHOLDER-ON-FIRST-RUN


def test_golden_game() -> None:
    result = run_game(MINIMAL_DB, [RandomPlayer(11), RandomPlayer(22)], seed=42)
    assert result.scores == EXPECTED_SCORES
    assert result.rounds == EXPECTED_ROUNDS
    assert result.steps == EXPECTED_STEPS
```

（黄金测试的占位值在 Step 4 中由实现者跑一次实际对局后回填，之后该测试即锁死引擎行为；此后任何改动若改变指纹，必须能解释原因。)

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/cli -v`
Expected: FAIL(`main` 不接受参数）

- [ ] **Step 3: 实现 CLI**

```python
# tta/cli/main.py
"""命令行入口: tta selfplay / tta replay."""

import argparse
import json
import sys
from pathlib import Path

from tta.agents.random_agent import RandomPlayer
from tta.cards.minimal import MINIMAL_DB
from tta.orchestrator.runner import run_game
from tta.replay.recorder import ReplayRecorder


def _cmd_selfplay(args: argparse.Namespace) -> int:
    out = Path(args.out)
    for g in range(args.games):
        seed = args.seed + g
        players = [RandomPlayer(seed=seed * 100 + i) for i in range(args.players)]
        path = out / f"selfplay_seed{seed}_game{g}.jsonl"
        with ReplayRecorder(path) as rec:
            result = run_game(MINIMAL_DB, players, seed=seed, recorder=rec)
        print(f"game {g}: seed={seed} rounds={result.rounds} "
              f"scores={list(result.scores)} winner={list(result.winners)} "
              f"-> {path}")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    lines = [json.loads(x) for x in Path(args.file).read_text().splitlines()]
    meta = next(x for x in lines if x["type"] == "meta")
    result = next(x for x in lines if x["type"] == "result")
    decisions = sum(1 for x in lines if x["type"] == "decision")
    print(f"seed: {meta['seed']}, players: {meta['players']}")
    print(f"decisions: {decisions}, rounds: {result['rounds']}, "
          f"scores: {result['scores']}, winners: {result['winners']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口."""
    parser = argparse.ArgumentParser(prog="tta")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("selfplay", help="随机/AI 玩家自我对弈")
    sp.add_argument("--players", type=int, default=2, choices=[2, 3, 4])
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--games", type=int, default=1)
    sp.add_argument("--out", default="replays")
    sp.set_defaults(func=_cmd_selfplay)

    rp = sub.add_parser("replay", help="查看棋谱摘要")
    rp.add_argument("file")
    rp.set_defaults(func=_cmd_replay)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行测试并回填黄金指纹**

Run: `uv run pytest tests/cli tests/property -v`（应全 PASS)
然后跑一次黄金对局取得真实指纹：

Run: `uv run python -c "from tta.agents.random_agent import RandomPlayer; from tta.cards.minimal import MINIMAL_DB; from tta.orchestrator.runner import run_game; r = run_game(MINIMAL_DB, [RandomPlayer(11), RandomPlayer(22)], seed=42); print(r.scores, r.rounds, r.steps)"`

把输出的 `(scores, rounds, steps)` 回填到 `tests/golden/test_golden_game.py` 的三个 `EXPECTED_*` 常量，并删除 `PLACEHOLDER-ON-FIRST-RUN` 注释行。

Run: `uv run pytest -q && uv run ruff check tta tests`
Expected: 全量 PASS;lint 无错误

- [ ] **Step 5: 手动冒烟 + Commit**

Run: `uv run tta selfplay --players 3 --seed 7 --games 2 --out /tmp/tta_replays && uv run tta replay /tmp/tta_replays/selfplay_seed7_game0.jsonl`
Expected: 打印两局结果与棋谱摘要

```bash
git add tta/cli/main.py tests/cli tests/property tests/golden
git commit -m "feat: CLI selfplay/replay、属性测试与黄金回归"
```

---

## P0 完成判定（验收清单）

- [ ] `uv run pytest -q` 全绿（含 10 个种子的属性测试与黄金回归）
- [ ] `uv run ruff check tta tests` 无错误
- [ ] `uv run tta selfplay --players 4 --games 3` 能跑完并产出 3 个 JSONL 棋谱
- [ ] 同一种子两次 `run_game` 结果逐比特一致（确定性测试覆盖）
- [ ] `tta/engine/` 无对上层包的 import(`grep -r "from tta.agents\|from tta.orchestrator\|from tta.cli\|from tta.cards" tta/engine/` 应为空）

## 后续阶段衔接（不在本计划）

- P1: 正式效果原语框架 + MVP 牌组替换 `minimal.py` + 腐败/手牌弃置等规则补全
- P2: 全牌库 + RULES-AUDIT 清单逐项核对（需要官方规则书）
