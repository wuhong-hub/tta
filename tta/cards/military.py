"""官方军事牌库(P2-T2 转录).

数值权威来源: Card Reference v1.09 第 3 页(奖励/侵略/战争/条约/阵型)
与第 4 页(事件 A 10 + I 15 + II 15 + III 15, 地区 I 6 + II 6),
实现者以 300/600 DPI 图标核对转录。

张数约定(军事牌堆):
- 事件/地区无张数列, 每张 1 份, quantities = (1, 1, 1);
- 条约仅 3-4 人局使用(规则书 p2: 2 人局移除全部条约牌), quantities = (0, 1, 1);
- 奖励/侵略/战争/阵型取 PDF "#" 列, 不随人数调整, quantities = (n, n, n)。

牌堆总数(Σ quantities, 2p/3p/4p):
- Age A:   10/10/10  (事件 10)
- Age I:   43/45/45  (事件 15 + 地区 6 + 阵型 10 + 侵略 6 + 奖励 6 + 条约 2)
- Age II:  46/50/50  (事件 15 + 地区 6 + 阵型 6 + 侵略 9 + 战争 4 + 奖励 6 + 条约 4)
- Age III: 41/45/45  (事件 15 + 阵型 6 + 侵略 8 + 战争 6 + 奖励 6 + 条约 4)

字段约定:
- 侵略/战争: military_cost = 军事行动费, 效果文本入 text, handler = 卡 id;
- 事件/条约: 效果文本入 text, handler = 卡 id(处理器后续任务注册);
- 阵型: tactics_units 键为 CardCategory 名("INFANTRY"/"CAVALRY"/"ARTILLERY"),
  tactics_strength_outdated 为括号内旧式军力(时代 I 无括号, 记 0);
- 地区: territory_immediate / territory_permanent 键为收益名
  ("food"/"materials"/"science"/"culture"/"strength"/"happiness"/
  "population"/"military_card"/"yellow_token"/"blue_token")。

转录存疑(详见 .superpowers/sdd/task-2-report.md):
- emigration: 参考表图标为"不快乐工人", 括注"移回黄色银行", 按"人口"转录;
- 阵型种类 PDF 为 15 种(brief 称 18 种), 以 PDF 为准。
"""

from tta.engine.enums import Age, CardCategory, DeckType
from tta.engine.model import CardDefinition

_ONE = (1, 1, 1)
_PACT_Q = (0, 1, 1)  # 条约: 2 人局移除


def _bonus(
    card_id: str, name: str, name_en: str, age: Age,
    defense: int, colonize: int, count: int,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=age,
        deck=DeckType.MILITARY, category=CardCategory.BONUS,
        text=f"防御 +{defense};殖民 +{colonize}。",
        defense_bonus=defense, colonize_bonus=colonize,
        quantities=(count, count, count),
    )


def _aggression(
    card_id: str, name: str, name_en: str, age: Age,
    military_cost: int, count: int, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=age,
        deck=DeckType.MILITARY, category=CardCategory.AGGRESSION,
        text=text, military_cost=military_cost, handler=card_id,
        quantities=(count, count, count),
    )


def _war(
    card_id: str, name: str, name_en: str, age: Age,
    military_cost: int, count: int, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=age,
        deck=DeckType.MILITARY, category=CardCategory.WAR,
        text=text, military_cost=military_cost, handler=card_id,
        quantities=(count, count, count),
    )


def _pact(
    card_id: str, name: str, name_en: str, age: Age, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=age,
        deck=DeckType.MILITARY, category=CardCategory.PACT,
        text=text, handler=card_id, quantities=_PACT_Q,
    )


def _tactics(
    card_id: str, name: str, name_en: str, age: Age,
    units: dict[str, int], strength: int, outdated: int, count: int,
) -> CardDefinition:
    part = "、".join(f"{n} {u}" for u, n in units.items())
    text = f"阵型:{part};军力 +{strength}"
    if outdated:
        text += f"(旧式 +{outdated})"
    text += "。"
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=age,
        deck=DeckType.MILITARY, category=CardCategory.TACTICS,
        text=text, tactics_units=units, tactics_strength=strength,
        tactics_strength_outdated=outdated,
        quantities=(count, count, count),
    )


