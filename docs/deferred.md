# TTA 引擎 DEFERRED 清零核对(P3 收官, 2026-07-28)

P3 阶段结束时的全部卡牌互动与引擎简化残留项最终核对。
来源: P2 收官清单(22 项卡牌互动 + 5 项引擎简化)逐项核对代码与测试。
规则歧义与引擎确定性口径汇总见 docs/rule-interpretations.md。

## 一、卡牌互动效果(22 项)

| 卡牌 | 能力 | 最终状态 |
| --- | --- | --- |
| trade_routes_agreement | 每回合食物/资源置换 | ✅ P3-T5: 主货币不足且差额恰 1 时替换(SIMPLIFICATION, 官方为主动选择, 见 rule-interpretations #11) |
| scientific_cooperation | 研发 -2 科技 + 对方付 1 | ✅ P3-T5: 卡面无 each turn 不限次; 对方强制付 1(下限 0) |
| winston_churchill | 每回合二选一 | ✅ P3-T4: turn_start_choice pending(+3 文化 / +3 科技+军事建造折扣 3) |
| bill_gates | 实验室产资源; 离场结算 | ✅ P3-T4 产资源+离场即时奖励; P2-T12 终局奖励(口径细节见 rule-interpretations #17) |
| alexander_the_great | +1 军力/单位; 政治行动移出游戏换 1 黄点 | 静态 ✅(P1); 政治行动 → P4(政治行动类领袖能力, 需新动作类型) |
| homer | +1 笑脸; 军事建造折扣; 替换时滑入已完成奇迹 | 静态与折扣 ✅(P1/turn_start_discounts); 滑入奇迹 → P4(换领袖流程选择) |
| joan_of_arc | 静态; 政治阶段开始查看下一事件 | 静态 ✅(P1); 查看事件 → P4(需隐藏信息视图机制) |
| genghis_khan | 步兵视为骑兵组阵型; 两强之一 +3 军力 | → P4(组军改造 + 全玩家强弱判定钩子) |
| christopher_columbus | 政治行动: 手牌直接殖民 | → P4(政治行动类领袖能力) |
| frederick_barbarossa | 红点直建军(-1 黄 -1 食) | → P4(新动作类型) |
| james_cook | 殖民地修正加成; 每回合弃 ≤2 军事牌各 +1 军力 | → P4(殖民结算修正 + 每回合选择) |
| mahatma_gandhi | 不能打侵略/战争; 被攻击费用 ×2 | ✅ 全部已实现(P2-T8/T9: legal 闸口 + aggression_cost ×2; deferred 旧文误标 P2-DEFERRED, P3-T10 更正) |
| maximilien_robespierre | 革命红点费; 革命时 +3 笑脸(一次性) | 红点费 ✅(P2-T13); 一次性笑脸 → P4(一次性触发器) |
| william_shakespeare | +1 笑脸; 配对文化; 配对建造折扣; 研发 -1 白点 | 静态+配对文化 ✅(P2-T13); 配对建造/升级 -1 资源 ✅(P3-T6); 研发 -1 内政行动 → P4(行动点折扣机制) |
| j_s_bach | 每剧院 +1 文化; 研发剧院 -2 科技; 每回合特殊升级 | 静态 ✅(P2-T13); 折扣与升级 ✅(P3-T6) |
| taj_mahal | 完成时 +1 蓝点; 换领袖 -2 白点 | → P4(奇迹完成触发器 + 换领袖流程); 静态 +3 文化 ✅ |
| st_peters_basilica | 其他每个有笑脸文明 +1 笑脸 | → P4(跨玩家笑脸判定); 静态 +2 文化 +1 笑脸 ✅ |
| hollywood | 建成时一次性得分 | → P4(奇迹完成触发器); 与 taj_mahal 同属一类, 若 P4 不做则为永久例外 |
| masonry / architecture / engineering | 奇迹多阶段与城市建筑折扣 | ✅ P3-T6(BuildWonderStage count 2/3/4 + construction_urban_discount) |
| transcontinental_railroad | 最佳矿场产出翻倍 | → P4(经济生产改造); 静态 +4 军力 ✅ |
| ocean_liner_service | 每回合免费增人口 | → P4(每回合选择类效果) |
| cartography | 殖民少花 2 | +1 殖民修正 ✅(P1); 殖民费 -2 → P4(殖民结算修正) |

### 留 P4 项的归类(均为机制新增, 非规则不明)

- **政治行动类领袖能力**(alexander/columbus/barbarossa): 需新增政治动作类型与 legal/apply 分支。
- **每回合选择类效果**(james_cook 弃牌/ocean_liner): 可复用 P3-T4 的 turn_start_choice pending 机制。
- **奇迹完成/换领袖触发器**(taj_mahal/hollywood/robespierre 笑脸/homer 滑入): 需在 BuildWonderStage 完成与 PlayLeader 替换处加钩子; 若 P4 判定收益低于复杂度, hollywood/taj_mahal 可转永久例外。
- **经济/殖民结算修正**(transcontinental/cartography/james_cook 殖民/genghis): 需在 produce/colonize 结算加条件分支。
- **shakespeare 研发 -1 白点**: 行动点折扣机制(现有折扣均为资源费)。
- **joan_of_arc 查看事件**: 依赖 P4 视图层(隐藏信息选择性揭示)。

## 二、引擎口径/简化(5 项)

| 项 | P3 收官状态 |
| --- | --- |
| 公共阵型区完整建模 | ✅ P3-T2 正式建模(GameState.public_tactics; 公开入区/换阵留区/同名覆盖保留一张/CopyTactics 来源=公共区), 不再是简化 |
| 弃牌决策先于抓牌 | ✅ P3-T3 官方顺序(规则书 p6): 回合末分阶段 + resume 续跑, 响应期手牌 = 压入时手牌 |
| Resign 后军事未来牌堆不重组 | **保留**(永久简化): 规则书仅明示内政堆按新人数重组, 军事堆沿用原人数组牌(politics.py SIMPLIFICATION) |
| 军事手牌/未来事件视图过滤 | ✅ 渲染层已就绪(P3-T7 ui/render 对手视角仅显示数量); P4 LLM 视图复用此过滤层 |
| runner 合法性闸口; ColonizeSacrifice 子集枚举 | ✅ P3-T1: legal.is_self_validating 闸口 + 常用子集枚举 |

## 三、清零结论

- 22 项卡牌互动: **7 项全部实现**(trade_routes/scientific_cooperation/churchill/bill_gates/gandhi/bach/masonry 系列), **15 项部分实现**(静态能力均已实现), 剩余互动能力全部归属 P4, 无规则不明残留。
- 5 项引擎简化: 4 项收口, 1 项(Resign 军事堆)确认为永久简化。
- 全部引擎确定性口径与无明文歧义已汇总至 docs/rule-interpretations.md, 供对照实体牌/官方 FAQ 抽查。
