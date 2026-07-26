# TTA 引擎 DEFERRED 残留清单(P2 收官, 2026-07-26)

P2 阶段结束时的全部 `P2-DEFERRED` / `P3-DEFERRED` 残留项及建议归属阶段。
来源: `grep -rn "P2-DEFERRED\|P3-DEFERRED" tta/` 汇总(T13 入库)。

## 一、卡牌互动效果(多数需"每回合选择"/政治行动/折扣机制, 建议 P3)

| 卡牌 | 残留能力 | 现状 | 建议归属 |
| --- | --- | --- | --- |
| trade_routes_agreement | 每回合食物/资源置换 | P3-DEFERRED(可缔约无效果) | P3(每回合选择) |
| scientific_cooperation | 每回合研发折扣 | P3-DEFERRED(可缔约无效果) | P3(每回合选择) |
| winston_churchill | 每回合二选一(+3 科技 或 3 白 3 红) | P2-DEFERRED | P3(回合开始选择 pending; T13 评估: 机制新增风险大, 不在 P2 收官顺带实现) |
| bill_gates | 实验室每回合按矿山产资源; 中场离场结算 | P2-DEFERRED(终局奖励已实现, events._bill_gates_endgame) | P3(经济生产改造) |
| alexander_the_great | 政治行动: 移出游戏换 1 黄点 | P2-DEFERRED(静态 +1/单位已实现) | P3(政治行动类领袖能力) |
| homer | 被替换时滑入已完成奇迹(多 1 笑脸) | P2-DEFERRED(静态 +1 笑脸/军事建造折扣已实现) | P3(换领袖流程选择) |
| joan_of_arc | 政治阶段开始查看下一事件 | P2-DEFERRED(静态已实现) | P3(需视图/选择机制) |
| genghis_khan | 步兵视为骑兵组阵型; 两强之一 +3 军力 | P2-DEFERRED | P3 |
| christopher_columbus | 政治行动: 手牌直接殖民 | P2-DEFERRED | P3 |
| frederick_barbarossa | 红点直建军(-1 黄 -1 食) | P2-DEFERRED | P3 |
| james_cook | 殖民地修正加成; 每回合弃 ≤2 军事牌各 +1 军力 | P2-DEFERRED | P3 |
| mahatma_gandhi | 不能打侵略/战争; 被攻击费用 ×2 | P2-DEFERRED(静态 +2 文化已实现) | P3(legal 闸口) |
| maximilien_robespierre | 革命时 +3 笑脸(一次性) | P2-DEFERRED(革命红点费已实现) | P3(一次性触发) |
| william_shakespeare | 图书馆/剧院各 -1 白 -1 资源折扣 | P2-DEFERRED(静态 +1 笑脸 + 配对文化 T13 已实现) | P3(折扣机制) |
| j_s_bach | 剧院 -2 白折扣; 每回合升级任一城市建筑为剧院 | P2-DEFERRED(静态每剧院 +1 文化 T13 已实现) | P3(折扣 + 每回合选择) |
| taj_mahal | 完成时 +1 蓝点; 换领袖 -2 白点 | P2-DEFERRED | P3(奇迹完成触发器) |
| st_peters_basilica | 其他每个有笑脸文明 +1 笑脸 | P2-DEFERRED | P3 |
| hollywood | 建成时一次性得分 | P2-DEFERRED | P3(奇迹完成触发器) |
| masonry / architecture / engineering | 奇迹建造折扣与多阶段(双/三/四阶段) | P2-DEFERRED | P3(建造折扣机制) |
| transcontinental_railroad | 最佳矿场产出翻倍 | P2-DEFERRED | P3(经济生产改造) |
| ocean_liner_service | 每回合免费增人口 | P2-DEFERRED | P3 |
| cartography | 殖民少花 2(+1 殖民修正已实现) | P2-DEFERRED | P3(殖民结算修正) |

## 二、引擎口径/简化(本任务确认, 多数可长期保留)

| 项 | 说明 | 建议归属 |
| --- | --- | --- |
| 公共阵型区完整建模 | T13: 被替换实体阵型卡一律入 removed(官方: 公开的留公共阵型区可被复制, 重复的移除); 复制他人阵型经 CopyTactics 引用在场卡, 不受影响 | 保持简化; 如需完整公共区 → P3/P4 |
| 弃牌决策先于抓牌 | turn.py 次优口径: discard_military pending 在"弃多余军事牌"步骤压入, 但响应发生在整个回合末流程(含抓牌)之后 | P3(若做逐步等待) |
| Resign 后军事未来牌堆不重组 | T13 SIMPLIFICATION: 规则书仅明示内政堆按新人数重组, 军事堆沿用原人数组牌 | 保持 |
| 军事手牌/未来事件视图过滤 | 隐藏信息过滤在视图层实现 | P4(LLM 玩家) |
| runner 合法性闸口; ColonizeSacrifice 子集枚举 | legal 仅给"全选"锚点, apply 前独立校验; runner 不做合法性闸口 | P4 |