def _event(
    card_id: str, name: str, name_en: str, age: Age, text: str,
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=age,
        deck=DeckType.MILITARY, category=CardCategory.EVENT,
        text=text, handler=card_id, quantities=_ONE,
    )


def _territory(
    card_id: str, name: str, name_en: str, age: Age, text: str,
    immediate: dict[str, int], permanent: dict[str, int],
) -> CardDefinition:
    return CardDefinition(
        id=card_id, name=name, name_en=name_en, age=age,
        deck=DeckType.MILITARY, category=CardCategory.TERRITORY,
        text=text, territory_immediate=immediate,
        territory_permanent=permanent, quantities=_ONE,
    )


# --- 军事奖励牌(PDF 第 3 页 Bonus 表, Def./Col./# 列) ---------------------------

DEFENSE_COLONIZATION_I = _bonus(
    "defense_colonization_i", "防御/殖民 I", "Defense / Colonization I",
    Age.I, 2, 1, 6,
)
DEFENSE_COLONIZATION_II = _bonus(
    "defense_colonization_ii", "防御/殖民 II", "Defense / Colonization II",
    Age.II, 4, 2, 6,
)
DEFENSE_COLONIZATION_III = _bonus(
    "defense_colonization_iii", "防御/殖民 III", "Defense / Colonization III",
    Age.III, 6, 3, 6,
)

# --- 侵略牌(PDF 第 3 页 Aggression 表) ------------------------------------------
# Cost 列 = 军事行动费(红色军事行动标记数)。

ENSLAVE_I = _aggression(
    "enslave_i", "奴役", "Enslave", Age.I, 2, 2,
    "受害者:-1 人口。侵略者:+2 食物并 +2 资源。",
)
PLUNDER_I = _aggression(
    "plunder_i", "掠夺", "Plunder", Age.I, 1, 2,
    "受害者:失去共 3 食物/资源。侵略者:获得等量。",
)
RAID_I = _aggression(
    "raid_i", "突袭", "Raid", Age.I, 1, 2,
    "受害者:-1 个 I 级或 A 级建筑。侵略者:+等于其建造费一半(向上取整)的资源。",
)
ANNEX_II = _aggression(
    "annex_ii", "吞并", "Annex", Age.II, 2, 1,
    "受害者:失去 1 个殖民地。侵略者:获得该殖民地。",
)
INFILTRATE_II = _aggression(
    "infiltrate_ii", "渗透", "Infiltrate", Age.II, 2, 2,
    "受害者:弃掉 1 个领袖或 1 个未完成奇迹。"
    "侵略者:每级领袖/奇迹 +3 文化。",
)
PLUNDER_II = _aggression(
    "plunder_ii", "掠夺", "Plunder", Age.II, 1, 2,
    "受害者:失去共 5 食物/资源。侵略者:获得等量。",
)
RAID_II = _aggression(
    "raid_ii", "突袭", "Raid", Age.II, 2, 2,
    "受害者:-1 个 II-A 级建筑,-1 个 I-A 级建筑。"
    "侵略者:+等于其建造费一半(向上取整)的资源。",
)
SPY_II = _aggression(
    "spy_ii", "间谍", "Spy", Age.II, 1, 2,
    "受害者:-5 科技。侵略者:获得等量文化分。",
)
ARMED_INTERVENTION_III = _aggression(
    "armed_intervention_iii", "武装干涉", "Armed Intervention", Age.III, 2, 4,
    "受害者:-7 文化。侵略者:+7 文化。",
)
PLUNDER_III = _aggression(
    "plunder_iii", "掠夺", "Plunder", Age.III, 1, 2,
    "受害者:失去共 7 食物/资源。侵略者:获得等量。",
)
RAID_III = _aggression(
    "raid_iii", "突袭", "Raid", Age.III, 3, 2,
    "受害者:-1 个 III-A 级建筑,-1 个 II-A 级建筑。"
    "侵略者:+等于其建造费一半(向上取整)的资源。",
)

# --- 战争牌(PDF 第 3 页 War 表) -------------------------------------------------

