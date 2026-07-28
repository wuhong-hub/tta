# P3: 人类玩家界面 + 引擎收口 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) 收口全部遗留引擎项（runner 闸口、公共阵型区、弃牌时序、每回合选择类卡牌效果）;(2) 实现人类玩家终端界面（棋盘渲染 + 动作菜单 + 悔棋），支持人机混编对局；(3) 棋谱回放增强（回合摘要、跳转到指定手、文本战报）。

**Architecture:** 引擎侧新增 `tta/engine/choices.py`（回合开始选择 pending）与公共阵型区字段；界面侧新增 `tta/ui/render.py`（纯函数渲染，输出字符串，快照测试）与 `tta/ui/menu.py` + `tta/agents/human_player.py`；回放增强在 `tta/replay/`。行式打印（无 curses 依赖），渲染与 IO 分离。

**Tech Stack:** Python 3.12（语法底线 3.10)、uv、pytest、ruff；零运行时第三方依赖。

## Global Constraints

- 沿用全部既有约束：Python >=3.10、4 空格缩进、类型注解、frozen dataclass、嵌套 dict 修改前整体复制、`apply(state, action, db)` 返回新状态、非法抛 `IllegalActionError`、engine 不得 import agents/orchestrator/cli/cards/**ui**;rng 只走 rng.py
- 测试命令：`uv run pytest <path> -v`;lint:`uv run ruff check tta tests`；每任务提交前全量绿
- **ui 包只依赖 engine/agents/orchestrator 的公开接口，不得反向被依赖**；渲染函数纯函数（state → str),IO 全部在 menu/human_player
- 隐藏信息：人机界面渲染对手时过滤军事手牌/军事牌堆/未来事件（仅显示数量）;P4 复用此过滤层
- 黄金指纹在引擎收口任务（T1-T6）后重建一次；界面任务不应再改变引擎轨迹

## 背景与依据

- 交办清单：docs/deferred.md(22 项卡牌互动 + 5 项引擎简化）、P2 终审裁定（docs/superpowers/progress.md)
- 数据权威：卡牌数值表 PDF（第 2 页领袖、第 3 页条约/阵型）、中文规则书 PDF
- 关键遗留口径：ColonizeSacrifice 复合动作需要 runner 闸口支持（P2 遗留 #9)；公共阵型区（规则书 p3)；弃牌先于抓牌（规则书 p6 回合结束阶段顺序）

---

### Task 1: runner 合法性闸口改造 + 复合动作协议

**Files:**
- Modify: `tta/orchestrator/runner.py`、`tta/engine/apply.py`、`tta/engine/legal.py`
- Test: `tests/orchestrator/test_runner.py`、`tests/engine/test_colonization.py`

**Interfaces:**
- 问题：runner 目前 `action not in legal → IllegalActionError`，会把 apply 明确支持的复合动作（ColonizeSacrifice 精确子集）拒之门外；人类/LLM 玩家必须能提交此类动作
- 方案：engine 新增 `legal.is_self_validating(action: Action) -> bool`（返回 True 的动作类型由 apply 独立校验合法性，当前仅 ColonizeSacrifice);runner 闸口改为 `action in legal or is_self_validating(action)`，不满足才抛
- apply 侧保持独立校验（卡 id 存在、属于该玩家、工人数、军力合计 ≥ 出价）；非法抛 IllegalActionError（类型一致）
- 顺手：为 legal 增加 ColonizeSacrifice 的**常用子集枚举**（全部 ≤N 张单位的组合，N≤3，超限时只给全选锚点）改善 agent 体验

- [ ] **Step 1-5:** TDD（精确子集经 runner 通过、非法子集被 apply 拒、闸口防作弊仍有效）→ commit `feat: runner 闸口支持自校验复合动作 + 殖民牺牲子集枚举`

---

### Task 2: 公共阵型区建模

**Files:**
- Modify: `tta/engine/state.py`、`tta/engine/military.py`、`tta/engine/apply.py`、`tta/engine/turn.py`、`tta/engine/legal.py`
- Test: `tests/engine/test_tactics.py`

**Interfaces:**
- GameState 新增 `public_tactics: tuple[str, ...]`（公共阵型区，序列化覆盖）
- 官方口径（规则书 p3)：阵型牌公开时放入公共阵型区（无数量限制；同名牌可覆盖或从游戏中移除）;CopyTactics 的合法来源 = 公共阵型区全部卡（不再局限于对手当前激活阵型）
- 时序：PlayTactics → 私有激活（次回合开始时强制公开 → 卡进入 public_tactics);CopyTactics → 激活（引用公共区卡，不移动）；玩家换新阵型时旧激活阵型若已公开则**留在公共区**（可被他人复制），同名牌按规则覆盖或入 removed
- 废弃 T13 的"旧阵型入 removed"过渡口径；tactics_copied 字段语义复查（公共区建模后幻影卡问题应自然消解，若已冗余则移除并迁移测试）

- [ ] **Step 1-5:** TDD（公开入区、复制来源为公共区、换阵留区、同名覆盖/移除、序列化）→ commit `feat(engine): 公共阵型区建模`

---

### Task 3: 弃牌决策先于抓牌（回合末逐步等待）

**Files:**
- Modify: `tta/engine/turn.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_military_draw.py`、`tests/engine/test_turn_machine.py`

**Interfaces:**
- 官方顺序（规则书 p6)：弃置多余军事牌 → 起义检定 → 生产 → 抓军事牌 → 恢复行动点。现状：弃牌 pending 在整个回合末流程之后才结算（次优口径，响应者能看到抓牌结果、可弃新抓的牌）
- 改法：end_of_turn 分阶段化：阶段 1 检查超限 → 若有 discard pending，压入并**立即返回**（阶段标记入 pending context `{"resume": "production"}`)；弃牌 pending 全部结算后（count 归零 pop),apply 调用 turn 的续跑函数从生产阶段继续
- 续跑不可重入已完成的阶段（腐败/生产/抓牌只执行一次）；起义检定在生产前、弃牌后（官方顺序内）
- 黄金指纹预期变化（轨迹重排），重建

- [ ] **Step 1-5:** TDD（弃牌后才抓牌、续跑不重复、超限+起义组合、指纹重建）→ commit `fix(engine): 弃多余军事牌先于生产与抓牌(逐步等待)`

---

### Task 4: 回合开始选择机制 + Churchill + Bill Gates

**Files:**
- Create: `tta/engine/choices.py`
- Modify: `tta/engine/turn.py`、`tta/engine/effects.py`、`tta/engine/economy.py`、`tta/engine/civ.py`
- Test: `tests/engine/test_choices.py`

**Interfaces:**
- 通用机制：回合开始阶段（公开阵型后、POLITICS 前）检查该玩家"回合开始选择"类效果，有则压 pending kind="turn_start_choice"(responder=自己）;legal 提供对应选项动作 + DeclineResponse（选择默认可放弃？——以卡文本为准，Churchill 为二选一必选）
- `ChooseTurnStart(option: str)` 动作（序列化）
- **Churchill**（领袖）:`+3 文化` 或 `3 科技 + 3 资源（本回合军事建造用,turn_discounts["unit_build"]=3 + science+3)`，每回合二选一
- **Bill Gates**（领袖）:(a) 实验室按矿山方式产资源——economy.produce("resource") 时实验室卡（LAB 类别）工人也各产 1 蓝点到实验室卡，resource_total 计入实验室蓝点（token_value=等级？——按规则书附录：实验室牌上每个蓝色标记代表与卡牌等级相同数量的资源，即 token_value = 时代等级 A=1/I=2/II=3/III=4);(b) 被替换离场时：+文化 = Σ 有工人实验室 × 等级（即时结算，hook 在 PlayLeader 替换处；终局已在 T12 实现）

- [ ] **Step 1-5:** TDD（选择 pending 流程、Churchill 两选项、Gates 生产/结算/支付全链）→ commit `feat(engine): 回合开始选择机制与 Churchill/Bill Gates`

---

### Task 5: trade_routes / scientific_cooperation 条约效果

**Files:**
- Modify: `tta/engine/economy.py`、`tta/engine/effects.py`、`tta/engine/legal.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_pacts.py`（扩充）

**Interfaces:**
- **trade_routes_agreement**:A 侧：每回合一次，支付资源费时可用 1 食物当 1 资源；B 侧反之（每回合一次，支付食物费用时用 1 资源当 1 食物）。实现：economy.pay 增加可选替换参数（默认关）;legal/apply 在支付处检测条约与"本回合未用"标记（turn_discounts 记录）；引擎确定性口径：仅当主货币不足时启用替换（注释 SIMPLIFICATION；官方为玩家主动选择，P4 可改显式）
- **scientific_cooperation**:A/B 任一側研发科技 −2 科技费，另一方付 1 科技（对方不足时不扣？——以 PDF p3 文本为准："Discover a technology for -2⚪, other player pays 1💡")。实现：DevelopTech 费用 −2（双方可用），结算时对方 science −1（下限 0)；每回合一次？——以 PDF 文本为准，报告说明

- [ ] **Step 1-5:** TDD（替换支付、每回合一次、研发折扣与对方扣费）→ commit `feat(engine): trade_routes 与 scientific_cooperation 条约效果`

---

### Task 6: shakespeare / bach 折扣 + masonry 建造系列

**Files:**
- Modify: `tta/engine/effects.py`、`tta/engine/legal.py`、`tta/engine/apply.py`
- Test: `tests/cards/test_age_ii.py`（扩充）

**Interfaces:**
- **shakespeare**（时代 II 领袖，静态 +1 笑脸已实现）：图书馆/剧院配对折扣——以 PDF p2 文本为准："disc. theatre for -1⚪(资源) and build for -1🪨 if you have lib. and vice versa"。实现为建造/升级费用钩子（legal 与 apply 同口径）
- **j_s_bach**（时代 II 领袖，每剧院 +1 文化已实现）:disc. theaters for -2（以 PDF 文本为准）；每回合一次可用 1 白点把任一城市建筑升级为同级或 +1 级剧院（新动作或 Upgrade 特判，报告说明口径）
- **masonry 系列**(masonry_i/architecture_ii/engineering_iii，特殊科技 CONSTRUCTION)：建造奇迹时每 1 白点可建 X 阶段（X=2/3/4)、城市建筑建造 -1 资源/级（max 1/2/3)——以 PDF p1 Construction 区文本为准；BuildWonderStage 改造：一次动作建多阶段（费用求和、蓝点逐阶段盖）

- [ ] **Step 1-5:** TDD（配对折扣、bach 升级、masonry 多阶段与折扣）→ commit `feat(cards): shakespeare/bach/masonry 系列效果`

---

### Task 7: 棋盘渲染器（ui/render.py)

**Files:**
- Create: `tta/ui/__init__.py`、`tta/ui/render.py`
- Test: `tests/ui/test_render.py`

**Interfaces:**
- 纯函数：`render_game(state: GameState, db: CardDB, seat: int) -> str` — 以 seat 视角渲染整屏（隐藏信息过滤：对手军事手牌只显示数量，军事牌堆/未来事件只显示数量）
- 组成：标题行（时代/轮次/相位/当前玩家）→ 卡牌列（13 格：序号/费用/卡名）→ 当前事件堆顶？（暗置不显示，仅数量）→ 各对手摘要（文化/科技/军力/笑脸、领袖/奇迹/阵型/殖民地、建筑工人分布）→ 你的面板详情（轨道数值、工人、手牌分组[内政/军事]、奇观进度、行动点）
- 渲染动作菜单：`render_actions(legal: list[Action], db: CardDB) -> str` — 分组编号（拿牌/研发/建造/升级/人口/领袖/奇迹/行动卡/政治/响应/其他）
- 快照测试：固定夹具 state，渲染输出与快照字符串比对（存 tests/ui/snapshots/ 或直接内联）

- [ ] **Step 1-5:** 实现 + 快照测试 → commit `feat(ui): 棋盘与动作菜单渲染器`

---

### Task 8: HumanPlayer + 动作菜单 + 悔棋

**Files:**
- Create: `tta/ui/menu.py`、`tta/agents/human_player.py`
- Modify: `tta/cli/main.py`(`tta play` 命令）、`tta/orchestrator/runner.py`（状态栈支持悔棋钩子）
- Test: `tests/agents/test_human_player.py`、`tests/ui/test_menu.py`

**Interfaces:**
- `HumanPlayer(input_fn=input, output_fn=print)` 实现 `choose(state, legal, db)`:render_game → render_actions → 读编号 → 返回动作；支持 `u`(悔棋，经 runner 状态栈回退到上一次自己决策前）、`?`(重复显示）、`q`(保存棋谱退出）
- 复合动作引导：ColonizeSacrifice 逐张询问单位卡（y/n）直到军力达标；BuildWonderStage 多阶段（T6 后）询问阶段数
- runner 增加可选 `history: list[GameState]` 记录（悔棋与回放用，默认开）;`tta play --seat 0 --ai 3 --seed N`:HumanPlayer + N 个 RandomPlayer 混编
- 输入输出注入（input_fn/output_fn）保证可测试：测试用脚本化输入序列驱动整局

- [ ] **Step 1-5:** TDD（脚本化输入跑通人机局、悔棋回退、保存退出）+ 手动冒烟 → commit `feat: 人类玩家界面与 tta play`

---

### Task 9: 棋谱回放增强

**Files:**
- Modify: `tta/replay/recorder.py`、`tta/cli/main.py`
- Create: `tta/replay/report.py`
- Test: `tests/replay/test_report.py`

**Interfaces:**
- `tta replay FILE [--turn N] [--report]`
- 回合摘要：按 round 分组列出各玩家决策数与关键事件（时代切换/战争/侵略/殖民/奇观完成——从 decision 动作类型聚合）
- `--turn N`：利用确定性从 meta.seed 重放到第 N 个 decision 前的状态，调 render_game 渲染当时棋盘（seat 视角可选 `--seat`)
- `--report`：导出文本战报（回合摘要 + 终局 + 关键转折点），供 P5 复盘智能体使用的格式预演
- recorder meta 补充 `card_db_version`/`engine_version`（当前 git commit 或包版本），回放兼容性提示

- [ ] **Step 1-5:** TDD（摘要聚合、跳转渲染、战报导出）→ commit `feat(replay): 回合摘要、指定手跳转与文本战报`

---

### Task 10: 回归重建 + deferred 清零核对

**Files:**
- Modify: `tests/property/test_invariants.py`（公共阵型区/选择机制不变量）、`tests/golden/test_golden_game.py`（最终指纹）、`docs/deferred.md`
- Test: 全量回归 + CLI `tta play` 脚本化冒烟

**收尾清单：**
- 属性测试补：公共阵型区守恒、turn_start_choice 不泄漏、多阶段奇迹蓝点守恒
- deferred.md 清零核对：22 项卡牌互动逐项标记（已实现/永久例外及理由）；引擎简化 5 项状态更新
- 黄金指纹最终重建；CLI 2/3/4 人冒烟 + 1 局脚本化人机对局
- 规则歧义清单更新（docs/deferred.md 或单独 docs/rule-interpretations.md：引擎约定与无明文歧义汇总，供用户对实体牌抽查）

- [ ] **Step 1-5:** 全量绿 + 文档更新 → commit `test: P3 回归重建与 deferred 清零核对`

---

## P3 完成判定

- [ ] 全测试绿 + lint 干净；`tta play` 脚本化人机对局跑通；悔棋可用
- [ ] 对手军事手牌在渲染层不可见（快照测试锁定）
- [ ] deferred.md 22 项互动清零（已实现或永久例外附理由）
- [ ] `tta replay --turn N --report` 可用
- [ ] 黄金回归锁定；CLI 2/3/4 人冒烟通过

## 用户抽查清单（P3 验收）

1. 亲自打一局 `tta play`（操作流畅性、信息展示、悔棋）
2. 抽 Churchill/Bill Gates/trade_routes/shakespeare/masonry 对照实体牌效果
3. 公共阵型区、弃牌先后的对局体验（规则书 p3/p6)

## 后续阶段衔接

- P4:LLM 玩家：状态视图生成器（复用 ui/render 的文本化与过滤层，但面向 token 优化而非人类阅读）、多模型配置、决策协议（JSON action_id + reasoning)、成本统计
- P5：手册迭代闭环（复盘智能体读 `--report` 战报与 JSONL 棋谱）
