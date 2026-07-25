# 《历史巨轮》AI 自我对弈策略研究工具 — 设计文档

日期：2026-07-24
状态：已获用户批准

## 1. 目标与范围

开发一个助手工具，让 AI（LLM 智能体）能够完整模拟《历史巨轮：文明新故事》(Through the Ages: A New Story of Civilization) 的对战，通过自我对弈 + 复盘迭代，持续发现更优秀的游戏策略。

**已定边界：**

- 规则范围：**完整官方规则**，支持 2-4 人
- AI 方式：LLM 智能体对弈 + **共享策略手册迭代**
- 技术方案：确定性引擎 + 数据驱动卡牌 + 合法动作接口（方案 A）
- 语言：Python 3.10+
- 交互：CLI + 结构化日志；支持人机对战
- LLM 接入：多模型可配置（玩家/复盘等角色独立配置）
- 手册晋级：自动锦标赛晋级（带统计检验，非人工审批）
- **关键约束：引擎可采用渐进牌库验证可用性，但自我对弈迭代（手册演化）必须在牌库 100% 完成并通过回归后才启动**

## 2. 整体架构

```
┌─────────────────────────────────────────────┐
│ cli        命令行入口：selfplay / play /     │
│            tournament / replay / handbook    │
├─────────────────────────────────────────────┤
│ orchestrator  对局运行器：驱动引擎+智能体,    │
│               锦标赛调度, 产出棋谱            │
├──────────────┬──────────────────────────────┤
│ agents       │ handbook                     │
│ LLM玩家/随机  │ 策略手册: 存储+复盘智能体     │
│ 玩家/人类玩家 │ +版本演化                     │
├──────────────┴──────────────────────────────┤
│ engine       规则引擎(唯一规则权威):         │
│   游戏状态 / 合法动作生成 / 动作结算 /        │
│   回合流程 / 种子随机 / 状态序列化            │
├─────────────────────────────────────────────┤
│ cards        卡牌数据库: 数据驱动的卡牌定义   │
│              + 效果原语解释器                │
└─────────────────────────────────────────────┘
```

单向依赖：上层可依赖下层，下层绝不 import 上层。engine + cards 可脱离 LLM 独立运行（随机玩家互弈 = 免费的引擎模糊测试）。

### 模块职责

- **cards** — 全部卡牌（内政牌/军事牌/领袖/奇观/行动牌/事件牌等）以结构化 Python 数据定义；声明式效果原语 + 少量特殊卡处理函数
- **engine** — 纯 Python、无 LLM 依赖。`legal_actions(state)` 与 `apply(state, action)` 两个核心函数；seeded RNG；状态可 JSON 序列化
- **agents** — 玩家抽象接口 `choose(state_view, legal_actions) -> action`。实现：LLM 玩家、随机玩家（基线/测试）、人类玩家（终端交互）
- **handbook** — 策略手册为带 git 版本的 Markdown 文件；复盘智能体读棋谱 → 写对局总结 → 提议手册修订
- **orchestrator** — 把引擎和 N 个智能体串成一局；并发多局；锦标赛（多手册版本对决）
- **cli** — `tta selfplay` / `tta play`（人机）/ `tta tournament` / `tta replay <file>` / `tta handbook show|diff` / `tta cards status` / `tta stats`

## 3. 引擎核心：状态模型与动作系统

### 3.1 游戏状态

纯数据树，可完整 JSON 序列化：

```
GameState
├── round, phase, current_player, seed/rng_state
├── card_row: [CardInstance × 13]        # 卡牌轮抽列(含费用位置)
├── decks: {A/I/II/III 内政牌堆, 军事牌堆, 当前事件牌...}
├── removed_cards / discard
├── players: [PlayerState × 2-4]
│   ├── 面板: culture, science, strength, 笑脸, 黄点/蓝点库存
│   ├── 工人池/人口轨道
│   ├── 建筑: 农场/矿场/实验室/神庙/兵营(各含工人分布)
│   ├── 手牌: 内政手牌 / 军事手牌
│   ├── 已出领袖、奇观进度、殖民地、特殊科技
│   └── 本轮行动点: 白点(civil) / 红点(military)
└── pending: 待处理事件/侵略/战争结算队列
```

### 3.2 动作系统