WAR_OVER_TECHNOLOGY_II = _war(
    "war_over_technology_ii", "科技之战", "War over Technology", Age.II, 2, 2,
    "败者:-科技,等于胜者的科技优势。胜者:+所失科技;可夺取蓝色科技。",
)
WAR_OVER_TERRITORY_II = _war(
    "war_over_territory_ii", "领土之战", "War over Territory", Age.II, 2, 2,
    "败者:-人口标记,等于 1 + 胜者军力优势的 1/5。胜者:获得等量人口标记。",
)
WAR_OVER_CULTURE_III = _war(
    "war_over_culture_iii", "文化之战", "War over Culture", Age.III, 3, 6,
    "败者:-文化,等于 5 + 胜者的文化优势。胜者:获得等量。",
)

# --- 条约牌(PDF 第 3 页 Pact 表, A/B 列效果; 2 人局移除) --------------------------

OPEN_BORDERS_AGREEMENT = _pact(
    "open_borders_agreement", "开放边境协议", "Open Borders Agreement", Age.I,
    "对称。双方各 +1 军事行动;若一方攻击另一方,攻击者 +2 军力。",
)
TRADE_ROUTES_AGREEMENT = _pact(
    "trade_routes_agreement", "贸易路线协议", "Trade Routes Agreement", Age.I,
    "A:每回合可用 1 食物代替 1 资源;B:每回合可用 1 资源代替 1 食物。",
)
ACCEPTANCE_OF_SUPREMACY = _pact(
    "acceptance_of_supremacy", "霸权承认", "Acceptance of Supremacy", Age.II,
    "A:+1 文化,不可攻击 B;B:-1 文化,不可攻击 A。",
)
INTERNATIONAL_TRADE_AGREEMENT = _pact(
    "international_trade_agreement", "国际贸易协议",
    "International Trade Agreement", Age.II,
    "A:+1 资源;B:+1 科技。",
)
PROMISE_OF_MILITARY_PROTECTION = _pact(
    "promise_of_military_protection", "军事保护承诺",
    "Promise of Military Protection", Age.II,
    "A:+1 文化;B:+4 军力并 -1 文化;若一方攻击另一方,条约终止。",
)
SCIENTIFIC_COOPERATION = _pact(
    "scientific_cooperation", "科学合作", "Scientific Cooperation", Age.II,
    "对称。以 -2 科技研发一项科技,另一名玩家支付 1 科技。",
)
INTERNATIONAL_TOURISM = _pact(
    "international_tourism", "国际旅游", "International Tourism", Age.III,
    "对称。对方每拥有 1 个奇迹,+1 文化。",
)
LOSS_OF_SOVEREIGNTY = _pact(
    "loss_of_sovereignty", "主权丧失", "Loss of Sovereignty", Age.III,
    "A:+2 笑脸,不可攻击 B;B:-2 笑脸,不可攻击 A;无人能对 B 宣战。",
)
MILITARY_ALLIANCE = _pact(
    "military_alliance", "军事同盟", "Military Alliance", Age.III,
    "对称。双方各 +3 军力;若一方攻击另一方,条约终止。",
)
PEACE_TREATY = _pact(
    "peace_treaty", "和平条约", "Peace Treaty", Age.III,
    "对称。双方各 +1 笑脸;不可互相攻击。",
)

# --- 阵型牌(PDF 第 3 页 Tactics 表, 15 种; 括号内为旧式军力) ----------------------

