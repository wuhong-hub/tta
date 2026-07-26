# P2: 军事与政治系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 P1 官方内政引擎之上实现完整军事与政治系统：回合相位化、pending 响应队列泛化、军事牌堆与抽弃、阵型军力、政治阶段、事件筹划/揭示/结算、殖民竞拍、侵略与防御响应、战争、条约、时代 III 终局 Impact 计分。此后引擎具备 100% 官方规则（2-4 人）对局能力。

**Architecture:** 沿用不可变状态与单向依赖。`GameState` 增加 `phase` 与军事/事件牌堆字段；`PendingEffect` 泛化为带 `responder` 的响应队列项；`turn.py` 按相位驱动；新增 `military.py`（阵型军力）、`politics.py`（政治动作结算）、`events.py`（事件处理器注册表）。军事手牌对对手隐藏（视图过滤留 P4，测试玩家看全状态）。

**Tech Stack:** Python 3.12（语法底线 3.10)、uv、pytest、ruff；零运行时第三方依赖。

**数据来源：** 中文规则书 PDF（机制权威，p3-p9)、卡牌数值表 PDF 第 3-4 页（军事牌数据权威：奖励/侵略/战争/条约/阵型/事件/地区）、`docs/research/tta-official-data.md`、`docs/superpowers/progress.md`(P1 执行台账）。

## Global Constraints

- 沿用 P0/P1 全部约束：Python >=3.10、4 空格缩进、类型注解、frozen dataclass、嵌套 dict 修改前整体复制、`apply(state, action, db)` 返回新状态、非法抛 `IllegalActionError`、engine 不得 import agents/orchestrator/cli/cards
- **rng_state 消费规范（P2 新增）:** 一切洗牌（军事牌堆组建、时代切换切洗、未来事件牌堆重洗、殖民/事件内随机）必须经 `tta/engine/rng.py` 纯函数消费 `GameState.rng_state`；禁止任何其他随机源
- 测试命令：`uv run pytest <path> -v`;lint:`uv run ruff check tta tests`；每任务提交前全量绿
- 军事相关 P1 遗留 `P2-DEFERRED` 项随本阶段逐个落地（领袖/奇迹/特殊科技的军事互动）；落地不了的保留标注并记入完成判定的例外清单
- 隐藏信息：军事手牌/军事牌堆/未来事件牌堆对对手不可见——引擎层仅保证"打出/揭示前不进入公开信息查询接口"(P4 视图过滤）；本阶段测试玩家可看全状态
- 黄金回归指纹在末任务重建；计划变更处（本文件「执行期修正记录」）随执行回写

## 关键规则摘要（实现依据，规则书 p3-p9 + 卡牌数值表 p3-4)

- 回合流程：回合开始（补牌列 → 结算战争 → 公开专属阵型）→ 政治阶段（≤1 政治行动）→ 行动阶段 → 回合结束（弃多余军事牌 → 起义 → 生产 → 抓军事牌 → 恢复行动点）
- 政治行动（≤1):筹划事件 / 发动侵略 / 宣告战争（最后轮不可）/ 提出条约（2 人不可）/ 取缔条约 / 体面退出；时代 IV 不可用政治行动？——规则书 p4:IV 可以筹划事件？（时代 IV 不能抽军事牌，但政治阶段存在；体面退出 IV 禁止）。以规则书为准：IV 无军事牌堆，故不可筹划事件（无牌可塞？手牌中已有的事件牌可以）；战争最后轮不可宣告
- 军事牌：手牌上限 = 总军事行动点；回合结束弃多余（面朝下，玩家选择）；回合结束抓军事牌 = 剩余红点（≤3),IV 不抓
- 事件：筹划 = 塞到未来事件牌堆顶 + 揭示当前事件牌堆顶牌结算；当前堆尽时重洗未来堆（按时代分类，早时代在上）成为当前堆；时代 A 军事堆开局取 人数+2 张为当前事件堆
- 侵略：付红牌 → 目标防御（可出防御奖励牌多张/弃军事牌 +1 军力每张）→ 防御方军力 ≥ 攻击方则失败弃置，否则结算效果
- 战争：付红牌宣告（放自己游戏区），下个自己回合开始结算：纯军力比较（不可用奖励牌），胜者按牌结算，战争牌弃置
- 阵型：打出 1 红点（专属）/复制公共阵型 2 红点，每回合合计 ≤1；军队按阵型图标组成，阵型军力加成；旧式军队（低 2 时代以上）减半；空军特殊
- 殖民：地区牌揭示 → 从揭示者开始顺时针竞拍殖民军力（军事单位军力+殖民修正+奖励牌），胜者牺牲相等军力的军事单位（黄点回人口银行），获得殖民地（即时 + 永久效果）
- 终局：最后轮结束后，以任意顺序结算当前与未来事件牌堆中所有时代 III 事件牌（Impact 计分），再结算终局奖励，文化最高者胜
- 军力等级 = Σ 军事单位军力 + 阵型加成 + 领袖/奇迹/政府 bonus；下限 0

