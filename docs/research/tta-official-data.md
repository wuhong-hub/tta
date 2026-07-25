# 《历史巨轮：人类文明新篇章》(Through the Ages: A New Story of Civilization, 2015) 官方游戏数据

> 研究日期:2026-07-24。仅收集 2015 新版(A New Story of Civilization)数据,不含 2006 旧版。
>
> 可信度分级:**[官方]** = CGE 官方规则书/手册/实物照片;**[实物照片]** = BGG 上玩家拍摄的官方组件照片(等同官方,但受照片清晰度限制);**[实现]** = 开源/在线实现(BGO 等);**[维基/论坛]** = 粉丝整理;**[推断]** = 由已证实数据按规律推得。

## 主要来源

| # | 来源 | 类型 | URL |
|---|------|------|-----|
| S1 | 官方规则书 Code of Laws (EN, 2015) | 官方 PDF | https://filemanager.czechgames.com/storage/files/through-the-ages-a-new-story-of-civilization/rules/through-the-ages-new-story-rules-en.pdf |
| S2 | 官方手册 Handbook "Your First Game" (EN) | 官方 PDF(镜像) | https://lelekan.com.ua/files/rules/2542/pravila-nastilnoyi-gri-kriz-epohi-nova-istoriya-civilizaciyi-through-the-ages-a-new-story-of-civilization-anglijskoyu-movoyu.0.pdf (原件在 filemanager.czechgames.com) |
| S3 | BGG 图片 2725254(英文玩家版图 4160px 原图) | 实物照片 | https://boardgamegeek.com/image/2725254 |
| S4 | BGG 图片 4187492(银行轨道俯视特写) | 实物照片 | https://boardgamegeek.com/image/4187492 |
| S5 | BGG 图片 2911022(时代 A 六张领袖牌) | 实物照片 | https://boardgamegeek.com/image/2911022 |
| S6 | BGG 图片 3316006 / 3316007(各时代内政/军事牌样例) | 实物照片 | https://boardgamegeek.com/image/3316006 , https://boardgamegeek.com/image/3316007 |
| S7 | BGG 图片 3853761-3853763(I/II/III 时代 2 人局牌堆照片) | 实物照片 | https://boardgamegeek.com/image/3853761 等 |
| S8 | BGG 图片 3126864(奇迹牌 Pyramids 等) | 实物照片 | https://boardgamegeek.com/image/3126864 |
| S9 | BGG 文件 "TtA: A New Story of Civilization Card Reference v1.09"(数据取自 BGO v2.5;本环境被 Cloudflare 拦截未能下载,仅引用其存在与描述) | 粉丝整理(源自 BGO) | https://boardgamegeek.com/filepage/123302 |
| S10 | Through the Ages Wiki (fandom) — Card Row / Colossus / Card List: Digital Edition | 维基 | https://throughtheages.fandom.com/wiki/Card_Row 等 |
| S11 | Stately Play 腐败机制策略文(确认蓝银行 -2/-4/-6 分区) | 论坛/博客 | https://statelyplay.com/2017/09/26/strategy-101-through-the-ages-corruption-edition/ |
| S12 | 扩展规则(New Leaders and Wonders) | 官方 PDF | https://filemanager.czechgames.com/storage/files/through-the-ages-new-leaders-and-wonders/rules/through-the-ages-expansion-rules-en.pdf |

---

## 1. 卡牌列(Card Row)费用分布 — [官方,高可信]

13 个牌位,费用(S1 p.2 "Preparing the Card Row" + S1 p.5 "Take a Non-Wonder Card" + S2 p.6,另有卡牌列官方美术图 BGG image 2653725 佐证):

| 牌位(从左到右) | 1-5 | 6-9 | 10-13 |
|---|---|---|---|
| 内政行动点费用 | **1** | **2** | **3** |

即 **5×1 / 4×2 / 4×3**。

相关规则(S1/S2,高可信):
- 补牌:回合开始移除最左端卡牌(2 人局 3 张、3 人局 2 张、4 人局 1 张),其余左移,空位从右端补新牌。
- 奇迹牌费用 = 牌位所示费用 + 每已完成 1 个奇迹 +1。
- 第一轮玩家依次只有 1/2/3/4 个内政行动。

---

## 2. 玩家版图轨道数值

### 2.1 黄色人口轨道(Yellow Bank,18 格)— [实物照片+官方手册插图,高可信;个别格为推断]