FIGHTING_BAND = _tactics(
    "fighting_band", "战斗队", "Fighting Band", Age.I,
    {"INFANTRY": 2}, 1, 0, 2,
)
HEAVY_CAVALRY = _tactics(
    "heavy_cavalry", "重骑兵", "Heavy Cavalry", Age.I,
    {"CAVALRY": 3}, 4, 0, 2,
)
LEGION = _tactics(
    "legion", "军团", "Legion", Age.I,
    {"INFANTRY": 3}, 2, 0, 2,
)
MEDIEVAL_ARMY = _tactics(
    "medieval_army", "中世纪军队", "Medieval Army", Age.I,
    {"INFANTRY": 1, "CAVALRY": 1}, 2, 0, 2,
)
PHALANX = _tactics(
    "phalanx", "方阵", "Phalanx", Age.I,
    {"INFANTRY": 2, "CAVALRY": 1}, 3, 0, 2,
)
CLASSIC_ARMY = _tactics(
    "classic_army", "古典军队", "Classic Army", Age.II,
    {"INFANTRY": 2, "CAVALRY": 2}, 8, 4, 1,
)
CONQUISTADORS = _tactics(
    "conquistadors", "征服者", "Conquistadors", Age.II,
    {"INFANTRY": 1, "CAVALRY": 2}, 5, 3, 1,
)
DEFENSIVE_ARMY = _tactics(
    "defensive_army", "防御军队", "Defensive Army", Age.II,
    {"INFANTRY": 2, "ARTILLERY": 1}, 6, 3, 1,
)
FORTIFICATIONS = _tactics(
    "fortifications", "防御工事", "Fortifications", Age.II,
    {"ARTILLERY": 2}, 5, 3, 1,
)
MOBILE_ARTILLERY = _tactics(
    "mobile_artillery", "机动炮兵", "Mobile Artillery", Age.II,
    {"CAVALRY": 1, "ARTILLERY": 1}, 5, 3, 1,
)
NAPOLEONIC_ARMY = _tactics(
    "napoleonic_army", "拿破仑军队", "Napoleonic Army", Age.II,
    {"INFANTRY": 1, "CAVALRY": 1, "ARTILLERY": 1}, 7, 4, 1,
)
ENTRENCHMENTS = _tactics(
    "entrenchments", "堑壕", "Entrenchments", Age.III,
    {"INFANTRY": 1, "ARTILLERY": 2}, 9, 5, 1,
)
MECHANIZED_ARMY = _tactics(
    "mechanized_army", "机械化军队", "Mechanized Army", Age.III,
    {"CAVALRY": 1, "ARTILLERY": 2}, 10, 5, 2,
)
MODERN_ARMY = _tactics(
    "modern_army", "现代化军队", "Modern Army", Age.III,
    {"INFANTRY": 2, "CAVALRY": 1, "ARTILLERY": 1}, 13, 7, 2,
)
SHOCK_TROOPS = _tactics(
    "shock_troops", "突击部队", "Shock Troops", Age.III,
    {"INFANTRY": 1, "CAVALRY": 2, "ARTILLERY": 1}, 11, 6, 1,
)

# --- 事件牌(PDF 第 4 页 Events 表) ----------------------------------------------

# 时代 A(10 张)
DEVELOPMENT_OF_AGRICULTURE = _event(
    "development_of_agriculture", "农业发展", "Development of Agriculture",
    Age.A, "每个文明 +2 食物。",
)
DEVELOPMENT_OF_CIVILIZATION = _event(
    "development_of_civilization", "文明发展", "Development of Civilization",
    Age.A,
    "每个文明可选择:+1 人口并 -1 食物;或以 -1 资源建造一个农场/矿场/"
    "城市建筑;或以 -1 科技研发一项科技。",
)
DEVELOPMENT_OF_CRAFTS = _event(
    "development_of_crafts", "工艺发展", "Development of Crafts",
    Age.A, "每个文明 +2 资源。",
)
DEVELOPMENT_OF_MARKETS = _event(
    "development_of_markets", "市场发展", "Development of Markets",
    Age.A, "每个文明 +2 食物或 +2 资源(玩家选择)。",
)
DEVELOPMENT_OF_POLITICS = _event(
    "development_of_politics", "政治发展", "Development of Politics",
    Age.A, "每名玩家 +3 张军事牌。",
)
DEVELOPMENT_OF_RELIGION = _event(
    "development_of_religion", "宗教发展", "Development of Religion",
    Age.A, "每名有可用工人的玩家可立即免费建造一个宗教。",
)
DEVELOPMENT_OF_SCIENCE = _event(
    "development_of_science", "科学发展", "Development of Science",
    Age.A, "每个文明 +2 科技。",
)
DEVELOPMENT_OF_SETTLEMENT = _event(
    "development_of_settlement", "定居发展", "Development of Settlement",
    Age.A, "每个文明免费 +1 人口。",
)
DEVELOPMENT_OF_TRADE_ROUTE = _event(
    "development_of_trade_route", "贸易路线发展", "Development of Trade Route",
    Age.A, "每个文明 +1 科技、+1 食物、+1 资源。",
)
DEVELOPMENT_OF_WARFARE = _event(
    "development_of_warfare", "军事发展", "Development of Warfare",
    Age.A, "每名有可用工人的玩家可立即免费建造一个战士。",
)