## 状态模型变更（Task 1 落地，后续任务依赖）

```python
class Phase(Enum):
    TURN_START = "turn_start"   # 引擎自动处理
    POLITICS = "politics"
    ACTION = "action"

@dataclass(frozen=True)
class PendingEffect:
    kind: str                              # "build_farm_mine" | ... | "aggression_defense" | "colonize_bid" | "discard_military" | "war_declaration_response"
    discount: int = 0
    responder: int | None = None           # 响应者座位; None = 当前玩家
    context: dict[str, str | int] = field(default_factory=dict)  # 卡片 id、攻击者、阶段等

# GameState 新增:
phase: Phase
military_deck: tuple[str, ...]
future_military_decks: dict[str, tuple[str, ...]]
military_discard: tuple[str, ...]
current_events: tuple[str, ...]
future_events: tuple[str, ...]
past_events: tuple[str, ...]

# PlayerState 新增:
tactics: str | None = None                 # 当前专属阵型
tactics_public: bool = False               # 已公开(可被复制)
tactics_this_turn: bool = False            # 本回合已打出/复制阵型(限1)
colonies: tuple[str, ...] = ()
declared_wars: tuple[str, ...] = ()        # 已宣告待结算的战争牌
pacts: tuple[str, ...] = ()                # 生效中的条约(卡 id, 3-4 人)
caesar_used: bool = False                  # Julius Caesar 双政治一次性
```

---

### Task 1: 相位化 + pending 泛化地基

**Files:**
- Modify: `tta/engine/state.py`、`tta/engine/actions.py`、`tta/engine/legal.py`、`tta/engine/apply.py`、`tta/engine/turn.py`
- Test: `tests/engine/test_phase_pending.py`

**Interfaces:**
- Produces:`Phase` 枚举；`GameState.phase`（序列化覆盖）;`PendingEffect.responder/context`（序列化兼容旧 pending 用例）；回合相位流转：`TURN_START(自动) → POLITICS → ACTION → (PassTurn) TURN_END 自动 → 下一位 TURN_START`
- legal 按相位分派：`POLITICS` 相位本任务只有 `SkipPolitics()`（政治动作后续任务加）;`ACTION` 相位 = 现有动作；`PassTurn` 仅在 ACTION 相位可用
- pending responder 非 None 且 ≠ current_player 时：`legal_actions` 生成的是 responder 的动作（引擎语义：响应期 current_player 逻辑切换——实现上 legal/apply 以 pending[0].responder 为准确定行动者，结算后恢复；本任务只建机制，用测试桩验证双人响应切换）
- apply 的 PassTurn 语义不变；SkipPolitics:phase POLITICS → ACTION

- [ ] **Step 1-5:** TDD（相位序列化、相位流转、responder 切换与恢复、旧 pending 用例回归）→ commit `feat(engine): 回合相位化与 pending 响应者泛化`

