"""事件卡结算注册表与 Age A/I/II/III 事件处理器(P2-T5/T6/T11/T12).

EVENT_HANDLERS: handler 名 -> (state, db) -> state。揭示流程见
politics.seed_event; 任何时代的事件未注册 handler 均 fail-loud
(ValueError, 缺失即实现缺陷)。

需要玩家决策的事件压入 pending 链: 从 current_player 起顺时针每座位一个
PendingEffect(responder=座位), 逐个结算 pop; 增益类选择(可
DeclineResponse 放弃)见 DECLINABLE_EVENT_KINDS, 强制失去类(raiders/
border_conflict 等)不可放弃(压入前保证恒有可执行选项, 防卡死)。
决策动作为 ChooseEventOption(见 apply_event_choice)或事件免费建造的
Build(见 EVENT_FREE_BUILD)。时代 III 15 张 Impact 事件全为自动计分类,
不压 pending(揭示即结算; 未揭示者于终局结算, 见 endgame_scoring)。

强弱比较口径(规则书 p7):
- "最强/最弱文明"按 civ 军力(civ_values.strength); barbarians 的"文化
  领先者"按文化分存量(p.culture), immigration 按笑脸(civ 幸福);
- 平局按当前玩家顺时针近者优先(同一事件同时引用最强与最弱且全场平局时,
  同一文明可同为两者, 如 crusades 该文明 +4 再 -4);
- 2 人局"两个最X"理解为"一个最X";
- immigration 为"所有笑脸最多的文明"(PDF 原文 Civilization(s)), 平局的
  全部生效(规则书 p7: 提到"所有…最多/最少"时平局保持平局)。

时代 I 事件的 PDF 图标口径(卡牌数值表 v1.09 第 4 页, 以 PDF 文本为准):
- 竖琴 = 文化, 灯泡 = 科技, 棋子 = 人口(黄点), 黄球 = 黄点银行标记;
- barbarians / pestilence / reign_of_terror 均为失去人口(棋子图标):
  优先空闲工人池, 不足时按 (类别, card_id) 字典序从有工人的卡上移除
  (SIMPLIFICATION, 官方为玩家自选), 失去的黄点回到黄点银行。

时代 II 事件的 PDF 口径(同上, 与卡牌转录的差异以 PDF 为准):
- civil_unrest 的"不快乐工人"= civ.discontent(黄点轨道幸福需求 - 笑脸);
  "最多"为所有平局者(规则书 p7); -1 蓝点取储存中 (token_value, card_id)
  升序第 1 个回供给区(SIMPLIFICATION 确定性口径);
- economic_progress "do not ignore consumption & corruption": 按回合生产
  阶段次序(腐败 -> 食物生产 -> 消耗 -> 资源生产), 不含计分与起义检定;
- ravages_of_time 翻面奇迹建模为 PlayerState.wonders_facedown: 留在场上
  (wonders 不变)但效果失效, 每个转为 +2 文化增速(见 civ.civ_values);
- politics_of_strength 的"最终时代"按 state.age in (III, IV) 判定; 终局
  ±文化分值 PDF 未给, 按同数值直译(最强 +5 / 最弱 -3, 见任务报告存疑);
- international_agreement 拿牌白点费自付(从现有白点扣), 预算 5;
  "跳过下一次政治行动"建模为 PlayerState.miss_political_action(其下一
  个 POLITICS 相位仅剩 SkipPolitics); 结束后补满卡牌列(SIMPLIFICATION:
  不触发时代结束处理)。
"""

from collections.abc import Callable
from dataclasses import replace

from tta.engine import economy, effects, military
from tta.engine.civ import civ_values, discontent, hand_limit_civil
from tta.engine.constants import FOOD_SHORTAGE_CULTURE_PENALTY, ROW_COSTS
from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    WORKER_CATEGORIES,
    Age,
    CardCategory,
)
from tta.engine.model import CardDB
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
    acting_index,
    active_indices,
    replace_player,
    workers_total,
)
from tta.engine.tracks import consumption_value, corruption_value

KIND_EVENT_MARKETS = "event_markets"
"""development_of_markets 选择 pending: responder 选 food/resource +2."""

KIND_EVENT_RELIGION = "event_religion"
"""development_of_religion 免费建造 pending: responder 可免费建 religion."""

KIND_EVENT_WARFARE = "event_warfare"
"""development_of_warfare 免费建造 pending: responder 可免费建 warriors."""

KIND_EVENT_CIVILIZATION = "event_civilization"
"""development_of_civilization 选择 pending: responder 三选一(官方口径:
人口/建造/研发; 建造在引擎中拆为 farm_mine 与 urban 两个 option, 见
CIVILIZATION_OPTION_PENDING 与 CIVILIZATION_OPTION_POPULATION)或
DeclineResponse."""

KIND_EVENT_DESTROY_BUILDING = "event_destroy_building"
"""border_conflict 失去建筑 pending: responder(最弱文明)选 1 张有工人的
城市建筑/农场/矿场卡, 移除 1 工人回空闲池(强制, 不可放弃)。"""

KIND_EVENT_FORAY = "event_foray"
"""foray 生产选择 pending: responder 选食物/资源组合(按价值共 3, 见
FORAY_OPTIONS), 可 DeclineResponse 放弃。"""

KIND_EVENT_RAIDERS = "event_raiders"
"""raiders 失去选择 pending: responder 选食物/资源组合(按价值共 2, 见
RAIDERS_OPTIONS), 不足部分损失到此为止(强制, 不可放弃)。"""

KIND_EVENT_DESTROY_URBAN = "event_destroy_urban"
"""terrorism 摧毁城市建筑 pending: responder(受害者)选 1 张有工人的城市
建筑卡, 移除 1 工人回空闲池(强制, 不可放弃; 失去口径同 border_conflict)。"""

KIND_EVENT_LOSE_COLONY = "event_lose_colony"
"""independence_declaration 失去殖民地 pending: responder(最弱文明)选
1 个殖民地失去(强制, 不可放弃); 永久黄/蓝标记归还(下限 0), 地区牌入
past_events。"""

KIND_EVENT_RAVAGES = "event_ravages"
"""ravages_of_time 翻面奇迹 pending: responder 选 1 个 A/I 时代已完成奇迹
翻面(强制, 不可放弃); 翻面入 wonders_facedown(效果失效, 转 +2 文化增速)。"""

KIND_EVENT_AGREEMENT = "event_agreement"
"""international_agreement 拿牌 pending: responder(最强文明)在预算
(context["budget"])内逐个拿卡牌列的牌(option 为槽位号字符串), 或
AGREEMENT_DONE 结束; 结束后补满卡牌列(见 _replenish_card_row)。"""

EVENT_FREE_BUILD: dict[str, str] = {
    KIND_EVENT_RELIGION: "religion",
    KIND_EVENT_WARFARE: "warriors",
}
"""事件免费建造 pending kind -> 可免费放置 1 工人的卡 id(0 行动点 0 费用)."""

DECLINABLE_EVENT_KINDS: frozenset[str] = frozenset({
    KIND_EVENT_MARKETS,
    KIND_EVENT_RELIGION,
    KIND_EVENT_WARFARE,
    KIND_EVENT_CIVILIZATION,
    KIND_EVENT_FORAY,
})
"""事件选择类 pending kind(增益类非强制选择, 可 DeclineResponse).

强制失去类(KIND_EVENT_DESTROY_BUILDING / KIND_EVENT_RAIDERS)不在名单:
压入前已保证恒有可执行选项(destroy 仅当有建筑可失; raiders 的
settle_loss 不足时损失到此为止, 不抛错), 不会卡死。"""

FORAY_OPTIONS: tuple[str, ...] = (
    "food:3", "food:2,resource:1", "food:1,resource:2", "resource:3",
)
"""foray 合法 option: 食物/资源组合, 按价值合计 3。"""

RAIDERS_OPTIONS: tuple[str, ...] = (
    "food:2", "food:1,resource:1", "resource:2",
)
"""raiders 合法 option: 食物/资源组合, 按价值合计 2。"""

