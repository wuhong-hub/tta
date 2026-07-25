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