---

### Task 2: 军事卡牌模型 + 全部军事牌转录

**Files:**
- Modify: `tta/engine/enums.py`、`tta/engine/model.py`
- Create: `tta/cards/military.py`（全部军事牌：奖励/侵略/战争/条约/阵型/事件/地区，按时代）
- Test: `tests/cards/test_military_cards.py`

**Interfaces:**
- 新 CardCategory:`EVENT, AGGRESSION, WAR, PACT, TACTICS, BONUS, TERRITORY`(deck 均 MILITARY)
- CardDefinition 扩展字段：
  - `military_cost: int = 0` — 侵略/战争的军事行动费
  - `defense_bonus: int = 0`、`colonize_bonus: int = 0` — 军事奖励牌
  - `tactics_units: dict[str, int] = field(default_factory=dict)` — 阵型组成 {单位类别： 数量}（如 {"INFANTRY":2,"CAVALRY":1})
  - `tactics_strength: int = 0`、`tactics_strength_outdated: int = 0` — 阵型军力（旧式减半后值，卡牌数值表括号内数字）
  - `territory_immediate: dict[str, int] = field(default_factory=dict)`、`territory_permanent: dict[str, int] = field(default_factory=dict)` — 地区牌
  - 事件/侵略/战争/条约效果文本入 `text` + `handler` 注册名
  - `quantities` 三元组复用（军事牌堆按人数调整：2 人移除全部条约牌；其余以卡牌数值表数量列为准）
- 转录：卡牌数值表 PDF 第 3 页（bonus 3 种/侵略 11/战争 3/条约 10/阵型 18）与第 4 页（事件 A 10 + I 15 + II 15+6 地区 + III 15 Impact+6 地区）；事件 handler 名按卡 id；存疑不猜，记清单
- `tta/cards/__init__.py` 的 `build_card_db()` 合并军事牌；`deck_for(age, n, deck_type)` 支持 MILITARY

- [ ] **Step 1-5:** TDD（类别计数、张数复核 PDF、字段非空）→ commit `feat(cards): 军事卡牌模型与全部军事牌转录`

---

### Task 3: 军事牌堆 setup + 抽弃机制

**Files:**
- Modify: `tta/engine/setup.py`、`tta/engine/turn.py`、`tta/engine/legal.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_military_draw.py`

