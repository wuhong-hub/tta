# TTA 引擎规则歧义与确定性口径汇总(P3 收官, 2026-07-28)

引擎对官方规则无明文处/玩家自选处采用的确定性口径全集, 供对照实体牌与
官方 FAQ 抽查。每项: 规则出处、引擎口径、替代解释、修改位置。
来源: 代码 SIMPLIFICATION/RULES-CHECK 注释与 docs/superpowers/progress.md
各阶段审查记录。若抽查发现口径与官方 FAQ 冲突, 按"修改位置"列定位改动。

## A. 支付与经济

### 1. 确定性支付与找零
- 出处: 规则书支付节(玩家自选从哪些卡取蓝点、找零落在哪)。
- 引擎口径: 反复从 token_value 最小(并列 card_id 字典序最小)的卡取 1 蓝点回供给区, 直至累计价值 ≥ 应付额; 超付找零从供给区向该类型最低等级卡(同序)放回, 单点价值超过剩余找零额时停止, 找不零的部分损失。
- 替代解释: 玩家自选取点/找零落点(官方)。
- 位置: tta/engine/economy.py(模块 docstring + pay)。

### 2. 生产供给不足时的分配序
- 出处: 规则书生产阶段(供给区蓝点不足时官方未明确顺序)。
- 引擎口径: 高等级(token_value 降序, 并列 card_id 字典序升序)卡优先得点。
- 位置: tta/engine/economy.py(produce)。

### 3. 奇迹建造仅从供给区盖蓝点
- 出处: 规则书奇迹建造(官方允许动用卡上蓝点盖阶段)。
- 引擎口径: 每阶段 1 蓝点须来自 blue_bank(legal 要求 blue_bank >= count)。
- 替代解释: 可动用农场/矿场卡上蓝点。
- 位置: tta/engine/apply.py(_build_wonder_stage)、legal.py(_wonder_actions)。

### 4. 摧毁农场/矿场时卡上蓝点保留
- 出处: 规则书摧毁节(卡上标记去向无明文)。
- 引擎口径: card_tokens 保留在卡 id 上(该卡已不在场上)。
- 位置: tta/engine/apply.py(_destroy_disband 附近, SIMPLIFICATION 注释)。

### 5. 殖民地永久黄/蓝标记的配件盒口径
- 出处: 规则书殖民节(永久标记来自配件盒, 非 25/16 池)。
- 引擎口径: 获得时自配件盒入银行(负值下限 0 截断), 失去(annex/独立宣言)时按持有方银行下限 0 归还。
- 位置: tta/engine/politics.py(_grant_colony/_annex_settle)、events.py(KIND_EVENT_LOSE_COLONY); 守恒补偿见 tests/property/test_invariants.py _colony_token_deltas。

## B. 军事与政治

### 6. 贪心组军
- 出处: 规则书阵型节("总是以获得最大加成的方式组军")。
- 引擎口径: 各类别单位按 strength 降序(并列 card_id 字典序)贪心填充阵型组; 引擎约定贪心即官方"最大加成"口径。
- 替代解释: 存在贪心非最优的构造性反例(理论), 官方意图为自动最优。
- 位置: tta/engine/military.py(模块 docstring + _greedy 填充)。

### 7. 防御上限按总军事行动点
- 出处: 规则书 p4("打出与弃置的牌总数不能超过防御方总军事行动点数")。
- 引擎口径: 上限 = civ 总军事行动点(非剩余红点池), P2 终审修正。
- 替代解释: 按当前剩余红点(P2-T8 曾用, 已废)。
- 位置: tta/engine/legal.py(_aggression_defense_actions)、actions.py(PlayDefenseBonus docstring)。

### 8. raid 战利品按总造价取半
- 出处: 卡牌数值表 p3 raid(受害者依次失去城市建筑, 攻击者得资源)。
- 引擎口径: loot = 已毁建筑卡面造价累计, 链尽攻击方 +ceil(loot/2) 资源(总造价取半向上取整)。
- 替代解释: 逐建筑分别取半再求和(P2-T8 歧义待裁项, 无明文)。
- 位置: tta/engine/politics.py(_raid_destroy/_raid_advance)。

### 9. 领土之战军力差除法取整
- 出处: 卡牌数值表 war_over_territory(败者失去 1 + 军力差÷5 黄点)。
- 引擎口径: 向下取整(1 + floor(diff/5))。
- 替代解释: 向上取整/四舍五入(P2-T9 披露无明文)。
- 位置: tta/engine/politics.py(WAR_TERRITORY_DIVISOR/_war_over_territory)。

### 10. 公共阵型区同名牌覆盖
- 出处: 规则书 p3(同名牌"可覆盖或从游戏中移除")。
- 引擎口径: 固定"公共区保留一张, 重复实体卡入 removed"(同 id 下两种选择状态等价)。
- 位置: tta/engine/turn.py(_reveal_tactics)。