证据:S3(英文版图原图)、S4(俯视特写)、S2 第 2-3 页官方插图、BGG image 8054227(意大利文版)。

**结构**:18 格分为 **8 个区段**,区段上方圆圈数字 = 幸福需求(该数字即"最左空置区段"要求的笑脸数,0-8)。最右端是 "Yellow Bank" 文字标签区(上方标 **0**,**无格**);需求 0 表示银行全满时无需笑脸。幸福指示轨就是这组圆圈数字(幸福标记放在上面)。

从左到右(人口最多→最少):

| 区段(幸福需求) | 8 | 7 | 6 | 5 | 4 | 3 | 2 | 1 | (0=标签区) |
|---|---|---|---|---|---|---|---|---|---|
| 格数 | 2 | 2 | 2 | 2 | 2 | 2 | **4** | 2 | 0 |
| 格下增人口食物成本 | 7 | 7 | 5 | 5 | 4 | 4 | 3 | 2 | — |
| 区段最左格食物消耗 | -6 | -4* | -4 | -3* | -3 | -2* | -2 | -1 | — |

*标注 `-6/-4/-3/-2`(区段 8/6/4/2)均在照片中直接读到(S3 放大/S4);需求 0/1 区的 -1、需求 2 区的 -2 亦直接读到。
标 `*` 的区段 7/5/3 消耗格被方块遮挡,按成对规律**推断**为 -4/-3/-2(规律:消耗值两两成对 -1,-2,-2,-3,-3,-4,-4,末端 -6)。**[推断,中高可信]**

- 增人口成本 = "最右被占用区段"下方的白色数字(规则书原文)。成本成对印刷:2,3,4,4,5,5,7,7(S2 官方插图中 4、S3 中 5、7、S4 中 2,3,4,5,7 均直接读到)。**高可信**。
- 食物不足时每缺 1 食物扣 4 文化分(S1 p.6)。
- 初始设置:黄色方块 25 个 = 18(银行)+1(工人池)+6(科技牌上)(S1/S2)。

### 2.2 蓝色供给区(Blue Bank,16 格)— [实物照片,高可信;-4/-6 为强推断]

证据:S3、S4、S2 p.2 插图、S11。

**结构**:16 格分 3 段(从左到右):**5 格 + 5 格 + 6 格**。每段最左格印有负数(腐败值):

| 段 | 左段(格 1-5) | 中段(格 6-10) | 右段(格 11-16) |
|---|---|---|---|
| 最左格数值 | **-6** | **-4** | **-2** |

- 腐败 = 回合结束时"最左未覆盖的负数";全部被方块覆盖则无腐败(S1 p.6)。
- 推论:银行内方块 ≥11 个时无腐败(右段第 11 格仍被覆盖);6-10 个 → -2;1-5 个 → -4;0 个 → -6。与 S11 描述一致。
- -2 在 S3/S4 中直接读到;-4/-6 被方块遮挡,由 S11("sections marked -2, -4, and -6")+ 结构推得。**-2 高可信;-4/-6 中高可信**。

---

## 3. 初始科技牌(印在玩家版图上,属时代 A)— [官方手册+实物照片,高可信]

证据:S2 p.2-3(官方特写插图及文字)、S3(实物照片局部)。

| 科技 | 类型 | 建造费(资源) | 每工人产出 | 备注 |
|---|---|---|---|---|
| **Agriculture** | 农场(麦穗图标) | **2** | 每蓝色方块 = **1 食物** | 初始 2 个工人(2 农场) |
| **Bronze** | 矿场(镐图标) | **2** | 每蓝色方块 = **1 资源** | 初始 2 个工人(2 矿场) |
| **Philosophy** | 城市建筑:实验室 (lab) | **3** | 每实验室 = **1 科技** | 初始 1 个工人(1 实验室) |
| **Religion** | 城市建筑:寺庙 (temple) | **3** | 每寺庙 = **1 文化 + 1 笑脸** | 初始 0 个工人(无寺庙) |
| **Warriors** | 军事单位:步兵 | **2** | 每单位 = **1 力量** | 初始 1 个工人(1 武士) |
| **Despotism** | 政体 | — | **4 内政行动 + 2 军事行动;城市建筑上限 2** | 初始 4 白 2 红方块置牌旁 |