**Interfaces:**
- new_game：时代 A 军事堆洗匀取 `人数+2` 张为 current_events（其余入 removed 不回牌堆——规则："不要查看剩余的军事牌， 并将它们放回盒中");I/II/III 军事堆洗匀入 future_military_decks;military_deck 当前 = 时代 A 军事堆（抽取用）——注意：时代 A 军事堆 = 事件牌 10 张，取 人数+2 后剩余移除，时代 A 期间抓军事牌从哪抓？规则：当前时代军事牌堆 = 时代 A 军事堆的剩余？——官方设置：时代 A 军事牌堆切洗后抽 人数+2 张形成当前事件牌堆，其余放回盒中；即时代 A 没有军事牌可抓（玩家第一轮回合结束也抓不到牌，Age I 军事堆在时代 A 结束时代开启时才启用）。实现：military_deck = () 时代 A；时代 A 结束时启用时代 I 军事堆
- 回合结束抓军事牌：剩余红点（≤3）张从 military_deck 顶抓；牌堆空 → 无牌可抓（不重洗，规则：时代切换时旧军事弃牌堆重洗入新堆？——规则书 p7:"当你抓取军事牌堆最后一张军事牌时， 请切洗当前时代的军事弃牌堆， 并重新放到当前时代版图"——即军事弃牌堆重洗补充）;Age IV 不抓
- 回合结束弃多余军事牌：hand_military > civ.military_actions + military_hand_extra → pending kind="discard_military"(responder=当前玩家），逐张选择 DiscardMilitary(card_id) 直到合规；随机玩家随机选
- 时代切换（turn.py 时代结束序列）：启用新时代军事牌堆（切洗 = rng_shuffle）替换 military_deck

- [ ] **Step 1-5:** TDD（初始事件堆张数、抽取上限、弃牌 pending 流程、时代切换军事堆更替、IV 不抓）→ commit `feat(engine): 军事牌堆组建与回合末抓弃`

---

### Task 4: 阵型与军力系统

**Files:**
- Create: `tta/engine/military.py`
- Modify: `tta/engine/civ.py`、`tta/engine/legal.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_tactics.py`

**Interfaces:**
- 新动作：`PlayTactics(card_id)`(1 红点，手牌阵型牌 → 专属阵型）、`CopyTactics(card_id)`(2 红点，复制任一对手已公开阵型或公共阵型区？——规则：复制军事版图上的公共阵型牌，即其他玩家已公开的阵型）;`tactics_this_turn` 限 1
- 回合开始"公开专属阵型"(turn.py)：有专属阵型且未公开 → tactics_public=True（可被复制）；可选？——规则 p3:"如果你的游戏区域中有一张阵型牌， 你必须在此时将其公开"——强制公开
- `military.army_strength(db, p) -> int`：基础 = Σ 单位工人数 × 卡 strength；阵型加成：按 tactics_units 贪心组军（高时代单位优先填充？——引擎约定：按单位 strength 降序填充阵型槽位，每个完整组 +tactics_strength)；旧式军队：组内任一单位比阵型卡低 ≥2 时代 → 该组按 tactics_strength_outdated 计；空军（AIR)：只能单独成军？——按卡牌数值表空军卡星注：空军单位军力 5* 星注（规则书：空军组成军队时……以卡牌与规则书为准，存疑记清单）
- civ_values.strength 改为 army_strength 口径（含领袖/奇迹/政府静态加成，拿破仑每类型+2 在军事单位类型计数后加）

- [ ] **Step 1-5:** TDD（组军贪心、完整组加成、残缺组无加成、旧式减半、打出/复制限次、强制公开）→ commit `feat(engine): 阵型与军力系统`

---

### Task 5: 政治阶段框架 + 事件机制

**Files:**
- Create: `tta/engine/politics.py`、`tta/engine/events.py`
- Modify: `tta/engine/legal.py`、`tta/engine/apply.py`、`tta/engine/turn.py`
- Test: `tests/engine/test_politics_events.py`

**Interfaces:**
- 新动作：`SeedEvent(card_id)`、`PlayAggression(card_id, target)`、`DeclareWar(card_id, target)`、`ProposePact(card_id, target)`、`CancelPact(card_id)`、`Resign()`、`SkipPolitics()`（前三个本任务只建框架，T8/T9/T10 填充）
- POLITICS 相位 legal：可用的政治动作 + SkipPolitics；任一政治动作结算后 → ACTION 相位（Julius Caesar 一次性双政治：结算后回到 POLITICS 并置 caesar_used,T10 完整）
- SeedEvent 结算：军事手牌中的 EVENT 卡 → future_events 顶（暗置）；揭示 current_events 顶牌：TERRITORY → 触发殖民竞拍（T7)；其余 → events.py 的 EVENT_HANDLERS[handler](state, db) 结算 → past_events；若揭示的是当前堆最后一张：重洗 future_events（按时代分组，早时代在上，组内 rng_shuffle）成为新 current_events
- EVENT_HANDLERS 签名：`(state: GameState, db: CardDB) -> GameState`；声明式事件用通用 handler 工厂（全场增益/按条件增益/强弱比较扣减），特殊的逐卡注册

- [ ] **Step 1-5:** TDD（政治相位限 1 次、筹划+揭示流程、当前堆尽重洗、SkipPolitics)→ commit `feat(engine): 政治阶段框架与事件机制`

---

### Task 6: 时代 A + 时代 I 事件处理器