# 时代 I(15 张)
BARBARIANS = _event(
    "barbarians", "蛮族", "Barbarians", Age.I,
    "若文化领先者是两个最弱文明之一,其失去 1 人口。",
)
BORDER_CONFLICT = _event(
    "border_conflict", "边境冲突", "Border Conflict", Age.I,
    "最弱文明失去 1 个城市建筑、农场或矿场;最强文明生产 3 资源。",
)
CRUSADES = _event(
    "crusades", "十字军", "Crusades", Age.I,
    "最强文明 +4 文化;最弱文明 -4 文化。",
)
CULTURAL_INFLUENCE = _event(
    "cultural_influence", "文化影响", "Cultural Influence", Age.I,
    "每个文明 +文化,等于其文化产出。",
)
FORAY = _event(
    "foray", "袭掠", "Foray", Age.I,
    "两个最强文明各生产共 3 食物/资源。",
)
GOOD_HARVEST = _event(
    "good_harvest", "丰收", "Good Harvest", Age.I,
    "每名玩家的农场立即生产;忽略消耗与腐败。",
)
IMMIGRATION = _event(
    "immigration", "移民", "Immigration", Age.I,
    "笑脸最多的文明 +1 人口。",
)
NEW_DEPOSITS = _event(
    "new_deposits", "新矿藏", "New Deposits", Age.I,
    "每名玩家的矿场立即生产;忽略腐败。",
)
PESTILENCE = _event(
    "pestilence", "瘟疫", "Pestilence", Age.I,
    "每个文明 -1 人口。",
)
RAIDERS = _event(
    "raiders", "掠夺者", "Raiders", Age.I,
    "两个最弱文明各失去共 2 食物/资源。",
)
RATS = _event(
    "rats", "鼠患", "Rats", Age.I,
    "每个文明失去所有储存的食物。",
)
REBELLION = _event(
    "rebellion", "叛乱", "Rebellion", Age.I,
    "每名玩家失去 2 个内政行动(于其下一回合)。",
)
REIGN_OF_TERROR = _event(
    "reign_of_terror", "恐怖统治", "Reign of Terror", Age.I,
    "最弱文明 -1 人口。",
)
SCIENTIFIC_BREAKTHROUGH_EVENT = _event(
    "scientific_breakthrough", "科学突破", "Scientific Breakthrough", Age.I,
    "每个文明 +科技,等于其科技产出。",
)
UNCERTAIN_BORDERS = _event(
    "uncertain_borders", "边界未定", "Uncertain Borders", Age.I,
    "最弱文明从其黄色银行给最强文明的黄色银行 1 个人口标记。",
)