### 11. trade_routes 强制替换口径
- 出处: 卡牌数值表 p3(每回合一次可用 1 食物抵 1 资源, 官方为玩家主动选择是否替换)。
- 引擎口径: 确定性——仅当主货币不足且差额恰为 1 时启用替换, 主货币足够时不替换。
- 替代解释: 玩家主动选择(P4 可改显式选择)。
- 位置: tta/engine/effects.py(pay_with_trade_routes/trade_routes_substitute_kind)。

### 12. 时代 IV 政治动作不受限
- 出处: 规则书 p4(仅明示时代 IV 不可退出游戏)。
- 引擎口径(RULES-CHECK): 时代 IV 无军事牌可抽, 但手牌已有的事件牌仍可筹划、侵略/战争牌仍可打出、条约动作同理。
- 位置: tta/engine/politics.py(politics_actions)。

### 13. Resign 后军事未来牌堆不重组
- 出处: 规则书退出节(仅明示内政牌堆按新人数重组)。
- 引擎口径: 军事牌堆沿用原人数组牌, 不重组(永久简化)。
- 位置: tta/engine/politics.py(resign, SIMPLIFICATION 注释)。

### 14. 失去人口的确定性选取
- 出处: 卡牌数值表 barbarians/pestilence/reign_of_terror(失去人口, 官方为玩家自选)。
- 引擎口径: 优先空闲工人池, 不足时按 (类别, card_id) 字典序从有工人的卡上移除; 黄点回银行。
- 位置: tta/engine/events.py(时代 I 事件模块 docstring + 失去人口实现)。

## C. 事件结算

### 15. 事件失去蓝点/弃牌的确定性选取
- 出处: civil_unrest(-1 蓝点)、reign_of_terror 类弃牌等(官方为玩家自选)。
- 引擎口径: -1 蓝点取储存中 (token_value, card_id) 升序第 1 个回供给区; 弃军事牌按 card_id 字典序。
- 位置: tta/engine/events.py(civil_unrest、时代 III 事件弃牌)。

### 16. politics_of_strength 终局分值
- 出处: 卡牌数值表 politics_of_strength(终局结算的分值 PDF 未给)。
- 引擎口径: "最终时代"按 state.age ∈ {III, IV} 判定; 终局 ±文化按同数值直译(最强 +5 / 最弱 -3, 下限 0)。
- 替代解释: 官方 FAQ 若有分值以其为准(P2-T11 披露无明文)。
- 位置: tta/engine/events.py(_politics_of_strength 及常量)。

### 17. bill_gates 实验室资源口径
- 出处: 规则书附录比尔·盖茨(实验室按矿山方式产资源)。
- 引擎口径: 实验室卡上每个蓝色标记代表与卡牌等级相同数量的资源(token_value = 时代等级 A=1/I=2/II=3/III=4); 离场/终局奖励 = Σ 每个实验室工人 × 该卡时代等级; 实验室产资源不计 impact_of_industry(规则书附录 p12 只计矿场)。
- 位置: tta/engine/economy.py(模块 docstring LAB 口径)、effects.py(gates_lab_bonus_culture)、events.py(_bill_gates_endgame)。

### 18. 文化失去下限 0
- 出处: 各失去文化效果(食物短缺/spy/armed_intervention/战争等)。
- 引擎口径: 文化不可为负, 失去按下限 0 截断; 攻击方只获得受害者实失量。
- 位置: tta/engine/turn.py(食物短缺)、events.py、politics.py(spy/armed_intervention/战争结算)。

### 19. economic_progress 生产次序
- 出处: 卡面 "do not ignore consumption & corruption"。
- 引擎口径: 按回合生产阶段次序(腐败 -> 食物生产 -> 消耗 -> 资源生产), 不含计分与起义检定。
- 位置: tta/engine/events.py(economic_progress)。

### 20. international_agreement 结算细节
- 出处: 卡牌数值表(拿牌预算 5, 跳过下一次政治行动)。
- 引擎口径: 拿牌白点费自付(从现有白点扣); 结束后补满卡牌列但不触发时代结束处理(SIMPLIFICATION)。
- 位置: tta/engine/events.py(_international_agreement)。

### 21. 瘟疫类"失去一半人口"取整
- 出处: 卡牌数值表(失去一半人口)。
- 引擎口径: 向上取整, 移回黄点银行。
- 位置: tta/engine/events.py(plague 类处理器)。

## D. 卡牌效果口径

### 22. 卡牌"等级"定义
- 出处: 卡牌数值表(多项效果按"等级"计)。
- 引擎口径: 级 = 时代序; effects._TECH_LEVEL 口径 Age A 计 1 级(leonardo/newton/einstein/sid_meier/first_space_flight); masonry 系列城市建筑折扣的 _CONSTRUCTION_LEVEL 口径 Age A 计 0 级(A 代城市建筑不享折扣)。
- 位置: tta/engine/effects.py(_TECH_LEVEL/_CONSTRUCTION_LEVEL)。