**Files:**
- Modify: `tta/engine/events.py`
- Test: `tests/engine/test_events_a_i.py`

**Interfaces:**
- Age A 10 事件（Development of X 系列，卡牌数值表 p4 文本）：全场增益/条件建造折扣/免费建造类，全部声明式或轻 handler
- Age I 15 事件：barbarians/border_conflict/crusades/cultural_influence/foray/good_harvest/immigration/new_deposits/pestilence/raiders/rats/rebellion/reign_of_terror/scientific_breakthrough/uncertain_borders
- 强弱比较类（weakest/strongest civ):2 人局"两个最"理解为"一个最"（规则书 p7)；平局按当前玩家顺时针优先级
- 影响生产的即时结算用 economy/civ 现有原语；需要玩家选择的（如 ravages 选奇迹）压 pending responder=对应玩家

- [ ] **Step 1-5:** TDD（每事件至少 1 用例，重点：强弱比较 2 人局口径、good_harvest 忽略消耗腐败、uncertain_borders 黄点转移）→ commit `feat(engine): 时代 A/I 事件处理器`

---

### Task 7: 殖民竞拍 + 地区牌

**Files:**
- Modify: `tta/engine/politics.py`、`tta/engine/events.py`、`tta/engine/legal.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_colonization.py`

**Interfaces:**
- 地区牌揭示 → 竞拍链：pending kind="colonize_bid",responder 从揭示者开始顺时针轮转；动作 `ColonizeBid(amount)`(>当前最高出价，上限 = 该玩家可承诺殖民军力 = Σ 可选牺牲单位军力（含阵型）+ 殖民修正 + 手中殖民奖励牌总值）或 `ColonizePass()`（退出）
- 仅剩 1 人 → 胜者结算：pending kind="colonize_sacrifice":胜者选择牺牲单位（动作 `ColonizeSacrifice(unit_card_ids: tuple)`，军力合计 ≥ 出价，黄点回 yellow_bank)，可出手中殖民奖励牌补足；然后获得殖民地：colonies 追加，即时效果结算（territory_immediate)，永久效果入 civ 合成（territory_permanent:黄点/蓝点/军力/文化增速等）
- 殖民地永久效果接入 civ.py（殖民修正、增速、行动点等键）
- 无人出价 → 地区牌入 past_events

- [ ] **Step 1-5:** TDD（轮转竞拍、胜者牺牲与黄点回银行、奖励牌补足、永久效果入 civ、流拍）→ commit `feat(engine): 殖民竞拍与地区牌`

---

### Task 8: 侵略与防御响应

**Files:**
- Modify: `tta/engine/politics.py`、`tta/engine/legal.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_aggression.py`

**Interfaces:**
- PlayAggression(card_id, target)（政治行动，付 military_cost 红点）：目标合法性（不可攻击有停战条约者；不可攻击军力 ≥ 自己的玩家——规则书 p4："你不能攻击军力等级大于或等于你的玩家")→ pending kind="aggression_defense", responder=target
- 防御方动作：`PlayDefenseBonus(card_id)`（防御奖励牌，多张）/ `DiscardForStrength(card_id)`（弃 1 军事牌 +1 军力，多张）/ `PassResponse()`;防御方军力（基础+奖励）≥ 攻击方 → 侵略失败弃置；否则结算侵略效果（AGGRESSION_HANDLERS：掠夺资源/科技/文化、摧毁建筑、殖民地被夺等，被夺资源从对方扣除加给自己，上限对方拥有量）
- 结算后 current_player 恢复攻击方，相位 → ACTION
- Gandhi 被动：对其侵略/战争双倍费用（落地 P1 遗留）；战争牌在场时不可对其侵略？

- [ ] **Step 1-5:** TDD（费用、目标限制、防御响应成功/失败、掠夺转移上限、Gandhi 双倍）→ commit `feat(engine): 侵略与防御响应`

---

### Task 9: 战争宣告与结算