注:建造费数字均在官方插图中直接读到(Agriculture 2、Bronze 2、Philosophy 3、Religion 3、Warriors 2);Despotism 的行动数与上限 2 直接见于 S1 p.2/S2 p.3。

---

## 4. 时代 A 内政牌完整列表(共 20 张)

组成:6 领袖 + 4 奇迹 + 10 行动牌。**无科技牌**(初始科技印在版图上)。来源:牌名与总数 [维基/BGG 内容清单,中高可信];卡牌文本均取自官方实物照片/手册 [高可信]。

### 4.1 领袖(绿色,各 ×1)— 文本 100% 取自 S5 官方牌照片

| 牌名 | 效果文本(英文原文意译) | 底部图标 |
|---|---|---|
| **Alexander the Great** | 你的每个军事单位为你提供 +1 力量。作为政治行动,可将 Alexander 移出游戏,并从供应堆拿 1 个黄色方块放入你的黄色银行。 | 力量相关 |
| **Aristotle** | 每当你从卡牌列拿取一张科技牌,你获得 1 科技分。 | — |
| **Hammurabi** | 你的回合中,你可以把 1 个军事行动当作内政行动使用。从卡牌列拿取领袖牌少花 1 内政行动。 | — |
| **Homer** | 你的回合中,建造/升级军事单位时额外有 1 资源可用。当你替换掉 Homer 时,可将此牌滑入你 1 个已完成奇迹下方,使其多 1 笑脸;若如此做,你不会拿回该内政行动。 | 1 笑脸 |
| **Julius Caesar** | 你打出政治行动后,可以再打出 1 个政治行动。此能力每局游戏只能用 1 次。 | +1 力量,+1 军事行动 |
| **Moses** | 你增加人口少花 1 食物。 | — |

### 4.2 奇迹(紫色,各 ×1)

| 牌名 | 各阶段费用 | 效果 | 来源与可信度 |
|---|---|---|---|
| **Pyramids** | **3-2-1** | **+1 内政行动**(白方块图标) | S8 官方牌照片,高 |
| **Colossus** | **3-3** | **+2 力量,+1 殖民修正** | 阶段数:常识+多照片(未直接读到数字,中);效果:fandom 维基"New Story version: +2 Strength and +1 Colonization"(中高) |
| **Hanging Gardens** | **2-2-2** | **+1 文化,+2 笑脸** | S6 照片(阶段 2-2-2 与 2 笑脸直接读到;文化 1 图标,中高) |
| **Library of Alexandria** | **1-4-1** | "你的手牌可额外持有 1 张内政牌和 1 张军事牌…"(后半句照片未完整拍到) | S2 p.4/p.7 照片(阶段 1-4-1、效果前半句直接读到,高;完整文本未找到) |

### 4.3 行动牌(黄色,共 10 张)

文本均取自 S2/S6 官方照片(高可信);**每种张数**来自 BGG 内容清单/fandom 汇总(中高可信,未能用官方文件逐一点算):

| 牌名 | 效果文本 | 张数 |
|---|---|---|
| **Stockpile** | 获得 1 资源和 1 食物。 | ×1 |
| **Frugality** | 增加你的人口。支付食物成本后,获得 1 食物。 | ×1 |
| **Engineering Genius** | 建造奇迹的 1 个阶段;少付 2 资源。 | ×1 |
| **Patriotism** | 本回合,你建造/升级军事单位时额外有 1 资源可用,并有 1 额外军事行动。 | ×1 |
| **Rich Land** | 建造或升级 1 个农场或矿场;少付 1 资源。 | ×2 |
| **Urban Growth** | 建造或升级 1 个城市建筑;少付 1 资源。 | ×2 |
| **Cultural Heritage** | 获得 1 科技分和 4 文化分。 | ×2 |

(Cultural Heritage ×2 另有 S2 p.7 官方示例牌列同时出现两张佐证。)

---

## 5. 各时代牌堆组成与张数

### 5.1 内政牌堆(浅色牌背)

| 牌堆 | 总张数 | 组成 | 可信度 |
|---|---|---|---|
| 时代 A | **20** | 4 奇迹 + 6 领袖 + 10 行动 | BGG 内容清单/fandom,中高 |
| 时代 I | **53** | 30 科技 + 4 奇迹 + 6 领袖 + 13 行动 | 同上,**中**(未经官方文件核实) |
| 时代 II | **53** | 同上 | 同上,中 |
| 时代 III | **53** | 同上 | 同上,中 |