# 时代 II(15 张)
CIVIL_UNREST = _event(
    "civil_unrest", "内乱", "Civil Unrest", Age.II,
    "每个文明每个不快乐工人 -4 文化;不快乐工人最多的所有文明:-1 蓝色标记;"
    "若没有不快乐工人,无效果。",
)
COLD_WAR = _event(
    "cold_war", "冷战", "Cold War", Age.II,
    "两个最强文明 +6 科技。",
)
CRIME_WAVE = _event(
    "crime_wave", "犯罪浪潮", "Crime Wave", Age.II,
    "两个最弱文明 -3 文化并 -1 蓝色标记。",
)
ECONOMIC_PROGRESS = _event(
    "economic_progress", "经济进步", "Economic Progress", Age.II,
    "每名玩家的矿场与农场立即生产;不忽略消耗与腐败。",
)
EMIGRATION = _event(
    "emigration", "人口外迁", "Emigration", Age.II,
    "每个文明失去其一半人口(向上取整,移回黄色银行)。",
)
ICONOCLASM = _event(
    "iconoclasm", "偶像破坏", "Iconoclasm", Age.II,
    "弃掉所有非当前时代的领袖。",
)
INDEPENDENCE_DECLARATION = _event(
    "independence_declaration", "独立宣言", "Independence Declaration",
    Age.II, "最弱文明失去 1 个殖民地(由该玩家选择)。",
)
INTERNATIONAL_AGREEMENT = _event(
    "international_agreement", "国际协议", "International Agreement", Age.II,
    "最强文明可用最多 5 个内政行动拿牌;跳过其下一政治行动;补充卡牌列。",
)
NATIONAL_PRIDE = _event(
    "national_pride", "民族自豪", "National Pride", Age.II,
    "文化分最多的文明 +5 文化。",
)
POLITICS_OF_STRENGTH = _event(
    "politics_of_strength", "强权政治", "Politics of Strength", Age.II,
    "最强文明 +5 张军事牌;最弱文明 -3 张军事牌;若为最终时代,改为 ±文化。",
)
POPULARIZATION_OF_SCIENCE = _event(
    "popularization_of_science", "科学普及", "Popularization of Science",
    Age.II, "每个文明 +文化,等于其科技产出。",
)
PROSPERITY = _event(
    "prosperity", "繁荣", "Prosperity", Age.II,
    "每个文明每个笑脸 +1 食物(至多 8)。",
)
RAVAGES_OF_TIME = _event(
    "ravages_of_time", "岁月侵蚀", "Ravages of Time", Age.II,
    "每名玩家将 1 个 A 或 I 时代奇迹翻为面朝下;效果失效,生产 2 文化。",
)
REFUGEES = _event(
    "refugees", "难民", "Refugees", Age.II,
    "最弱文明 -3 文化并 -1 人口;最强文明 +3 文化并 +1 人口。",
)
TERRORISM = _event(
    "terrorism", "恐怖主义", "Terrorism", Age.II,
    "文化最少的文明摧毁其他每个文明的 1 个城市建筑。",
)

# 时代 III(15 张 Impact 系列, 终局计分)
IMPACT_OF_AGRICULTURE = _event(
    "impact_of_agriculture", "农业影响", "Impact of Agriculture", Age.III,
    "每个文明 +文化,等于其农场产出;若该产出超过消耗,再 +4 文化。",
)
IMPACT_OF_ARCHITECTURE = _event(
    "impact_of_architecture", "建筑影响", "Impact of Architecture", Age.III,
    "每个文明每级城市建筑 +文化。",
)
IMPACT_OF_BALANCE = _event(
    "impact_of_balance", "平衡影响", "Impact of Balance", Age.III,
    "每个文明 +文化,等于其产出最少项(科技/文化/食物/资源)的 2 倍。",
)
IMPACT_OF_COLONIES = _event(
    "impact_of_colonies", "殖民影响", "Impact of Colonies", Age.III,
    "每个文明每个殖民地 +3 文化。",
)
IMPACT_OF_COMPETITION = _event(
    "impact_of_competition", "竞争影响", "Impact of Competition", Age.III,
    "每个文明每级军事单位与竞技场 +文化。",
)
IMPACT_OF_GOVERNMENT = _event(
    "impact_of_government", "政体影响", "Impact of Government", Age.III,
    "每个文明每个内政行动 +2 文化,每个军事行动 +1 文化。",
)
IMPACT_OF_HAPPINESS = _event(
    "impact_of_happiness", "幸福影响", "Impact of Happiness", Age.III,
    "每个文明每个笑脸 +2 文化,每个怒脸 -2 文化。",
)
IMPACT_OF_INDUSTRY = _event(
    "impact_of_industry", "工业影响", "Impact of Industry", Age.III,
    "每个文明 +文化,等于其矿场资源产出。",
)
IMPACT_OF_POPULATION = _event(
    "impact_of_population", "人口影响", "Impact of Population", Age.III,
    "每个文明超过 10 的每个人口 +2 文化。",
)
IMPACT_OF_PROGRESS = _event(
    "impact_of_progress", "进步影响", "Impact of Progress", Age.III,
    "每个文明每级政体与特殊科技 +2 文化。",
)
IMPACT_OF_SCIENCE = _event(
    "impact_of_science", "科学影响", "Impact of Science", Age.III,
    "每个文明按科技排名 +文化:2 人局 10/0,3 人局 14/7/0,"
    "4 人局 15/10/5/0。",
)
IMPACT_OF_STRENGTH = _event(
    "impact_of_strength", "军力影响", "Impact of Strength", Age.III,
    "每个文明按军力排名 +文化:2 人局 10/0,3 人局 14/7/0,"
    "4 人局 15/10/5/0。",
)
IMPACT_OF_TECHNOLOGY = _event(
    "impact_of_technology", "科技影响", "Impact of Technology", Age.III,
    "每个文明每项 III 级科技 +4 文化。",
)
IMPACT_OF_VARIETY = _event(
    "impact_of_variety", "多样性影响", "Impact of Variety", Age.III,
    "每个文明每种类型的军事单位、城市建筑与特殊(蓝色)科技 +2 文化。",
)
IMPACT_OF_WONDERS = _event(
    "impact_of_wonders", "奇迹影响", "Impact of Wonders", Age.III,
    "每个文明按其奇迹 +文化:A 时代 5 分,I 时代 4 分,"
    "II 时代 3 分,III 时代 2 分。",
)