**Files:**
- Modify: `tta/engine/politics.py`、`tta/engine/turn.py`、`tta/engine/legal.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_war.py`

**Interfaces:**
- DeclareWar(card_id, target)：付红点，战争牌入 declared_wars；最后轮不可宣告
- 回合开始结算（turn.py TURN_START，补牌后）：对 declared_wars 逐张：双方军力比较（纯 civ.strength，无奖励牌），平局无效果；胜者按战争牌效果结算（war over technology/territory/culture：夺取科技/领土/文化，数值按卡牌数值表 p3)；战争牌入弃牌堆
- 战争相关的临时军力加成（事件给的临时军力）在比较时计入——本阶段无此类事件则注释

- [ ] **Step 1-5:** TDD（宣告费用、次回合结算时机、三种战争效果、平局、最后轮禁止）→ commit `feat(engine): 战争宣告与结算`

---

### Task 10: 条约 + 体面退出 + Caesar 双政治

**Files:**
- Modify: `tta/engine/politics.py`、`tta/engine/civ.py`、`tta/engine/apply.py`
- Test: `tests/engine/test_pacts.py`

**Interfaces:**
- ProposePact(card_id, target)(3-4 人）：对方 pending 响应 accept/reject；接受 → 双方 pacts 追加，条约效果生效（按卡牌数值表 p3 条约效果：资源置换/互不攻击/科技共享等，handler 注册）；已有同类型条约须先移除（规则：游戏区域最多 1 张同类型？——按规则书 p9:"你的游戏区域中最多只能存在1张条约牌")
- CancelPact(card_id)：移除，效果终止
- Resign()：非 IV 可主动退出：文明移除（牌入 removed)，后续跳过其回合；仅剩 1 人 → 游戏立即结束其获胜；剩 2 人按 2 人规则继续（牌堆不再调整）
- Julius Caesar:caesar_used=False 时政治动作后可再执行一次（回 POLITICS 相位）

- [ ] **Step 1-5:** TDD（提议/接受/拒绝/取缔、同类型互斥、退出后轮换与终局、Caesar 一次性）→ commit `feat(engine): 条约、体面退出与双政治`

---

### Task 11: 时代 II 事件处理器

**Files:**
- Modify: `tta/engine/events.py`
- Test: `tests/engine/test_events_ii.py`

**Interfaces:** Age II 15 事件 + 6 地区（卡牌数值表 p4):civil_unrest/cold_war/crime_wave/economic_progress/emigration/iconoclasm/independence_declaration/international_agreement/national_pride/politics_of_strength/popularization_of_science/prosperity/ravages_of_time/refugees/terrorism；地区 6 张复用 T7 机制
- ravages_of_time（每位玩家将 1 个 A/I 奇迹翻面失效）:pending responder=各玩家选择

- [ ] **Step 1-5:** TDD → commit `feat(engine): 时代 II 事件处理器`

---

### Task 12: 时代 III 事件 + 终局 Impact 计分

**Files:**
- Modify: `tta/engine/events.py`、`tta/engine/turn.py`
- Test: `tests/engine/test_events_iii.py`

**Interfaces:**
- Age III 15 Impact 事件（按卡牌数值表 p4 计分公式：农业/建筑/平衡/殖民/竞争/政府/幸福/工业/人口/进步/科学/军事/科技/多样性/奇迹）+ 6 地区
- 终局（last_round 结束后，terminal 前）：以任意顺序（引擎约定：按揭示顺序）结算 current_events + future_events 中所有时代 III 事件 → 计入 culture；再结算终局奖励效果（chaplin 离场加分等）
- final_scores = 终局 culture

- [ ] **Step 1-5:** TDD（抽查 5 个 Impact 公式、终局结算顺序、chaplin 类离场效果）→ commit `feat(engine): 时代 III 事件与终局计分`

---

### Task 13: 属性测试扩展 + 黄金回归重建 + P1 遗留收尾

