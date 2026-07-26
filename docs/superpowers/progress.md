# P0 执行进度台账
Task 1: complete (commits f66d978..826f621, review clean; Minor: 报告包数量措辞瑕疵、main.py 空行风格——无需处理)
Task 2: complete (commits 826f621..63b3099, review clean; Minor: CardDefinition 含 dict 字段实际不可 hash、Age.next() 临时 list——记录备查)
Task 3: complete (commits 63b3099..b0062ad, review clean; Minor: 取模偏差理论存在已在 docstring 声明、空洗牌不推进状态——记录备查)
Task 4: complete (commits b0062ad..02be6bb, review clean; Minor: final_scores 空元组边界、sorted 冗余、浅冻结既定设计——记录备查)
Task 5: complete (commits 02be6bb..dfd1068, review clean; Minor: 政体缺失时 KeyError/ValueError 不一致、action_from_dict 裸 KeyError——后续补强;实现者修正了 brief 测试夹具两处 bug: 补 iron 卡与 government 字段)
Task 6: complete (commits dfd1068..c8d3ca0, review clean; Minor: _play_action_card 仅结算四项 gains 键、list(Age) 重复构建——Task 8 配牌时留意 strength/happiness 键)
Task 7: complete (commits c8d3ca0..439c507, review clean; _refill_row 以测试为准修正级联语义,reviewer 独立推演确认正确;Minor: 起义免消耗待 P2 规则核对;⚠️ happiness/strength 导出行列在 Task 8 统一处理已确认覆盖)
Task 8: complete (commits 439c507..d0abad6, review clean; Task 7 ⚠️ happiness/strength 导出已闭环;Minor: new_game ValueError 分支无测试——后续补)
Task 9: complete (commits d0abad6..ab5786b, review clean; Minor: recorder._path 死字段、if recorder 风格、Any 注解权衡——记录备查)
Task 10: complete (commits ab5786b..09f223a, review clean; 验收清单五项经 reviewer 独立复验通过;Minor: 函数内 import、capsys 注解豁免、replay 文件损坏时报错不友好——记录备查)
全部 10 任务完成,进入全分支终审
Final review: Ready for next phase;2 项必修已修 (commit 8bd9b6a),计划文档已回写执行期修正

# P1 官方规则核心重铸(plan: 2026-07-25-p1-official-core.md)
Task 1: complete (commits f2d12cd..f26a55b, review clean; brief 的 corruption_value 参考实现有误,实现者改为分档版,reviewer 全值域推演确认正确;Minor: BLUE_SPACES 死常量)
Task 2: complete (commits f26a55b..7ed189a, review clean; Minor: deck_for 未按 DeckType 过滤——T9/T13 明确语义;agents/orchestrator 源码 import 即坏——T13/14 优先重建;replay 实际可 import)
Task 3: complete (commits 7ed189a..8f5629e, review clean)
Task 4: complete (commits 8f5629e..ef07337, review clean; "该类型卡"并集定义待后续集成确认;brief 内联用例矛盾已按正式算法处理)
Task 5: complete (commits ef07337..6e1ce0f, review clean; T9 建议: 真实 handler 端到端集成用例 + urban_produces/wonder_bonus 键名校验;T14 收口 engine/__init__ 导出)
Task 6: complete (commits 6e1ce0f..b476c9b + fix 2e8f06e, review found 2 deviations: apply 签名与 round==1 PassTurn,均已修复验证;T9 注意: 同名政体变更未禁,可收紧)
Task 7: complete (commits 2e8f06e..24a8eb5, review clean; T8 注意: PassTurn 丢弃 pending 后须落入推进逻辑不能提前 return;T9 注意: breakthrough develop_tech 须在 _pending_actions 加分支、handler 与 PENDING_SPECS 成对注册)
Task 8: complete (commits 24a8eb5..e13f85b + fix f0de03f; reviewer 发现 2 处规则保真问题,经官方规则核实:A 结束不扣黄点、IV 继续弃牌不补牌,均已修复;计划文档需回写这两点)
Task 9: complete (commits f0de03f..1f3f990 + fix 8272f58; review 发现 hammurabi 折扣 Major bug 已修;计划缺陷 IncreasePopulation 动作已补;Library of Alexandria 产出已补;hammurabi 红点垫付仍为 SIMPLIFICATION 待规则核对)
Task 10: complete (commits 8e94c08..52fd620, review clean 转录零错误 44/50/53 与官方移除规则吻合;T11 顺带清理 test_actions_legal.py:465 的 2 参数桩)
Task 10-11: complete (52fd620, 547e004, reviews clean;shakespeare +1笑脸静态未实现记 Minor 随 P2 补;newton 白点返还口径 SIMPLIFICATION 待 P2 裁定)
Task 12: complete (a84907b + fix f0115ee;reviewer 五项勘正全部成立,仅 Churchill 卡文本一处错误已修;P2 待办: sid_meier 按工人计口径、first_space_flight 计当前政体)
Task 13: complete (commits f0115ee..d05bfca, review clean;随机玩家得分恒 0 为策略病理非引擎 bug,replay 数据佐证;建议后续用启发式基线玩家)
Task 14: complete (f5ad597 + 蓝点闭环修复 fa73959, review clean + reviewer 300 种子压力测试 0 违规)
全部 14 任务完成,进入 P1 全分支终审
P1 终审: 6 项规则修正 (commit 6c860e5): 时代III结束序列/领袖首打费用/特殊科技替换/政体查重/hammurabi垫付限次/首航计政体;389 测试全绿
P1 完成