### 5.2 军事牌堆(深色牌背)

| 牌堆 | 总张数 | 组成(BGG 内容清单汇总,中可信) |
|---|---|---|
| 时代 A | **10** | 10 事件牌 |
| 时代 I | **45** | 15 事件 + 10 阵型 + 6 侵略 + 6 地区 + 6 防御/殖民奖励 + 2 条约 |
| 时代 II | **50** | 15 事件 + 9 侵略 + 6 阵型 + 6 地区 + 6 防御/殖民奖励 + 4 战争 + 4 条约 |
| 时代 III | **45** | 15 事件 + 8 侵略 + 6 战争 + 6 阵型 + 6 防御/殖民奖励 + 4 条约 |

总计 329 张牌(179 内政 + 150 军事)。**[维基/BGG 内容清单,中可信;未经官方文件核实]**

### 5.3 人数调整(官方规则书 S1 p.2 "Deck Setup",高可信)

- **3 人局**:内政牌堆 I、II、III 各有 **3 张带 "4" 标记**的牌,移除(每堆 → 50 张)。
- **2 人局**:内政牌堆 I、II、III 再额外移除 **6 张带 "3+" 标记**的牌(共移除 9 张,每堆 → 44 张);并移除军事牌堆中所有**条约牌**(军事 I 有 2 张、II 和 III 各 4 张)。
- 时代 A 内政堆与军事堆不做人数调整;时代 A 军事堆开局随机取 **玩家人数 + 2** 张作为当前事件堆,其余放回盒中(S1/S2,高可信)。
- 2 人局移除的 9 张 Age I 牌(实物照片 S7 = 3853761,显示 2 人局**使用**的 32 张非行动牌:6 领袖、Swordsmen×2、Knights×2、Irrigation×2、Iron×2、Alchemy×2、Theology×1、Printing Press×2、Bread and Circuses×1、Drama×1、Cartography、Masonry、Warfare、Code of Laws、Theocracy、Monarchy、4 奇迹)——即被移除的是剩余科技/行动牌;照片未给出行动牌部分,**具体 9 张名单未完整确认**。

---

## 6. 军事牌堆明细(部分,低优先级)

完整名单**未找到**可直接核实的来源(BGG Card Reference 被反爬拦截)。已确认:

- **时代 A 军事 = 10 张事件牌**(BGG 内容清单,中)。S6 照片直接确认其中 4 张:**Development of Politics**、**Development of Civilization**、**Development of Settlement**、**Development of Religion**(高)。其余 6 张未直接确认;按旧版与维基线索可能为 Development of Agriculture / Crafts / Markets / Science / Trade Routes / Warfare 中的 6 个(**未证实,低可信**)。S12 扩展规则提到扩展另含 Development of Planning。
- 其他样张(S6 照片,高可信存在性):
  - Age I:阵型 **Medieval Army**(2 步兵,战术力 2)、军事奖励牌(防御 ×2 / 殖民 1)、侵略 **Raid**、事件 **Crusades**。
  - Age II:条约 **International Trade Agreement**、阵型 **Classic Army**(3 单位)、地区 **Strategic Territory**、战争 **War over Technology**。
  - Age III:事件 **Impact of Architecture**、侵略 **Plunder**、军事奖励(防御 ×6 / 殖民 3)、阵型 **Shock Troops**(3 单位,战术力 4/6)。

---

## 7. 未找到/未完全确认项汇总

1. 黄轨区段 7/5/3 的消耗值(推断 -4/-3/-2,规律与已读 5 个值自洽,但无直接图像证据)。
2. Library of Alexandria 完整效果文本(后半句)。
3. 时代 A 各行动牌的确切张数(来源为 BGG/fandom 汇总,非官方文件;总数 20 与组成 6+4+10 两来源一致)。
4. 时代 I/II/III 内政牌完整逐张列表及张数(仅有 2 人局 Age I 部分照片;BGG Card Reference v1.09 是最佳来源但被 Cloudflare 拦截,建议人工登录 BGG 下载: https://boardgamegeek.com/filepage/123302 )。
5. 军事牌堆 A/I/II/III 完整逐张列表(同上)。
6. 内政牌堆 53 张的逐类细目(30 科技等)未经官方文件核实。