**Files:**
- Modify: `tests/property/test_invariants.py`、`tests/golden/test_golden_game.py`、`tests/cli/test_cli.py`
- Test: 全量回归

**收尾清单：**
- 属性测试新增不变量：军事手牌数 ≤ 上限（响应期除外）、事件堆守恒（current+future+past+removed ≡ 军事牌全集）、战争/条约状态合法性、序列化往返覆盖新字段
- shakespeare 配对文化、j_s_bach 每剧院 +1 文化（P1 终审交办的内政静态项）落地
- 黄金回归重建（新指纹）;CLI 4 人 3 局冒烟
- 检查 P2-DEFERRED 残留，列入最终例外清单（预期仅剩：shakespeare 配对折扣、bill_gates 实验室产资源、churchill 回合开始选择等需"每回合选择"机制的项——评估是否本阶段顺带实现：若 turn 开始选择机制可用 pending 轻量实现，则实现之）

- [ ] **Step 1-5:** 全量绿 + lint + 冒烟 → commit `test: P2 属性测试扩展与黄金回归重建`

---

## P2 完成判定

- [ ] 全测试绿 + lint 干净；CLI 2/3/4 人冒烟各 1 局产出 JSONL；同种子确定性一致
- [ ] 军事牌全部转录并经抽查（奖励/侵略/战争/条约/阵型/事件/地区）
- [ ] 响应队列覆盖：侵略防御、殖民竞拍、军事弃牌、事件选择
- [ ] 终局 Impact 计分可产生非零文化分的对局（至少 1 个脚本化场景测试）
- [ ] P2-DEFERRED 残留 ≤ 例外清单（清单入库）
- [ ] 黄金回归锁定；`grep -r "from tta.cards" tta/engine/` 为空

## 用户抽查清单（P2 验收）

1. 抽 3 张侵略 + 2 张战争 + 2 张条约 + 3 张阵型对照实体牌
2. 抽 5 张事件（含 1 张 Impact）对照实体牌
3. 殖民竞拍流程、战争结算时机、阵型旧式减半（规则书 p4/p7/p9)

## 后续阶段衔接

> **执行期修正记录（P2 终审确认，均已落地）:**
> 1. 时代结束过期处理含**军事手牌与条约**（本计划规则摘要遗漏，P1 计划原本有）
> 2. 军事弃牌决策先于回合推进，但仍在抓牌之后（次优口径，P3 可打磨为逐步等待）
> 3. 防御用牌上限 = **总军事行动点**（规则书 p4 明文，非剩余红点）
> 4. 公共阵型区：被替换阵型入 removed 而非军事弃牌堆（防回流）；公共区完整建模留 P3
> 5. 玩家退出后：时代 II/III 内政牌堆按新人数重组（军事堆不重组为 SIMPLIFICATION);**殖民竞拍/事件目标须过滤已退出玩家**
> 6. 黄点银行可 >18（殖民地配件盒标记）,tracks 查询钳制上界；守恒公式含配件盒补偿项
> 7. ColonizeSacrifice 精确子集与 runner 合法性闸口矛盾——**P3 开工第一件事**（人类界面不能接受全选锚点）
> 8. 计划层教训：规则摘要应从规则书重新转录，不要从上阶段计划继承（本计划"阵型 18 种"实为 15、时代结束序列漏军事手牌与条约）
>
> **P3/P4 readiness 备注：** agents 接口 `choose(state, legal, db)` 够用；隐藏信息字段集中（hand_military/military_deck/future_events/current_events),P4 单层过滤即可；遗留清单见 docs/deferred.md(22 项卡牌互动 + 5 项引擎简化）。

- P3:CLI 完善 + 人类玩家界面（终端棋盘渲染、动作菜单、悔棋）+ 棋谱回放增强
- P4:LLM 玩家（状态视图生成器 + 隐藏信息过滤 + 多模型配置）——注意军事手牌/未来事件的过滤在视图层实现
- P5：手册迭代闭环