# --- 地区牌(PDF 第 4 页 Territory 行, 即时/永久效果) ------------------------------
# 永久效果中 yellow_token = 人口标记, blue_token = 资源标记
# (持有殖民地期间自配件盒取入己方银行, 失去殖民地须归还)。

DEVELOPED_TERRITORY_I = _territory(
    "developed_territory_i", "发达地区", "Developed Territory", Age.I,
    "即时:+3 科技。永久:1 人口标记、1 资源标记。",
    {"science": 3}, {"yellow_token": 1, "blue_token": 1},
)
HISTORIC_TERRITORY_I = _territory(
    "historic_territory_i", "历史地区", "Historic Territory", Age.I,
    "即时:+6 文化。永久:1 笑脸。",
    {"culture": 6}, {"happiness": 1},
)
INHABITED_TERRITORY_I = _territory(
    "inhabited_territory_i", "宜居地区", "Inhabited Territory", Age.I,
    "即时:+1 人口。永久:2 人口标记。",
    {"population": 1}, {"yellow_token": 2},
)
STRATEGIC_TERRITORY_I = _territory(
    "strategic_territory_i", "战略地区", "Strategic Territory", Age.I,
    "即时:+3 张军事牌。永久:2 军力。",
    {"military_card": 3}, {"strength": 2},
)
VAST_TERRITORY_I = _territory(
    "vast_territory_i", "广袤地区", "Vast Territory", Age.I,
    "即时:+3 食物。永久:3 人口标记、-1 资源标记。",
    {"food": 3}, {"yellow_token": 3, "blue_token": -1},
)
WEALTHY_TERRITORY_I = _territory(
    "wealthy_territory_i", "富饶地区", "Wealthy Territory", Age.I,
    "即时:+5 资源。永久:3 资源标记。",
    {"materials": 5}, {"blue_token": 3},
)
DEVELOPED_TERRITORY_II = _territory(
    "developed_territory_ii", "发达地区", "Developed Territory", Age.II,
    "即时:+5 科技。永久:2 人口标记、2 资源标记。",
    {"science": 5}, {"yellow_token": 2, "blue_token": 2},
)
HISTORIC_TERRITORY_II = _territory(
    "historic_territory_ii", "历史地区", "Historic Territory", Age.II,
    "即时:+11 文化。永久:2 笑脸。",
    {"culture": 11}, {"happiness": 2},
)
INHABITED_TERRITORY_II = _territory(
    "inhabited_territory_ii", "宜居地区", "Inhabited Territory", Age.II,
    "即时:+2 人口。永久:3 人口标记。",
    {"population": 2}, {"yellow_token": 3},
)
STRATEGIC_TERRITORY_II = _territory(
    "strategic_territory_ii", "战略地区", "Strategic Territory", Age.II,
    "即时:+5 张军事牌。永久:4 军力。",
    {"military_card": 5}, {"strength": 4},
)
VAST_TERRITORY_II = _territory(
    "vast_territory_ii", "广袤地区", "Vast Territory", Age.II,
    "即时:+4 食物。永久:4 人口标记、-1 资源标记。",
    {"food": 4}, {"yellow_token": 4, "blue_token": -1},
)
WEALTHY_TERRITORY_II = _territory(
    "wealthy_territory_ii", "富饶地区", "Wealthy Territory", Age.II,
    "即时:+9 资源。永久:4 资源标记。",
    {"materials": 9}, {"blue_token": 4},
)