DESTROY_BUILDING_CATEGORIES: frozenset[CardCategory] = (
    URBAN_CATEGORIES | frozenset({CardCategory.FARM, CardCategory.MINE})
)
"""border_conflict 可失去的建筑类别(城市建筑/农场/矿场, 不含兵种)。"""

REBELLION_CIVIL_LOSS = 2
"""rebellion 每名玩家下一回合失去的白点数。"""

DECLINABLE_PENDING_KINDS: frozenset[str] = (
    effects.DECLINABLE_PENDING_KINDS | DECLINABLE_EVENT_KINDS
)
"""可放弃 pending kind 全量白名单(行动卡子行动类 ∪ 事件选择类)."""

CIVILIZATION_OPTION_POPULATION = "population"
"""development_of_civilization 人口选项(官方选项 ①): +1 人口并付 1 食物."""

CIVILIZATION_POPULATION_FOOD_COST = 1
"""人口选项的食物费(事件固定价 1 食物, 非轨道人口费, moses 折扣不适用)."""

CIVILIZATION_OPTION_PENDING: dict[str, tuple[str, int]] = {
    "farm_mine": (effects.KIND_BUILD_FARM_MINE, 1),
    "urban": (effects.KIND_BUILD_URBAN, 1),
    "tech": (effects.KIND_DEVELOP_TECH, 1),
}
"""development_of_civilization 折扣选项 -> (子 pending kind, 折扣).

SIMPLIFICATION(brief 口径): "-1 食物建农场/矿场"与"-1 资源建城市建筑"
统一实现为建造折扣 1(引擎支付以资源计); "-1 科技研发科技"实现为
develop_tech pending 的科技费折扣 1。人口选项(①)无子 pending, 选择即
结算, 不在本表(见 CIVILIZATION_OPTION_POPULATION)。
"""

EVENT_HANDLERS: dict[str, Callable[[GameState, CardDB], GameState]] = {}
"""事件结算处理器注册表: handler 名 -> (state, db) -> 新 state."""

MARKETS_GAIN = 2
"""development_of_markets 每名玩家所得(食物或资源)."""

POLITICS_DRAW = 3
"""development_of_politics 每名玩家抓军事牌数."""


def resolve_event(state: GameState, db: CardDB, card_id: str) -> GameState:
    """揭示事件的统一入口: 查 EVENT_HANDLERS 结算.

    fail-loud: 任何时代的事件未注册 handler -> ValueError(T6/T11/T12 拥有
    全量事件, 缺失即实现缺陷)。
    """
    card = db.get(card_id)
    handler = EVENT_HANDLERS.get(card.handler)
    if handler is None:
        msg = f"事件 {card_id!r} 未注册 EVENT_HANDLERS handler"
        raise ValueError(msg)
    return handler(state, db)


def apply_event_choice(
    db: CardDB, state: GameState, option: str,
) -> GameState:
    """ChooseEventOption 结算: pop pending[0] 并按 kind 分派(合法性由 legal 保证)."""
    if not state.pending:  # pragma: no cover - legal 已排除
        msg = "无待决策的事件 pending"
        raise ValueError(msg)
    pending = state.pending[0]
    idx = acting_index(state)
    state = replace(state, pending=state.pending[1:])
    if pending.kind == KIND_EVENT_MARKETS:
        p = economy.gain_tokens(db, state.players[idx], option, MARKETS_GAIN)
        return replace_player(state, idx, p)
    if pending.kind == KIND_EVENT_CIVILIZATION:
        if option == CIVILIZATION_OPTION_POPULATION:
            # 官方选项 ①: +1 人口并付 1 食物(事件固定价, moses 折扣不适用)
            p = state.players[idx]
            p = replace(p, yellow_bank=p.yellow_bank - 1,
                        worker_pool=p.worker_pool + 1)
            p = economy.pay(db, p, "food", CIVILIZATION_POPULATION_FOOD_COST)
            return replace_player(state, idx, p)
        spec = CIVILIZATION_OPTION_PENDING.get(option)
        if spec is None:  # pragma: no cover - legal 已排除
            msg = f"事件 {pending.kind!r} 无选项 {option!r}"
            raise ValueError(msg)
        kind, discount = spec
        sub = PendingEffect(kind, discount, responder=idx)
        return replace(state, pending=(sub,) + state.pending)
    if pending.kind == KIND_EVENT_DESTROY_BUILDING:
        # border_conflict: 移除所选建筑卡上 1 工人, 回空闲池
        p = state.players[idx]
        return replace_player(state, idx, _remove_building_worker(db, p, option))
    if pending.kind == KIND_EVENT_DESTROY_URBAN:
        # terrorism: 摧毁所选城市建筑(同 border_conflict 失去口径)
        p = state.players[idx]
        return replace_player(state, idx, _remove_building_worker(db, p, option))
    if pending.kind == KIND_EVENT_LOSE_COLONY:
        # independence_declaration: 失去所选殖民地; 永久黄/蓝标记归还
        # (下限 0, 与 annex 受害者侧同口径), 地区牌入 past_events
        p = state.players[idx]
        colonies = list(p.colonies)
        colonies.remove(option)
        permanent = db.get(option).territory_permanent
        p = replace(
            p, colonies=tuple(colonies),
            yellow_bank=max(0, p.yellow_bank - permanent.get("yellow_token", 0)),
            blue_bank=max(0, p.blue_bank - permanent.get("blue_token", 0)))
        state = replace_player(state, idx, p)
        return replace(state, past_events=state.past_events + (option,))
    if pending.kind == KIND_EVENT_RAVAGES:
        # ravages_of_time: 所选 A/I 奇迹翻面(效果失效, 转 +2 文化增速)
        p = state.players[idx]
        return replace_player(
            state, idx,
            replace(p, wonders_facedown=p.wonders_facedown + (option,)))
    if pending.kind == KIND_EVENT_AGREEMENT:
        return _agreement_choice(db, state, pending, idx, option)
    if pending.kind == KIND_EVENT_FORAY:
        # foray: 按所选组合生产(按价值, 见 economy.gain_value)
        p = state.players[idx]
        for kind, amount in parse_mix(option):
            p = economy.gain_value(db, p, kind, amount)
        return replace_player(state, idx, p)
    if pending.kind == KIND_EVENT_RAIDERS:
        # raiders: 按所选组合失去(不足部分损失到此为止)
        p = state.players[idx]
        for kind, amount in parse_mix(option):
            p, _ = economy.settle_loss(db, p, kind, amount)
        return replace_player(state, idx, p)
    msg = f"pending {pending.kind!r} 不接受 ChooseEventOption"  # pragma: no cover
    raise ValueError(msg)  # pragma: no cover


def parse_mix(option: str) -> tuple[tuple[str, int], ...]:
    """解析 "food:2,resource:1" 形式的组合 option 为 ((kind, 数量), ...)."""
    parts: list[tuple[str, int]] = []
    for chunk in option.split(","):
        kind, _, count = chunk.partition(":")
        parts.append((kind, int(count)))
    return tuple(parts)


# --- pending 链辅助 ----------------------------------------------------------


def _seat_order(state: GameState) -> list[int]:
    """从 current_player 起顺时针的座位序(不含已体面退出者)."""
    n = len(state.players)
    return [
        (state.current_player + i) % n for i in range(n)
        if not state.players[(state.current_player + i) % n].resigned
    ]


def _push_chain(state: GameState, kind: str, seats: list[int]) -> GameState:
    """按座位序压一串同 kind pending(responder=座位), 逐个结算 pop."""
    chain = tuple(PendingEffect(kind, 0, responder=seat) for seat in seats)
    return replace(state, pending=state.pending + chain)


def _placed_count(p: PlayerState, card_id: str) -> int:
    return sum(slots.get(card_id, 0) for slots in p.buildings.values())


def _free_build_eligible(p: PlayerState, card_id: str) -> bool:
    """事件免费建造资格: 有可用工人且该卡有空槽."""
    return (
        p.worker_pool >= 1
        and _placed_count(p, card_id) < p.developed.count(card_id)
    )