- 动作是扁平可序列化结构：`{"type": "take_card", "row_index": 3}`、`{"type": "increase_population"}`、`{"type": "build", "building": "iron", ...}`、`{"type": "play_aggression", "card": ..., "target": ...}` 等约 30-40 种动作类型
- 核心函数：`legal_actions(state) -> list[Action]`；`apply(state, action) -> state`
- **`apply` 返回新状态（不可变式）**，免费获得悔棋/回放/分支搜索能力
- 多步交互（战争结算、侵略响应、选牌事件）用 **pending 队列**分解：动作可能产生新的待决决策点，`current_player` 切换到需响应的玩家，引擎统一驱动。显式队列，不用回调

### 3.3 回合流程

按官方规则硬编码为状态机：补充卡牌列 → 政治行动（事件/侵略/战争）→ 白点/红点行动阶段（循环至玩家 pass）→ 回合末结算（生产/消耗/腐败/文化科技得分/弃牌）。卡牌特殊效果以监听器钩子挂在对应阶段。

2-4 人规则差异（卡牌列数量、行动点、奇观上限等）在 `legal_actions` 中集中分支，是规则正确性的主要测试面。

## 4. 卡牌系统与效果原语

### 4.1 卡牌数据结构

每张牌一个不可变数据记录，同时携带结构化效果（给引擎）与原文文本（给 LLM）：

```python
Card(
    id="code_of_laws", name="法典", age=Age.A, deck=DeckType.CIVIL,
    category=CardCategory.GOVERNMENT,
    cost_science=6, cost_actions=1,
    text="法典：...",                      # 原始规则文本,直接进 LLM 上下文
    effects=[ModifyCivilActions(+1), ...], # 结构化效果原语
)
```

### 4.2 效果原语

约 20-30 个声明式原语覆盖 ~90% 的牌：`GainCulture(n)`、`ModifyProduction(building, n)`、`ExtraAction(color, n)`、`Discount(category, n)`、`BuildWonderStage()`、`WarBonus(...)` 等。原语实现 `apply()` 与 `revoke()`（领袖死亡/政体更换时移除）。

### 4.3 特殊牌

剩余 ~10% 无法声明式表达的牌写小型处理函数，注册到 `SPECIAL_HANDLERS[card_id]`，设计上压到最少。

### 4.4 组织与完成度

- 按时代+牌堆分文件：`cards/age_a_civil.py`、`cards/age_i_military.py` 等
- 每张牌有 `verified: bool` 元数据（单元测试验证后置真）；`tta cards status` 报告实现完成度
- 生成 LLM 状态视图时直接拼接相关卡牌的 `text` 字段

### 4.5 卡牌实现路线图

1. **MVP 牌组**：核心机制运转的最小牌集（基础农场/矿场/实验室/神庙/兵营升级线 + 基础政体 + 简单行动牌），约 40-60 张，仅用于验证引擎
2. **逐时代补全**：A → I → II → III，每时代完成后跑回归
3. **全部事件/侵略/战争牌**（军事互动最晚做，依赖 pending 队列成熟）
4. 牌库 100% + 回归通过 ⇒ 才启动手册迭代

## 5. LLM 智能体与手册迭代闭环

### 5.1 决策协议

```
[系统] 你是历史巨轮玩家 + 最新策略手册(相关章节)
[用户] 当前状态视图:
  - 你的面板(资源/科技/文化/军力/建筑/手牌含卡牌原文)
  - 对手公开信息(面板/军力/已出领袖奇观)
  - 卡牌列及费用、待决事件
  - 合法动作列表(编号 + 人类可读描述)
请以 JSON 回复: {"action_id": N, "reasoning": "..."}
```

- **状态视图生成器**：GameState → token 可控的自然语言+表格混合文本；隐藏信息严格过滤（对手手牌/军事牌堆不可见）
- `reasoning` 必填，进棋谱，是复盘核心素材
- 手册按 game phase 检索相关章节注入（开局/军事/终局），控制 token 成本

### 5.2 迭代闭环（牌库完成后启用）

```
跑 K 局自弈(并发) → JSONL 棋谱
   → 复盘智能体逐局分析: 转折点、失误、亮点(读 reasoning + 状态快照)
   → 汇总智能体跨局提炼: 哪些经验被反复验证/推翻
   → 生成手册修订提案(diff 形式)
   → 新版本手册进入锦标赛: 新手册玩家 vs 旧手册玩家, 跑 N 局
   → 胜率显著更优(最小局数 + 置信区间检验)则自动晋级
```