# P2 军事与政治系统(plan: 2026-07-26-p2-military-politics.md)
Task 1: complete (commits db7e9a9..96357b9, review clean;Medium 交接: 响应期零合法动作会卡死,T5 必须加 DeclineResponse 兜底并作为验收标准)
Task 2: complete (commits 96357b9..cf8d5b4, review clean 转录零错误;军事牌堆 A=10, I=43/45/45, II=46/50/50, III=41/45/45;存疑 4 项记 T6/T11 核对)
Task 3: complete (07e52da + fix dd1db84;reviewer 发现弃牌时序与军事弃牌堆跨时代两项中等问题已修;残留次优口径: 弃牌决策在抓牌后(官方在前),记 P3 打磨)
Task 4: complete (commits dd1db84..752adb9, review clean;空军翻倍规则经规则书 p9 核验成立;T13 待办: 公共阵型区建模——被替换阵型不应入 military_discard 可回流,应留公共区或 removed)
Task 5: complete (5e8d618 + fix 96e6cdf;审查发现 civilization 事件缺人口选项已补,抓军事牌去重;TODO 标记: I/II/III 事件过场兜底待 T6/T11/T12 注册后删除)
Task 6: complete (commits 96e6cdf..9f949aa, review clean;brief 三处事件语义错误以 PDF 为准修正(barbarians/pestilence/reign_of_terror=人口);顺手项: state.py:184 不可达 return 待清理)
Task 7: complete (6a33095 + fix d4a6d23;审查发现黄点银行越界崩溃已修(钳制 18);P4 交接: runner 合法性闸口会拦 ColonizeSacrifice 精确子集,P4 需同步改造;竞拍出价枚举长列表 P4 注意)
Task 8: complete (commits d4a6d23..1d9f252, review clean;11 张侵略效果全量核对通过;歧义待裁: raid 取半口径、防御上限按当前红点池)
Task 9: complete (commits 1d9f252..82ee62e, review clean;战争 3 效果全核对;⚠️ 领土取整无明文已披露)
Task 10: complete (062528f + fix 2a95211, review clean;⚠️ 待裁: 退出后时代 II/III 牌堆人数重调未实现(brief 与规则书冲突,规则书要求重调);_enter_age_four 起始玩家退出边角;P3 认领: trade_routes/scientific_cooperation 效果、公共阵型区、弃牌决策先于抓牌)
Task 11: complete (commits 2a95211..f48ce5b, review clean 15/15 事件对照 PDF 全过;brief 四处事件语义猜错以 PDF 为准;T12 注意: 翻面奇迹终局计分口径复查、politics_of_strength 终局分值无明文)
Task 12: complete (commits f48ce5b..d3f646c, review clean;15 Impact 全核对,终局计分非零;T13 顺手: _impact_of_technology docstring 订正、Gates 遗留归属确认)
Task 13: complete (commits d3f646c..2b281f1;公共阵型区修复/退出牌堆重调/shakespeare/bach/deferred.md 22+5 项入库;729 测试)
全部 13 任务完成,进入 P2 全分支终审
P2 终审: 5 项修正 (commit 90e01e4): 军事手牌/条约过期、退出者禁竞拍、守恒补偿、防御上限总值;734 测试全绿
P2 完成