def _push_free_build_chain(state: GameState, kind: str, card_id: str) -> GameState:
    seats = [
        seat for seat in _seat_order(state)
        if _free_build_eligible(state.players[seat], card_id)
    ]
    return _push_chain(state, kind, seats)


# --- Age A 事件 handler(卡牌数值表 p4 文本) --------------------------------------


def _gain_tokens_all(
    db: CardDB, state: GameState, kind: str, count: int,
) -> GameState:
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, economy.gain_tokens(db, p, kind, count))
    return state


def _development_of_agriculture(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 食物."""
    return _gain_tokens_all(db, state, "food", 2)


def _development_of_civilization(state: GameState, db: CardDB) -> GameState:
    """每名玩家三选一(官方口径): +1 人口付 1 食物 | -1 建造 | -1 研发."""
    return _push_chain(state, KIND_EVENT_CIVILIZATION, _seat_order(state))


def _development_of_crafts(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 资源."""
    return _gain_tokens_all(db, state, "resource", 2)


def _development_of_markets(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 食物或 +2 资源(玩家各自选, pending 链)."""
    return _push_chain(state, KIND_EVENT_MARKETS, _seat_order(state))


def _development_of_politics(state: GameState, db: CardDB) -> GameState:
    """每名玩家 +3 张军事牌(从 current_player 起顺时针, 共享军事牌堆)."""
    for seat in _seat_order(state):
        state = military.draw_military(state, seat, POLITICS_DRAW)
    return state


def _development_of_religion(state: GameState, db: CardDB) -> GameState:
    """有可用工人的玩家可免费建 1 宗教(pending 链, 可放弃)."""
    return _push_free_build_chain(state, KIND_EVENT_RELIGION, "religion")


def _development_of_science(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 科技."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, replace(p, science=p.science + 2))
    return state


def _development_of_settlement(state: GameState, db: CardDB) -> GameState:
    """每个文明免费 +1 人口(yellow_bank > 0 才生效; 不付食物费)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        if p.yellow_bank > 0:
            state = replace_player(state, i, replace(
                p, yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1))
    return state


def _development_of_trade_route(state: GameState, db: CardDB) -> GameState:
    """每个文明 +1 科技、+1 食物、+1 资源."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        p = replace(p, science=p.science + 1)
        p = economy.gain_tokens(db, p, "food", 1)
        p = economy.gain_tokens(db, p, "resource", 1)
        state = replace_player(state, i, p)
    return state


def _development_of_warfare(state: GameState, db: CardDB) -> GameState:
    """有可用工人的玩家可免费建 1 战士(pending 链, 可放弃)."""
    return _push_free_build_chain(state, KIND_EVENT_WARFARE, "warriors")


EVENT_HANDLERS.update({
    "development_of_agriculture": _development_of_agriculture,
    "development_of_civilization": _development_of_civilization,
    "development_of_crafts": _development_of_crafts,
    "development_of_markets": _development_of_markets,
    "development_of_politics": _development_of_politics,
    "development_of_religion": _development_of_religion,
    "development_of_science": _development_of_science,
    "development_of_settlement": _development_of_settlement,
    "development_of_trade_route": _development_of_trade_route,
    "development_of_warfare": _development_of_warfare,
})


# --- 强弱比较辅助(规则书 p7) ------------------------------------------------------


def _clockwise_distance(state: GameState, seat: int) -> int:
    """座位距 current_player 的顺时针距离(0 = 当前玩家)."""
    return (seat - state.current_player) % len(state.players)


def _extreme_seats(
    state: GameState, values: list[int], *, strongest: bool, count: int = 1,
) -> list[int]:
    """按 values 取最值前 count 个座位; 平局按当前玩家顺时针近者优先.

    返回按"最值程度"排序的座位列表(同一事件同时引用最强与最弱且全场平局
    时, 两侧可判给同一座位 — 规则书 p7 平局口径的字面结果)。
    已体面退出者(resigned)不参与比较(规则书 p4: 其文明移出游戏)。
    """
    seats = active_indices(state)

    def key(seat: int) -> tuple[int, int]:
        primary = -values[seat] if strongest else values[seat]
        return (primary, _clockwise_distance(state, seat))

    return sorted(seats, key=key)[:count]


def _most_count(state: GameState) -> int:
    """"两个最X"的数量: 2 人局理解为"一个最X"(规则书 p7), 否则 2.

    按在局(未退出)人数计(规则书 p4: 只剩 2 位玩家时按 2 人规则结算事件)。
    """
    return 1 if len(active_indices(state)) == 2 else 2


def _strengths(db: CardDB, state: GameState) -> list[int]:
    """各玩家 civ 军力(最强/最弱文明的比较口径; 含条约静态加成)."""
    return [
        civ_values(db, p, state.players, i).strength
        for i, p in enumerate(state.players)
    ]


def _weakest_seats(db: CardDB, state: GameState) -> list[int]:
    """"两个最弱文明"座位(2 人局 1 个), 按军力升序 + 顺时针平局口径."""
    return _extreme_seats(
        state, _strengths(db, state), strongest=False,
        count=_most_count(state))


def _strongest_seats(db: CardDB, state: GameState) -> list[int]:
    """"两个最强文明"座位(2 人局 1 个), 按军力降序 + 顺时针平局口径."""
    return _extreme_seats(
        state, _strengths(db, state), strongest=True,
        count=_most_count(state))


def _clockwise_sorted(state: GameState, seats: list[int]) -> list[int]:
    """座位集按从 current_player 起顺时针排序(多人决策的依次结算序)."""
    return sorted(seats, key=lambda seat: _clockwise_distance(state, seat))


def lose_population(p: PlayerState, count: int) -> PlayerState:
    """失去人口: 优先空闲工人池, 不足按 (类别, card_id) 字典序从卡上移除.

    失去的黄点回到黄点银行(官方规则, 如 emigration 注记 return to yellow
    bank)。SIMPLIFICATION: 池空时官方为玩家自选, 引擎按字典序确定选取。
    """
    from_pool = min(count, p.worker_pool)
    remaining = count - from_pool
    buildings = {cat: dict(slots) for cat, slots in p.buildings.items()}
    taken = 0
    for cat in sorted(buildings):
        for card_id in sorted(buildings[cat]):
            if remaining == 0:
                break
            take = min(remaining, buildings[cat][card_id])
            if take == 0:
                continue
            left = buildings[cat][card_id] - take
            if left > 0:
                buildings[cat][card_id] = left
            else:
                del buildings[cat][card_id]
            remaining -= take
            taken += take
    return replace(
        p,
        worker_pool=p.worker_pool - from_pool,
        yellow_bank=p.yellow_bank + from_pool + taken,
        buildings=buildings,
    )


def destroyable_building_ids(p: PlayerState) -> list[str]:
    """border_conflict 可失去的建筑卡 id(有工人的城市建筑/农场/矿场)."""
    ids: list[str] = []
    for cat_value, slots in sorted(p.buildings.items()):
        if CardCategory(cat_value) not in DESTROY_BUILDING_CATEGORIES:
            continue
        ids.extend(card_id for card_id, n in sorted(slots.items()) if n > 0)
    return ids


def urban_destroyable_ids(p: PlayerState) -> list[str]:
    """terrorism 可摧毁的城市建筑卡 id(有工人的城市建筑, 类别字典序)."""
    ids: list[str] = []
    for category in sorted(URBAN_CATEGORIES, key=lambda c: c.value):
        ids.extend(
            card_id
            for card_id, n in sorted(p.buildings.get(category.value, {}).items())
            if n > 0
        )
    return ids


def _remove_building_worker(
    db: CardDB, p: PlayerState, card_id: str,
) -> PlayerState:
    """失去建筑/摧毁城市建筑共用: 所选卡 -1 工人回空闲池."""
    card = db.get(card_id)
    buildings = dict(p.buildings)
    slots = dict(buildings[card.category.value])
    left = slots[card_id] - 1
    if left > 0:
        slots[card_id] = left
    else:
        del slots[card_id]
    buildings[card.category.value] = slots
    return replace(p, buildings=buildings, worker_pool=p.worker_pool + 1)


# --- 时代 I 事件 handler(卡牌数值表 p4 Events 表 Age I 行) ---------------------------


def _barbarians(state: GameState, db: CardDB) -> GameState:
    """文化领先者(文化分最多)若为两个最弱文明之一, 失去 1 人口."""
    cultures = [p.culture for p in state.players]
    leader = _extreme_seats(state, cultures, strongest=True)[0]
    if leader in _weakest_seats(db, state):
        state = replace_player(
            state, leader, lose_population(state.players[leader], 1))
    return state


def _border_conflict(state: GameState, db: CardDB) -> GameState:
    """最弱失去 1 城市建筑/农场/矿场(该玩家选择, 强制 pending); 最强产 3 资源."""
    weakest = _weakest_seats(db, state)[0]
    strongest = _strongest_seats(db, state)[0]
    p = state.players[strongest]
    state = replace_player(
        state, strongest, economy.gain_value(db, p, "resource", 3))
    if destroyable_building_ids(state.players[weakest]):
        state = _push_chain(state, KIND_EVENT_DESTROY_BUILDING, [weakest])
    return state


def _crusades(state: GameState, db: CardDB) -> GameState:
    """最强 +4 文化; 最弱 -4 文化(下限 0, 同 turn 食物短缺的文化扣减口径)."""
    strongest = _strongest_seats(db, state)[0]
    weakest = _weakest_seats(db, state)[0]
    p = state.players[strongest]
    state = replace_player(state, strongest, replace(p, culture=p.culture + 4))
    p = state.players[weakest]
    return replace_player(
        state, weakest, replace(p, culture=max(0, p.culture - 4)))


def _cultural_influence(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化, 等于其文化增速."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        rate = civ_values(db, p, state.players, i).culture_rate
        if rate:
            state = replace_player(state, i, replace(p, culture=p.culture + rate))
    return state


def _foray(state: GameState, db: CardDB) -> GameState:
    """两个最强文明各产共 3 食物/资源(各自选组合, 顺时针依次, 可放弃)."""
    seats = _clockwise_sorted(state, _strongest_seats(db, state))
    return _push_chain(state, KIND_EVENT_FORAY, seats)


def _good_harvest(state: GameState, db: CardDB) -> GameState:
    """每名玩家农场立即生产(事件即时结算, 天然无消耗与腐败)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, economy.produce(db, p, "food"))
    return state


def _immigration(state: GameState, db: CardDB) -> GameState:
    """笑脸最多的所有文明(平局全部)免费 +1 人口(黄点银行非空才生效).

    已体面退出者(resigned)不参与比较与生效(规则书 p4: 其文明移出游戏),
    与其他全员事件口径一致。
    """
    happiness = [
        civ_values(db, p, state.players, i).happiness
        for i, p in enumerate(state.players)
    ]
    active = active_indices(state)
    best = max(happiness[i] for i in active)
    for i in active:
        p = state.players[i]
        if happiness[i] == best and p.yellow_bank > 0:
            state = replace_player(state, i, replace(
                p, yellow_bank=p.yellow_bank - 1,
                worker_pool=p.worker_pool + 1))
    return state


def _new_deposits(state: GameState, db: CardDB) -> GameState:
    """每名玩家矿场立即生产(忽略腐败)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, economy.produce(db, p, "resource"))
    return state


def _pestilence(state: GameState, db: CardDB) -> GameState:
    """每个文明 -1 人口."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        state = replace_player(state, i, lose_population(p, 1))
    return state


def _raiders(state: GameState, db: CardDB) -> GameState:
    """两个最弱文明各失去共 2 食物/资源(各自选组合, 强制; 全无则不压)."""
    seats = [
        seat for seat in _clockwise_sorted(state, _weakest_seats(db, state))
        if (economy.food_total(db, state.players[seat])
            + economy.resource_total(db, state.players[seat])) > 0
    ]
    return _push_chain(state, KIND_EVENT_RAIDERS, seats)


def _rats(state: GameState, db: CardDB) -> GameState:
    """每个文明失去所有储存的食物(农场卡上蓝点全清回供给区)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        farm_tokens = sum(
            n for card_id, n in p.card_tokens.items()
            if n > 0 and db.get(card_id).category is CardCategory.FARM
        )
        if not farm_tokens:
            continue
        tokens = {
            card_id: n for card_id, n in p.card_tokens.items()
            if db.get(card_id).category is not CardCategory.FARM
        }
        state = replace_player(state, i, replace(
            p, card_tokens=tokens, blue_bank=p.blue_bank + farm_tokens))
    return state


def _rebellion(state: GameState, db: CardDB) -> GameState:
    """每名玩家下一回合 -2 白点.

    行动点在每回合末恢复(为下一回合预算): 当前玩家的下一次恢复尚未发生,
    挂 civil_action_debt 于恢复时生效(见 turn.end_of_turn); 他玩家的下
    回合行动点已于其上一回合末恢复完毕, 立即 -2(下限 0)。
    """
    idx = state.current_player
    players: list[PlayerState] = []
    for i, p in enumerate(state.players):
        if p.resigned:
            players.append(p)
            continue
        if i == idx:
            p = replace(
                p, civil_action_debt=p.civil_action_debt + REBELLION_CIVIL_LOSS)
        else:
            p = replace(p, civil_actions=max(
                0, p.civil_actions - REBELLION_CIVIL_LOSS))
        players.append(p)
    return replace(state, players=tuple(players))


def _reign_of_terror(state: GameState, db: CardDB) -> GameState:
    """最弱文明 -1 人口."""
    weakest = _weakest_seats(db, state)[0]
    return replace_player(
        state, weakest, lose_population(state.players[weakest], 1))


def _scientific_breakthrough(state: GameState, db: CardDB) -> GameState:
    """每个文明 +科技, 等于其科技增速."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        rate = civ_values(db, p, state.players, i).science_rate
        if rate:
            state = replace_player(state, i, replace(p, science=p.science + rate))
    return state


def _uncertain_borders(state: GameState, db: CardDB) -> GameState:
    """最弱文明从黄点银行给最强文明 1 黄点(银行空或同一文明则无效果)."""
    weakest = _weakest_seats(db, state)[0]
    strongest = _strongest_seats(db, state)[0]
    if weakest == strongest or state.players[weakest].yellow_bank == 0:
        return state
    p_from = replace(
        state.players[weakest],
        yellow_bank=state.players[weakest].yellow_bank - 1)
    state = replace_player(state, weakest, p_from)
    p_to = replace(
        state.players[strongest],
        yellow_bank=state.players[strongest].yellow_bank + 1)
    return replace_player(state, strongest, p_to)


EVENT_HANDLERS.update({
    "barbarians": _barbarians,
    "border_conflict": _border_conflict,
    "crusades": _crusades,
    "cultural_influence": _cultural_influence,
    "foray": _foray,
    "good_harvest": _good_harvest,
    "immigration": _immigration,
    "new_deposits": _new_deposits,
    "pestilence": _pestilence,
    "raiders": _raiders,
    "rats": _rats,
    "rebellion": _rebellion,
    "reign_of_terror": _reign_of_terror,
    "scientific_breakthrough": _scientific_breakthrough,
    "uncertain_borders": _uncertain_borders,
})


# --- 时代 II 事件 handler(卡牌数值表 p4 Events 表 Age II 行) ---------------------------

CIVIL_UNREST_CULTURE_PER_WORKER = 4
"""civil_unrest 每个不快乐工人失去的文化."""

COLD_WAR_SCIENCE = 6
"""cold_war 两个最强文明各自获得的科技."""

CRIME_WAVE_CULTURE = 3
CRIME_WAVE_SCIENCE = 1
"""crime_wave 两个最弱文明各自失去的文化/科技(下限 0)."""

NATIONAL_PRIDE_CULTURE = 5
"""national_pride 文化分最多的文明获得的文化."""

POLITICS_OF_STRENGTH_DRAW = 5
"""politics_of_strength 最强文明抓军事牌数(终局改为 +5 文化)."""

POLITICS_OF_STRENGTH_DISCARD = 3
"""politics_of_strength 最弱文明弃军事牌数(终局改为 -3 文化)."""

PROSPERITY_MAX_POPULATION = 8
"""prosperity 人口收益上限(PDF: 每个笑脸 +1 人口, max 8)."""

REFUGEES_CULTURE = 3
"""refugees 最强/最弱文明的文化增减(另 ±1 人口)."""

AGREEMENT_BUDGET = 5
"""international_agreement 拿牌白点预算(PDF: up to 5 civil actions)."""

AGREEMENT_DONE = "done"
"""international_agreement 结束拿牌 option(预算内拿牌为"可", 非强制)."""

_AGREEMENT_NO_DUPLICATE = (
    WORKER_CATEGORIES
    | frozenset({CardCategory.SPECIAL, CardCategory.GOVERNMENT})
)
"""international_agreement 拿牌查重类别(与 legal._take_card_legal 同口径)."""

_FINAL_AGES = (Age.III, Age.IV)
"""politics_of_strength "最终时代"判定(state.age 处于 III/IV)."""

_RAVAGES_WONDER_AGES = (Age.A, Age.I)
"""ravages_of_time 可翻面的奇迹时代."""


def _civil_unrest(state: GameState, db: CardDB) -> GameState:
    """每个文明每个不快乐工人 -4 文化; 不快乐工人最多的所有文明各 -1 蓝点;
    全场无不快乐工人则无效果.

    不快乐工人 = civ.discontent(黄点轨道幸福需求 - 当前笑脸); "最多"平局
    全部生效(规则书 p7 "所有…最多"口径, 同 immigration)。
    """
    active = active_indices(state)
    unhappy = {
        i: discontent(db, state.players[i], state.players, i) for i in active
    }
    most = max(unhappy.values(), default=0)
    if most == 0:
        return state
    for i in active:
        p = state.players[i]
        loss = CIVIL_UNREST_CULTURE_PER_WORKER * unhappy[i]
        if loss:
            p = replace(p, culture=max(0, p.culture - loss))
        if unhappy[i] == most:
            p = _lose_blue_token(db, p)
        state = replace_player(state, i, p)
    return state


def _lose_blue_token(db: CardDB, p: PlayerState) -> PlayerState:
    """失去 1 个储存的蓝点回供给区: (token_value, card_id) 升序取第 1 个
    (SIMPLIFICATION 确定性口径); 卡上无蓝点则无损失."""
    candidates = [
        (db.get(card_id).token_value, card_id)
        for card_id, n in p.card_tokens.items()
        if n > 0
    ]
    if not candidates:
        return p
    _, card_id = min(candidates)
    tokens = dict(p.card_tokens)
    left = tokens[card_id] - 1
    if left > 0:
        tokens[card_id] = left
    else:
        del tokens[card_id]
    return replace(p, card_tokens=tokens, blue_bank=p.blue_bank + 1)


def _cold_war(state: GameState, db: CardDB) -> GameState:
    """两个最强文明各 +6 科技."""
    for seat in _strongest_seats(db, state):
        p = state.players[seat]
        state = replace_player(
            state, seat, replace(p, science=p.science + COLD_WAR_SCIENCE))
    return state


def _crime_wave(state: GameState, db: CardDB) -> GameState:
    """两个最弱文明各 -3 文化与 -1 科技(下限 0)."""
    for seat in _weakest_seats(db, state):
        p = state.players[seat]
        state = replace_player(state, seat, replace(
            p,
            culture=max(0, p.culture - CRIME_WAVE_CULTURE),
            science=max(0, p.science - CRIME_WAVE_SCIENCE)))
    return state


def _economic_progress(state: GameState, db: CardDB) -> GameState:
    """每名玩家矿场与农场立即生产; 不忽略消耗与腐败.

    按回合生产阶段次序(腐败 -> 食物生产 -> 消耗 -> 资源生产, 见
    turn._production), 不含计分与起义检定(事件即时结算, 与 good_harvest
    同口径)。
    """
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        # 腐败: 资源支付, 不足用食物补, 仍不足损失到此为止
        amount = corruption_value(p.blue_bank)
        if amount > 0:
            p, paid = economy.settle_loss(db, p, "resource", amount)
            p, _ = economy.settle_loss(db, p, "food", amount - paid)
        # 食物生产 -> 食物消耗(每缺 1 -4 文化, 下限 0)
        p = economy.produce(db, p, "food")
        need = consumption_value(p.yellow_bank)
        if need > 0:
            p, paid = economy.settle_loss(db, p, "food", need)
            missing = need - paid
            if missing > 0:
                p = replace(p, culture=max(
                    0, p.culture - FOOD_SHORTAGE_CULTURE_PENALTY * missing))
        # 资源生产
        p = economy.produce(db, p, "resource")
        state = replace_player(state, i, p)
    return state


def _emigration(state: GameState, db: CardDB) -> GameState:
    """每个文明失去一半人口(向上取整, 移回黄点银行; 失去口径同
    lose_population: 先空闲池, 不足按字典序从卡上移除)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        total = workers_total(p)
        if total == 0:
            continue
        state = replace_player(state, i, lose_population(p, (total + 1) // 2))
    return state


def _iconoclasm(state: GameState, db: CardDB) -> GameState:
    """弃掉所有非当前时代的在场领袖(入内政弃牌堆, leader_ages 保留)."""
    for i, p in enumerate(state.players):
        if p.resigned or p.leader is None:
            continue
        if db.get(p.leader).age is state.age:
            continue
        state = replace(state, discard=state.discard + (p.leader,))
        state = replace_player(
            state, i, replace(state.players[i], leader=None))
    return state


def _independence_declaration(state: GameState, db: CardDB) -> GameState:
    """最弱文明失去 1 个殖民地(该玩家选择, 强制 pending); 无则无效果."""
    weakest = _weakest_seats(db, state)[0]
    if state.players[weakest].colonies:
        state = _push_chain(state, KIND_EVENT_LOSE_COLONY, [weakest])
    return state


def _international_agreement(state: GameState, db: CardDB) -> GameState:
    """最强文明可用最多 5 白点从卡牌列拿牌(逐个选择 pending, AGREEMENT_DONE
    提前结束); 跳过其下一次政治行动; 拿牌结束后补满卡牌列."""
    strongest = _strongest_seats(db, state)[0]
    p = state.players[strongest]
    state = replace_player(
        state, strongest, replace(p, miss_political_action=True))
    if agreement_take_options(db, state, state.players[strongest],
                              AGREEMENT_BUDGET):
        pending = PendingEffect(
            KIND_EVENT_AGREEMENT, 0, responder=strongest,
            context={"budget": AGREEMENT_BUDGET})
        return replace(state, pending=state.pending + (pending,))
    # 无可拿之牌(白点/预算不足或行空): 直接补满卡牌列
    return _replenish_card_row(state)


def agreement_take_cost(
    db: CardDB, p: PlayerState, row_index: int, card_id: str,
) -> int:
    """international_agreement 拿牌白点费(与 apply._take_card 同口径)."""
    card = db.get(card_id)
    cost = ROW_COSTS[row_index]
    if card.category is CardCategory.WONDER:
        cost += effects.wonder_take_surcharge(db, p)
    if card.category is CardCategory.LEADER:
        cost = max(0, cost - effects.leader_take_discount(db, p))
    return cost


def agreement_take_options(
    db: CardDB, state: GameState, p: PlayerState, budget: int,
) -> list[int]:
    """international_agreement 可拿槽位: 白点费 <= min(预算, 现有白点).

    其余拿牌约束(手牌上限/查重/奇迹在建/领袖时代)与
    legal._take_card_legal 同口径; 不含 hammurabi 红点垫付(事件拿牌仅耗
    白点)。
    """
    options: list[int] = []
    for i, card_id in enumerate(state.card_row):
        if card_id is None:
            continue
        card = db.get(card_id)
        cost = agreement_take_cost(db, p, i, card_id)
        if cost > budget or cost > p.civil_actions:
            continue
        if card.category is CardCategory.WONDER:
            # 奇迹牌不受内政手牌上限限制; 有未完成奇迹不可再拿
            if p.wonder_progress is not None:
                continue
        else:
            if len(p.hand_civil) >= hand_limit_civil(db, p):
                continue
            if card.category in _AGREEMENT_NO_DUPLICATE:
                if card_id in p.hand_civil or card_id in p.developed:
                    continue
            if card.category is CardCategory.GOVERNMENT:
                if card_id == p.government:
                    continue
            if card.category is CardCategory.LEADER:
                if card.age.value in p.leader_ages:
                    continue
        options.append(i)
    return options


def _agreement_choice(
    db: CardDB, state: GameState, pending: PendingEffect, idx: int,
    option: str,
) -> GameState:
    """international_agreement 选择结算: 拿 1 张牌(扣白点与预算)或结束.

    结束后(AGREEMENT_DONE / 预算或白点耗尽无可拿)补满卡牌列。pending[0]
    已由 apply_event_choice pop; 可继续拿时重压新预算 pending 于栈顶。
    """
    if option == AGREEMENT_DONE:
        return _replenish_card_row(state)
    row_index = int(option)
    p = state.players[idx]
    card_id = state.card_row[row_index]
    if card_id is None:  # pragma: no cover - legal 已排除
        msg = f"卡牌列 {row_index} 号位为空"
        raise ValueError(msg)
    card = db.get(card_id)
    cost = agreement_take_cost(db, p, row_index, card_id)
    row = list(state.card_row)
    row[row_index] = None
    state = replace(state, card_row=tuple(row))
    p = replace(p, civil_actions=p.civil_actions - cost)
    if card.category is CardCategory.WONDER:
        p = replace(p, wonder_progress=(card_id, 0))
    else:
        p = replace(p, hand_civil=p.hand_civil + (card_id,))
    # aristotle 等领袖的拿牌即时收益(与 apply._take_card 同口径)
    gains = effects.on_take_card_gains(db, p, card)
    if gains:
        p = replace(p,
                    science=p.science + gains.get("science", 0),
                    culture=p.culture + gains.get("culture", 0))
    state = replace_player(state, idx, p)
    remaining = int(pending.context["budget"]) - cost
    if remaining > 0 and agreement_take_options(db, state, p, remaining):
        nxt = PendingEffect(
            KIND_EVENT_AGREEMENT, 0, responder=idx,
            context={"budget": remaining})
        return replace(state, pending=(nxt,) + state.pending)
    return _replenish_card_row(state)


def _replenish_card_row(state: GameState) -> GameState:
    """international_agreement 补满卡牌列: 空槽从左到右以当前内政牌堆顶
    依次填入(SIMPLIFICATION: 不触发时代结束处理, 牌堆尽则留空)."""
    row = list(state.card_row)
    deck = list(state.civil_deck)
    for i in range(ROW_SLOTS):
        if row[i] is None and deck:
            row[i] = deck.pop(0)
    return replace(state, card_row=tuple(row), civil_deck=tuple(deck))


def _national_pride(state: GameState, db: CardDB) -> GameState:
    """文化分最多的文明 +5 文化(平局按顺时针近者优先)."""
    cultures = [p.culture for p in state.players]
    leader = _extreme_seats(state, cultures, strongest=True)[0]
    p = state.players[leader]
    return replace_player(
        state, leader, replace(p, culture=p.culture + NATIONAL_PRIDE_CULTURE))


def _politics_of_strength(state: GameState, db: CardDB) -> GameState:
    """最强 +5 军事牌; 最弱 -3 军事牌; 最终时代(III/IV)改为 ±文化.

    - 抓牌共用 military.draw_military(与事件/回合末抓牌同一官方口径);
    - 弃牌为手牌 -3(SIMPLIFICATION: 按 card_id 字典序确定弃置, 官方为
      玩家自选; 不足 3 张则全弃);
    - 终局 ±文化分值 PDF 未给, 按同数值直译(最强 +5 / 最弱 -3 下限 0,
      见任务报告存疑)。
    """
    strongest = _strongest_seats(db, state)[0]
    weakest = _weakest_seats(db, state)[0]
    if state.age in _FINAL_AGES:
        p = state.players[strongest]
        state = replace_player(state, strongest, replace(
            p, culture=p.culture + POLITICS_OF_STRENGTH_DRAW))
        p = state.players[weakest]
        return replace_player(state, weakest, replace(
            p, culture=max(0, p.culture - POLITICS_OF_STRENGTH_DISCARD)))
    state = military.draw_military(
        state, strongest, POLITICS_OF_STRENGTH_DRAW)
    p = state.players[weakest]
    discarded = tuple(sorted(p.hand_military)[:POLITICS_OF_STRENGTH_DISCARD])
    hand = list(p.hand_military)
    for card_id in discarded:
        hand.remove(card_id)
    state = replace_player(
        state, weakest, replace(p, hand_military=tuple(hand)))
    return replace(
        state, military_discard=state.military_discard + discarded)


def _popularization_of_science(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化, 等于其科技增速."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        rate = civ_values(db, p, state.players, i).science_rate
        if rate:
            state = replace_player(
                state, i, replace(p, culture=p.culture + rate))
    return state


def _prosperity(state: GameState, db: CardDB) -> GameState:
    """每个文明每个笑脸 +1 人口(至多 8; 黄点银行空则尽力而为)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        happiness = civ_values(db, p, state.players, i).happiness
        count = min(happiness, PROSPERITY_MAX_POPULATION, p.yellow_bank)
        if count:
            state = replace_player(state, i, replace(
                p, yellow_bank=p.yellow_bank - count,
                worker_pool=p.worker_pool + count))
    return state


def ravages_eligible_wonders(db: CardDB, p: PlayerState) -> list[str]:
    """ravages_of_time 可翻面的奇迹(A/I 时代已完成且未翻面)."""
    return [
        card_id for card_id in p.wonders
        if db.get(card_id).age in _RAVAGES_WONDER_AGES
        and card_id not in p.wonders_facedown
    ]


def _ravages_of_time(state: GameState, db: CardDB) -> GameState:
    """每名玩家将 1 个 A/I 奇迹翻面(各自选择, 强制 pending; 效果失效,
    转为 +2 文化增速, 见 civ.civ_values); 无合格奇迹的玩家跳过."""
    seats = [
        seat for seat in _seat_order(state)
        if ravages_eligible_wonders(db, state.players[seat])
    ]
    return _push_chain(state, KIND_EVENT_RAVAGES, seats)


def _refugees(state: GameState, db: CardDB) -> GameState:
    """最弱 -3 文化(下限 0)与 -1 人口; 最强 +3 文化与 +1 人口(银行非空)."""
    weakest = _weakest_seats(db, state)[0]
    strongest = _strongest_seats(db, state)[0]
    p = state.players[weakest]
    p = replace(p, culture=max(0, p.culture - REFUGEES_CULTURE))
    state = replace_player(state, weakest, lose_population(p, 1))
    p = state.players[strongest]
    p = replace(p, culture=p.culture + REFUGEES_CULTURE)
    if p.yellow_bank > 0:
        p = replace(
            p, yellow_bank=p.yellow_bank - 1,
            worker_pool=p.worker_pool + 1)
    return replace_player(state, strongest, p)


def _terrorism(state: GameState, db: CardDB) -> GameState:
    """文化分最少的文明之外, 其他每个文明各摧毁 1 个城市建筑.

    受害者各自选择(强制 pending, 与 border_conflict/raid 的"受害者自选"
    口径一致; 失去口径: 所选卡 -1 工人回空闲池); 无城市建筑的文明跳过。
    """
    cultures = [p.culture for p in state.players]
    least = _extreme_seats(state, cultures, strongest=False)[0]
    seats = [
        seat for seat in _seat_order(state)
        if seat != least and urban_destroyable_ids(state.players[seat])
    ]
    return _push_chain(state, KIND_EVENT_DESTROY_URBAN, seats)


EVENT_HANDLERS.update({
    "civil_unrest": _civil_unrest,
    "cold_war": _cold_war,
    "crime_wave": _crime_wave,
    "economic_progress": _economic_progress,
    "emigration": _emigration,
    "iconoclasm": _iconoclasm,
    "independence_declaration": _independence_declaration,
    "international_agreement": _international_agreement,
    "national_pride": _national_pride,
    "politics_of_strength": _politics_of_strength,
    "popularization_of_science": _popularization_of_science,
    "prosperity": _prosperity,
    "ravages_of_time": _ravages_of_time,
    "refugees": _refugees,
    "terrorism": _terrorism,
})


# --- 时代 III 事件 handler(卡牌数值表 p4 Events 表 Age III 行, 全为 Impact 计分类) ----
#
# 统一口径:
# - 全为自动计分, 每名在局(未退出)玩家按公式 +文化(仅 impact_of_happiness
#   可为负, 文化下限 0), 不压 pending;
# - 农场/矿场"产出"= Σ 工人数 × token_value(每张有工人的卡每回合各产 1 蓝点,
#   与 economy.produce 同口径);
# - "级"= 时代序(A=1, I=2, II=3, III=4, 与 effects/politics 的 _TECH_LEVEL
#   同口径); 同名卡的每个工人 = 一张同等级卡;
# - 排名类(impact_of_science/strength)平局按当前玩家顺时针近者优先(规则书
#   p7; 终局结算时起始玩家视作当前玩家, 见 endgame_scoring);
# - 翻面奇迹(ravages_of_time)仍计入 impact_of_wonders(规则书附录 p12
#   岁月摧残: 被摧残的奇迹仍视作一个相应时代的已完成的奇迹)。

IMPACT_AGRICULTURE_SURPLUS_BONUS = 4
"""impact_of_agriculture 产出超过消耗的额外文化."""

IMPACT_BALANCE_MULTIPLIER = 2
"""impact_of_balance 最低产出的文化倍数."""

IMPACT_COLONIES_CULTURE = 3
"""impact_of_colonies 每殖民地文化."""

IMPACT_GOVERNMENT_CIVIL_CULTURE = 2
IMPACT_GOVERNMENT_MILITARY_CULTURE = 1
"""impact_of_government 每内政/军事行动的文化."""

IMPACT_HAPPINESS_CULTURE = 2
"""impact_of_happiness 每笑脸 +文化 / 每不快乐工人 -文化."""

IMPACT_POPULATION_THRESHOLD = 10
IMPACT_POPULATION_CULTURE = 2
"""impact_of_population 超过阈值的人口每人口文化."""

IMPACT_PROGRESS_CULTURE = 2
"""impact_of_progress 每级政体与特殊科技的文化."""

IMPACT_TECHNOLOGY_CULTURE = 4
"""impact_of_technology 每项时代 III 科技的文化."""

IMPACT_VARIETY_CULTURE = 2
"""impact_of_variety 每种类型的文化."""

IMPACT_RATING_SCORES: dict[int, tuple[int, ...]] = {
    2: (10, 0),
    3: (14, 7, 0),
    4: (15, 10, 5, 0),
}
"""排名类 Impact 按在局人数的名次文化表(PDF: 10/0, 14/7/0, 15/10/5/0)."""

IMPACT_WONDER_SCORES: dict[Age, int] = {
    Age.A: 5, Age.I: 4, Age.II: 3, Age.III: 2,
}
"""impact_of_wonders 各时代奇迹分值."""

BILL_GATES = "bill_gates"
BILL_GATES_RESOURCE_PER_LEVEL = 1
"""bill_gates: 实验室每级产 1 资源; 终局 +文化 = 该额外产出."""

_TECH_LEVEL: dict[Age, int] = {Age.A: 1, Age.I: 2, Age.II: 3, Age.III: 4}
"""卡牌等级(级 = 时代序; 与 effects/politics 同口径, 防循环 import 重声明)."""

_COMPETITION_CATEGORIES = UNIT_CATEGORIES | frozenset({CardCategory.ARENA})
"""impact_of_competition 计等级的类别(军事单位与竞技场)."""


def _production_rate(db: CardDB, p: PlayerState, category: CardCategory) -> int:
    """农场/矿场每回合产出 = Σ 工人数 × token_value."""
    return sum(
        workers * db.get(card_id).token_value
        for card_id, workers in p.buildings.get(category.value, {}).items()
        if workers > 0
    )


def _building_levels(
    db: CardDB, p: PlayerState, categories: frozenset[CardCategory],
) -> int:
    """指定类别建筑的等级总和(每工人 = 一张同等级卡, 级 = 时代序)."""
    return sum(
        workers * _TECH_LEVEL[db.get(card_id).age]
        for category in categories
        for card_id, workers in p.buildings.get(category.value, {}).items()
        if workers > 0
    )


def _building_types(
    p: PlayerState, categories: frozenset[CardCategory],
) -> int:
    """指定类别有工人的卡 id 数(类型数)."""
    return sum(
        1
        for category in categories
        for workers in p.buildings.get(category.value, {}).values()
        if workers > 0
    )


def _impact_all(
    state: GameState, db: CardDB,
    score: Callable[[CardDB, GameState, int], int],
) -> GameState:
    """每名在局玩家按 score(db, state, 座位) 加文化(负值下限 0)."""
    for i, p in enumerate(state.players):
        if p.resigned:
            continue
        delta = score(db, state, i)
        if delta:
            state = replace_player(
                state, i, replace(p, culture=max(0, p.culture + delta)))
    return state


def _impact_rating(
    state: GameState, db: CardDB, values: list[int],
) -> GameState:
    """排名类 Impact: 按 values 降序排名, 平局按当前玩家顺时针近者优先.

    名次分值按在局(未退出)人数查 IMPACT_RATING_SCORES(规则书 p4: 只剩
    2 位玩家时按 2 人规则结算事件); 已退出者不参与排名不计分。
    """
    active = active_indices(state)
    table = IMPACT_RATING_SCORES[len(active)]
    ordered = sorted(
        active,
        key=lambda seat: (-values[seat], _clockwise_distance(state, seat)))
    for rank, seat in enumerate(ordered):
        gain = table[rank]
        if gain:
            p = state.players[seat]
            state = replace_player(
                state, seat, replace(p, culture=p.culture + gain))
    return state


def _impact_of_agriculture(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化 = 农场产出; 产出超过消耗再 +4."""

    def score(db: CardDB, state: GameState, i: int) -> int:
        p = state.players[i]
        production = _production_rate(db, p, CardCategory.FARM)
        surplus = production > consumption_value(p.yellow_bank)
        return production + (IMPACT_AGRICULTURE_SURPLUS_BONUS if surplus else 0)

    return _impact_all(state, db, score)


def _impact_of_architecture(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化 = 城市建筑等级总和."""
    return _impact_all(
        state, db,
        lambda db, state, i: _building_levels(
            db, state.players[i], URBAN_CATEGORIES))


def _impact_of_balance(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化 = 2 × 四项产出(科技/文化/食物/资源)的最低值."""

    def score(db: CardDB, state: GameState, i: int) -> int:
        p = state.players[i]
        values = civ_values(db, p, state.players, i)
        least = min(
            values.science_rate, values.culture_rate,
            _production_rate(db, p, CardCategory.FARM),
            _production_rate(db, p, CardCategory.MINE))
        return IMPACT_BALANCE_MULTIPLIER * least

    return _impact_all(state, db, score)


def _impact_of_colonies(state: GameState, db: CardDB) -> GameState:
    """每个文明每个殖民地 +3 文化."""
    return _impact_all(
        state, db,
        lambda db, state, i: IMPACT_COLONIES_CULTURE * len(state.players[i].colonies))


def _impact_of_competition(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化 = 军事单位与竞技场的等级总和."""
    return _impact_all(
        state, db,
        lambda db, state, i: _building_levels(
            db, state.players[i], _COMPETITION_CATEGORIES))


def _impact_of_government(state: GameState, db: CardDB) -> GameState:
    """每个文明每内政行动 +2 文化, 每军事行动 +1 文化(civ 总值)."""

    def score(db: CardDB, state: GameState, i: int) -> int:
        values = civ_values(db, state.players[i], state.players, i)
        return (
            IMPACT_GOVERNMENT_CIVIL_CULTURE * values.civil_actions
            + IMPACT_GOVERNMENT_MILITARY_CULTURE * values.military_actions)

    return _impact_all(state, db, score)


def _impact_of_happiness(state: GameState, db: CardDB) -> GameState:
    """每个文明每笑脸 +2 文化, 每不快乐工人(discontent) -2 文化."""

    def score(db: CardDB, state: GameState, i: int) -> int:
        p = state.players[i]
        happiness = civ_values(db, p, state.players, i).happiness
        return IMPACT_HAPPINESS_CULTURE * (
            happiness - discontent(db, p, state.players, i))

    return _impact_all(state, db, score)


def _impact_of_industry(state: GameState, db: CardDB) -> GameState:
    """每个文明 +文化 = 矿场资源产出.

    bill_gates 实验室产资源不计入(规则书附录 p12 比尔·盖茨: 结算工业的
    影响时, 因本牌效果实验室生产的资源数量不会被计算在内)。
    """
    return _impact_all(
        state, db,
        lambda db, state, i: _production_rate(
            db, state.players[i], CardCategory.MINE))


def _impact_of_population(state: GameState, db: CardDB) -> GameState:
    """每个文明超过 10 的每个人口 +2 文化(人口 = 工人总数)."""
    return _impact_all(
        state, db,
        lambda db, state, i: IMPACT_POPULATION_CULTURE * max(
            0, workers_total(state.players[i]) - IMPACT_POPULATION_THRESHOLD))


def _impact_of_progress(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 文化 × (政体等级 + 已研发特殊科技等级和)."""

    def score(db: CardDB, state: GameState, i: int) -> int:
        p = state.players[i]
        levels = _TECH_LEVEL[db.get(p.government).age]
        levels += sum(
            _TECH_LEVEL[db.get(card_id).age]
            for card_id in p.developed
            if db.get(card_id).category is CardCategory.SPECIAL)
        return IMPACT_PROGRESS_CULTURE * levels

    return _impact_all(state, db, score)


def _impact_of_science(state: GameState, db: CardDB) -> GameState:
    """按科技增速排名计分(2p 10/0, 3p 14/7/0, 4p 15/10/5/0)."""
    rates = [
        civ_values(db, p, state.players, i).science_rate
        for i, p in enumerate(state.players)
    ]
    return _impact_rating(state, db, rates)


def _impact_of_strength(state: GameState, db: CardDB) -> GameState:
    """按 civ 军力排名计分(分值表同 impact_of_science)."""
    return _impact_rating(state, db, _strengths(db, state))


def _impact_of_technology(state: GameState, db: CardDB) -> GameState:
    """每个文明每项时代 III 科技 +4 文化(政体算科技, 同 first_space_flight
    口径; 按已研发卡逐张计)."""

    def score(db: CardDB, state: GameState, i: int) -> int:
        p = state.players[i]
        count = sum(
            1 for card_id in p.developed if db.get(card_id).age is Age.III)
        if db.get(p.government).age is Age.III:
            count += 1
        return IMPACT_TECHNOLOGY_CULTURE * count

    return _impact_all(state, db, score)


def _impact_of_variety(state: GameState, db: CardDB) -> GameState:
    """每个文明 +2 文化/类型: 军事单位、城市建筑与特殊(蓝色)科技.

    单位/城市建筑按有工人的卡 id 计类型; 特殊科技按已研发卡计。
    """

    def score(db: CardDB, state: GameState, i: int) -> int:
        p = state.players[i]
        types = _building_types(p, UNIT_CATEGORIES | URBAN_CATEGORIES)
        types += sum(
            1 for card_id in p.developed
            if db.get(card_id).category is CardCategory.SPECIAL)
        return IMPACT_VARIETY_CULTURE * types

    return _impact_all(state, db, score)


def _impact_of_wonders(state: GameState, db: CardDB) -> GameState:
    """每个文明按已完成奇迹 +文化: A 5 / I 4 / II 3 / III 2.

    翻面奇迹(ravages_of_time)仍计入(规则书附录 p12 岁月摧残: 被摧残的
    奇迹仍视作一个相应时代的已完成的奇迹); 翻面奇迹留在 wonders 中, 直接
    遍历即含。
    """
    return _impact_all(
        state, db,
        lambda db, state, i: sum(
            IMPACT_WONDER_SCORES[db.get(card_id).age]
            for card_id in state.players[i].wonders))


EVENT_HANDLERS.update({
    "impact_of_agriculture": _impact_of_agriculture,
    "impact_of_architecture": _impact_of_architecture,
    "impact_of_balance": _impact_of_balance,
    "impact_of_colonies": _impact_of_colonies,
    "impact_of_competition": _impact_of_competition,
    "impact_of_government": _impact_of_government,
    "impact_of_happiness": _impact_of_happiness,
    "impact_of_industry": _impact_of_industry,
    "impact_of_population": _impact_of_population,
    "impact_of_progress": _impact_of_progress,
    "impact_of_science": _impact_of_science,
    "impact_of_strength": _impact_of_strength,
    "impact_of_technology": _impact_of_technology,
    "impact_of_variety": _impact_of_variety,
    "impact_of_wonders": _impact_of_wonders,
})


# --- 终局计分(规则书 p1 游戏流程) ---------------------------------------------------


def endgame_scoring(db: CardDB, state: GameState) -> GameState:
    """终局计分: 时代 III 事件 -> 终局奖励效果 -> terminal + final_scores.

    规则书 p1: 最后的游戏轮过后, 以任意顺序结算当前和未来事件牌堆中所有
    时代 III 的事件牌, 再结算所有游戏结束时能够结算的奖励效果(例如
    比尔·盖茨), 最高文化获胜(并列共享, 由 orchestrator 判定)。
    引擎约定结算顺序: current_events 先、future_events 后, 各自原顺序;
    非时代 III 的卡不结算并留堆(终局状态仅作记录)。已结算事件入
    past_events。终局的事件平局比较以起始玩家(0 号位)视作当前玩家
    (规则书 p7 结算事件), 结算期间 current_player 临时置 0, 结算后还原。
    Impact 事件全为自动计分类, 不压 pending(若压 pending 终局会悬空,
    属实现缺陷)。
    """
    current_player = state.current_player
    state = replace(state, current_player=0)
    piles = state.current_events + state.future_events
    resolved = tuple(
        card_id for card_id in piles if db.get(card_id).age is Age.III)
    for card_id in resolved:
        state = resolve_event(state, db, card_id)
        state = replace(state, past_events=state.past_events + (card_id,))
    state = replace(
        state,
        current_events=tuple(
            c for c in state.current_events if db.get(c).age is not Age.III),
        future_events=tuple(
            c for c in state.future_events if db.get(c).age is not Age.III))
    state = _bill_gates_endgame(db, state)
    return replace(
        state,
        current_player=current_player,
        terminal=True,
        final_scores=tuple(p.culture for p in state.players),
    )


def _bill_gates_endgame(db: CardDB, state: GameState) -> GameState:
    """bill_gates 终局奖励: +文化 = 实验室额外产出 = Σ 有工人实验室
    工人数 × 等级(级 = 时代序).

    实验室每回合按矿山方式产资源的经济改造见 economy 的 LAB 口径(P3-T4;
    不计入 impact_of_industry, 规则书附录明示, 见 _impact_of_industry);
    被替换离场的即时奖励见 effects.gates_lab_bonus_culture; 本函数仅结算
    规则书 p1 的游戏结束奖励效果。
    """
    for i, p in enumerate(state.players):
        if p.resigned or p.leader != BILL_GATES:
            continue
        extra = _building_levels(db, p, frozenset({CardCategory.LAB}))
        extra *= BILL_GATES_RESOURCE_PER_LEVEL
        if extra:
            state = replace_player(
                state, i, replace(p, culture=p.culture + extra))
    return state