- 手册用 git 管理，每次修订一个 commit，可查 diff/blame 演化史
- 防过拟合：最小局数 + 简单统计检验，避免单次运气改写手册
- 成本记录：每局决策数、token 用量记入棋谱元数据，`tta stats` 可查

### 5.3 多模型配置

`agents.yaml` 定义角色→模型映射（player_1..4、reviewer、summarizer），通过 provider 抽象层支持 Anthropic/OpenAI/本地模型。

## 6. 棋谱格式、错误处理与测试

### 6.1 棋谱（Replay）

JSONL，一局一文件：

```jsonl
{"type": "meta", "engine_version": "...", "card_db_version": "...", "seed": 42, "players": [...], "models": {...}, "handbook_version": "abc123"}
{"type": "decision", "round": 3, "player": 0, "state_hash": "...", "legal_count": 17, "action": {...}, "reasoning": "...", "tokens": {"in": 2100, "out": 150}, "latency_ms": 3400}
{"type": "event", "detail": "战争结算: P0 胜, 掠夺..."}
{"type": "result", "scores": [132, 118], "winner": 0, "rounds": 19}
```

- `seed` + 引擎确定性 ⇒ 任意棋谱可精确重放验证；`state_hash` 链校验防引擎非确定性回归
- `tta replay <file>` 渲染人类可读记录；`--turn N` 跳转

### 6.2 错误处理

- **LLM 输出非法/超时**：指数退避重试（默认 3 次）；仍失败则降级为随机合法动作并记 `fallback` 标记；一局内 fallback 超阈值（默认 5%）该局作废不计入锦标赛
- **引擎内部错误**：不吞异常，崩溃即失败；棋谱已落盘至出错前一步，可精确复现
- **API 限流**：orchestrator 全局并发闸 + 每模型 RPM 配置

### 6.3 测试策略（四层）

1. **单元测试**：每张卡效果一条用例（`verified` 标记来源）；行动点/生产/腐败/战争等核心机制专项
2. **属性测试**：随机玩家 fuzzing——任意局数后不变量成立（资源非负、黄点守恒、卡牌总数守恒）
3. **黄金回归**：固定种子对局快照，引擎重构后逐状态比对
4. **规则对拍**：关键结算场景（战争/侵略/奇观）与官方规则书/FAQ 人工核对清单

### 6.4 目录结构

```
tta/
├── engine/  cards/  agents/  handbook/  orchestrator/  cli/  replay/
tests/
handbook/          # 策略手册 git 仓库(独立版本史)
replays/           # 棋谱输出
docs/superpowers/specs/
pyproject.toml     # Python 3.10+
```

## 7. 实施阶段路线图

| 阶段 | 内容 | 完成标志 |
|------|------|----------|
| P0 | 项目骨架、引擎核心（状态/动作/回合状态机/序列化）、随机玩家 | 随机玩家能跑通一局最小规则对局 ✅(2026-07-25 完成) |
| P1 | **官方规则核心重铸**（规则书+卡牌数值表已就绪，2026-07-25 经用户批准调整）:Token 资源模型（黄点人口轨道/蓝点供给区/卡上储存）、官方回合状态机、文明数值与效果框架、全部官方内政牌（初始科技 + A/I/II/III) | 官方规则对局可跑通，无 RULES-AUDIT 残留 |
| P2 | 军事系统：军事牌堆/政治阶段/事件/侵略/战争/条约/阵型/殖民 + pending 响应队列（数据源：卡牌数值表第 3-4 页） | 完整官方规则可玩 |
| P3 | CLI 完善 + 人类玩家界面 + 棋谱回放 | 人机能对战完整规则 |
| P4 | LLM 玩家 + 状态视图生成器 + 多模型配置 | LLM 互弈完整对局，成本可见 |
| P5 | 复盘/汇总智能体 + 手册 git 演化 + 锦标赛自动晋级 | 手册迭代闭环全自动运转 |

P0 用随机/基线玩家验证；P4 起 LLM 介入但手册冻结；**P5 是自弈迭代正式起点（牌库完成后）**。