### 23. "最佳实验室/图书馆"按已研发卡计
- 出处: leonardo/newton/einstein/sid_meier 卡文本。
- 引擎口径(SIMPLIFICATION): 按 developed 已研发卡计, 不要求卡上有工人; sid_meier 每个实验室 -1 科技同口径。
- 替代解释: 仅计有工人的卡(P1 Task 12 待裁定, 现行为简化)。
- 位置: tta/engine/effects.py(_leonardo_bonus/_sid_meier_bonus 等)。

### 24. newton 白点返还范围
- 出处: 卡文本"每当你研发一项科技, 拿回 1 内政行动"。
- 引擎口径(SIMPLIFICATION): 研发兵种科技所花红点也以白点形式拿回; breakthrough pending 0 行动点研发同样触发; 变更政体不触发。
- 位置: tta/engine/effects.py(on_develop_tech_gains)。

### 25. first_space_flight 政体计入
- 出处: 官方规则(政体算科技)。
- 引擎口径: 当前政体按其时代等级计入(与 _TECH_LEVEL 同口径)。
- 位置: tta/engine/effects.py(_first_space_flight_bonus)。

### 26. shakespeare 配对口径
- 出处: 卡文本(每对图书馆与剧院 +2 文化; 配对折扣)。
- 引擎口径(SIMPLIFICATION): 图书馆按已研发卡计, 剧院按有工人的卡计; 配对建造折扣 -1 资源双向对称(有图书馆则剧院折, 反之亦然)。
- 位置: tta/engine/effects.py(_shakespeare_bonus/shakespeare_build_discount)。

### 27. bach 每回合特殊升级
- 出处: 卡文本(每回合一次, 1 内政行动把任一城市建筑升级为同级或高一级剧院)。
- 引擎口径: 以 Upgrade 特例枚举(apply 按 is_bach_upgrade 识别并记次); 目标剧院卡 0 工人(新增建筑)时受城市建筑上限约束。
- 位置: tta/engine/legal.py(_bach_upgrade_actions)、apply.py。

### 28. Churchill "3 资源军事用"平铺为建造折扣
- 出处: 卡文本(每回合二选一: +3 文化, 或 +3 科技 + 3 资源用于军事)。
- 引擎口径: "3 资源军事用本回合"实现为 turn_discounts["unit_build"] += 3(军事建造/升级费用折扣, 与 homer/patriotism 同键叠加, 回合末清空), 非 3 枚资源标记。
- 替代解释: 发放 3 枚只能用于军事的资源标记(需带用途标记的蓝点, 复杂度高)。
- 位置: tta/engine/choices.py(CHURCHILL_MILITARY_RESOURCE)。

### 29. scientific_cooperation 不限次与对方付费下限
- 出处: 卡牌数值表 p3(卡面无 each turn 字样, 对照 trade_routes 的 each turn)。
- 引擎口径: 研发 -2 科技不限次; 对方强制付 1 科技, 不足时扣到 0; 政府变更不适用。
- 位置: tta/engine/effects.py(scientific_cooperation_discount)、apply.py(_develop_tech)。

### 30. hammurabi 红点垫付
- 出处: 卡文本(每回合一次, 1 红点当 1 白点)。
- 引擎口径: flexible_actions 实现, 每回合限 1 次(turn_discounts 记次, P1 终审修正限次)。
- 位置: tta/engine/effects.py(flexible_actions/HAMMURABI_FLEX_KEY)。

### 31. caesar 军事卡当内政(时代 A 行动卡口径)
- 出处: 卡牌数值表(时代 A 行动卡 "可作为内政行动使用"类文本)。
- 引擎口径(SIMPLIFICATION 注释于卡文本): 按卡面直译。
- 位置: tta/cards/age_a.py。

## E. 时序与相位

### 32. 军事手牌上限仅回合末执行
- 出处: 规则书 p6(回合结束阶段弃置多余军事牌)。
- 引擎口径: 上限仅在回合末弃牌点强制执行; 抓牌/竞拍/politics_of_strength 使手牌再度超限时不追溯, 下次检查在该玩家下个回合末(官方口径)。
- 位置: tta/engine/turn.py(end_of_turn)、tests/property/test_invariants.py 第 7 条。

### 33. 行动卡效果可放弃
- 出处: 规则书(官方行动卡效果为强制)。
- 引擎口径(SIMPLIFICATION): 引擎允许 PassTurn 放弃行动卡 pending(仅丢弃, 随后正常推进回合)。
- 位置: tta/engine/apply.py(apply 的 PassTurn 分支)。

### 34. 时代 A 结束无黄点损失
- 出处: 规则书(时代 A 结束 "nothing else happens")。
- 引擎口径: 时代 I/II/III 结束各 -2 黄点(下限 0), 时代 A 结束不扣(P1 终审修正, 有明文)。
- 位置: tta/engine/turn.py(_age_end_cleanup/AGE_END_YELLOW_LOSS)。

### 35. 腐败/食物不足损失到此为止
- 出处: 规则书生产阶段(不足时的处理)。
- 引擎口径: 腐败资源不足用食物补, 仍不足损失到此为止; 食物消耗每缺 1 -4 文化(下限 0)。
- 位置: tta/engine/turn.py(_production)、economy.settle_loss。