MILITARY_CARDS = (
    # 奖励 3
    DEFENSE_COLONIZATION_I, DEFENSE_COLONIZATION_II, DEFENSE_COLONIZATION_III,
    # 侵略 11
    ENSLAVE_I, PLUNDER_I, RAID_I, ANNEX_II, INFILTRATE_II, PLUNDER_II,
    RAID_II, SPY_II, ARMED_INTERVENTION_III, PLUNDER_III, RAID_III,
    # 战争 3
    WAR_OVER_TECHNOLOGY_II, WAR_OVER_TERRITORY_II, WAR_OVER_CULTURE_III,
    # 条约 10
    OPEN_BORDERS_AGREEMENT, TRADE_ROUTES_AGREEMENT, ACCEPTANCE_OF_SUPREMACY,
    INTERNATIONAL_TRADE_AGREEMENT, PROMISE_OF_MILITARY_PROTECTION,
    SCIENTIFIC_COOPERATION, INTERNATIONAL_TOURISM, LOSS_OF_SOVEREIGNTY,
    MILITARY_ALLIANCE, PEACE_TREATY,
    # 阵型 15
    FIGHTING_BAND, HEAVY_CAVALRY, LEGION, MEDIEVAL_ARMY, PHALANX,
    CLASSIC_ARMY, CONQUISTADORS, DEFENSIVE_ARMY, FORTIFICATIONS,
    MOBILE_ARTILLERY, NAPOLEONIC_ARMY, ENTRENCHMENTS, MECHANIZED_ARMY,
    MODERN_ARMY, SHOCK_TROOPS,
    # 事件 A 10
    DEVELOPMENT_OF_AGRICULTURE, DEVELOPMENT_OF_CIVILIZATION,
    DEVELOPMENT_OF_CRAFTS, DEVELOPMENT_OF_MARKETS, DEVELOPMENT_OF_POLITICS,
    DEVELOPMENT_OF_RELIGION, DEVELOPMENT_OF_SCIENCE,
    DEVELOPMENT_OF_SETTLEMENT, DEVELOPMENT_OF_TRADE_ROUTE,
    DEVELOPMENT_OF_WARFARE,
    # 事件 I 15
    BARBARIANS, BORDER_CONFLICT, CRUSADES, CULTURAL_INFLUENCE, FORAY,
    GOOD_HARVEST, IMMIGRATION, NEW_DEPOSITS, PESTILENCE, RAIDERS, RATS,
    REBELLION, REIGN_OF_TERROR, SCIENTIFIC_BREAKTHROUGH_EVENT,
    UNCERTAIN_BORDERS,
    # 事件 II 15
    CIVIL_UNREST, COLD_WAR, CRIME_WAVE, ECONOMIC_PROGRESS, EMIGRATION,
    ICONOCLASM, INDEPENDENCE_DECLARATION, INTERNATIONAL_AGREEMENT,
    NATIONAL_PRIDE, POLITICS_OF_STRENGTH, POPULARIZATION_OF_SCIENCE,
    PROSPERITY, RAVAGES_OF_TIME, REFUGEES, TERRORISM,
    # 事件 III 15
    IMPACT_OF_AGRICULTURE, IMPACT_OF_ARCHITECTURE, IMPACT_OF_BALANCE,
    IMPACT_OF_COLONIES, IMPACT_OF_COMPETITION, IMPACT_OF_GOVERNMENT,
    IMPACT_OF_HAPPINESS, IMPACT_OF_INDUSTRY, IMPACT_OF_POPULATION,
    IMPACT_OF_PROGRESS, IMPACT_OF_SCIENCE, IMPACT_OF_STRENGTH,
    IMPACT_OF_TECHNOLOGY, IMPACT_OF_VARIETY, IMPACT_OF_WONDERS,
    # 地区 12
    DEVELOPED_TERRITORY_I, HISTORIC_TERRITORY_I, INHABITED_TERRITORY_I,
    STRATEGIC_TERRITORY_I, VAST_TERRITORY_I, WEALTHY_TERRITORY_I,
    DEVELOPED_TERRITORY_II, HISTORIC_TERRITORY_II, INHABITED_TERRITORY_II,
    STRATEGIC_TERRITORY_II, VAST_TERRITORY_II, WEALTHY_TERRITORY_II,
)
