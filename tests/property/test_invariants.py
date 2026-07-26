"""官方规则属性测试: 随机合法动作整局的不变量校验(P1 Task 14 重写).

用 stdlib random 驱动随机合法动作, 跑 10 个种子的 2 人整局与 3 个种子的
3 人整局(覆盖条约双录/多目标战争), 每步断言:

1. 黄点守恒(每人): yellow_bank + worker_pool + 建筑工人数
   = 25 − 2 × (已结束的时代 I/II/III 数) + 转移净转入 + 殖民地配件盒补偿。
   口径说明: 时代 A 结束官方规则 "nothing else happens"(无 −2),
   时代 I/II/III 结束各 −2(turn.py AGE_END_YELLOW_LOSS; III 结束进入
   时代 IV 前在 _enter_age_four 执行同一序列)。由 state.age 推断已结束的
   时代 I/II/III 数: A/I -> 0, II -> 1, III -> 2, IV -> 3。引擎对 −2 做
   下限 0 截断(max(0, bank − 2)), 时代结束时 yellow_bank 实际恒 ≥ 2,
   等号成立。玩家间零和转移 = uncertain_borders 事件(时代 I, 最弱银行
   转 1 黄点给最强银行)与领土之战(war_over_territory_ii, 黄点银行
   转移, P2-T9); 殖民地永久黄/蓝标记来自配件盒(非 25/16 池内), 竞拍
   赢得自配件盒入银行, annex/独立宣言失去按银行下限 0 归还
   (_colony_token_deltas 口径); 驱动循环在转移/殖民步骤按结算前后差值
   累计净转入(yellow_adj/blue_adj)并断言扣除配件盒收支后零和,
   其余步骤严格等号。
2. 蓝点守恒(每人, 精确等号): blue_bank + Σ card_tokens + 进行中奇迹
   已付阶段数 == 16 + 3 × (本局已成功研发 justice_system +
   civil_service 的次数, 由驱动循环按 DevelopTech 动作追踪)
   + 殖民地配件盒蓝标记补偿(blue_adj)。
   官方规则: 支付(建造/升级/增人口/食物消耗/腐败)所花蓝点放回
   blue_bank, 奇迹完成时其上蓝点也放回 blue_bank, 总量守恒 = 16
   (+ justice_system / civil_service 研发各从盒中 +3)。注意同类型
   特殊科技替换会把等级较低者从 developed 移入 removed(官方规则),
   但 +3 蓝点不退回, 故上限按"曾研发次数"而非"当前 developed"计。
3. 资源非负: culture / science / civil_actions / military_actions ≥ 0,
   yellow_bank ∈ [0, 18], blue_bank ∈ [0, 蓝点上界], card_tokens ≥ 0。
4. 卡牌守恒: 牌列 + 当前牌堆 + future_decks + 弃牌堆 + removed
   + 各玩家(手牌 + developed + 政府 + 场上领袖 + 进行中/完成奇迹
   + 实体专属阵型[tactics 且非 tactics_copied] + 在途战争牌
   declared_wars 的卡 id)
   + 军事域(military_deck + future_military_decks + military_discard
   + current_events/future_events/past_events + 各玩家军事手牌)
   ≡ 牌库全集(内政 + 军事, multiset; buildings/card_tokens 的键均 ⊆
   developed, 不重复计数; 领袖弃置入弃牌堆、政府更替入弃牌堆、过期入
   removed; 时代 A 事件堆余量与旧军事牌堆余牌入 removed; 打出阵型手牌
   -> tactics 字段, 替换时实体卡入 removed(规则书 p3, T13; 复制引用仅
   引用不计);
   宣告战争手牌 -> declared_wars(在途), 结算后入军事弃牌堆)。
5. 序列化往返: 每 10 步 from_dict(to_dict(state)) == state(含 P2 新字段
   非空值: pacts/declared_wars/colonies/wonders_facedown 等, 3 人局
   覆盖条约双录)。
6. state_hash 链: 同 seed 两次逐步走, 每步 hash 相等(见独立测试)。
7. 军事手牌上限执行(T13): 上限(= civ 军事行动点 + military_hand_extra)
   仅在回合末弃牌点强制执行, 且引擎口径弃牌检查先于抓牌——discard
   pending 压入后整个回合末流程(含抓 ≤3 张)才完成, 响应才发生, 故
   响应期手牌 = 压入时手牌 + 抓取数, 收敛后手牌 = 上限 + 抓取数; 殖民
   竞拍与 politics_of_strength 事件抽牌亦明示忽略上限。逐步可断言的
   不变量: discard_military pending 存续期间 1 ≤ context.count ≤
   响应者手牌数 − 上限(弃牌序列向上限收敛且绝不弃过限)。
8. 事件牌堆守恒(T13): 军事牌库中 EVENT/TERRITORY 类别子集 ≡
   current_events + future_events + past_events + removed 中事件类
   + 各玩家军事手牌中事件类 + 各玩家殖民地(竞拍赢得的 TERRITORY)
   + 在途(殖民竞拍 pending 的 territory)。
9. 战争/条约状态合法性(T13): declared_wars 的卡均为 WAR 类别、目标为
   未退出的其他玩家座位; pacts 双方同录(每条 (卡, 侧) 恰有另一玩家
   同录同卡异侧, 侧 ∈ {A, B}); 翻面奇迹 ⊆ 已完成奇迹。
"""

import random
from collections import Counter

import pytest

from tta.cards import build_card_db
from tta.engine import effects, politics
from tta.engine.actions import ColonizeSacrifice, DevelopTech, Resign, SeedEvent
from tta.engine.apply import apply
from tta.engine.civ import civ_values
from tta.engine.enums import Age, CardCategory, DeckType, Phase
from tta.engine.legal import legal_actions
from tta.engine.setup import new_game
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
    from_dict,
    state_hash,
    to_dict,
    workers_total,
)
from tta.engine.turn import AGE_END_YELLOW_LOSS

SEEDS = range(10)
"""整局属性测试的种子集(2 人局)."""

SEEDS_3P = range(3)
"""3 人局种子集(覆盖条约双录/多目标战争/殖民多方竞拍)."""

SERIALIZE_EVERY = 10
"""序列化往返断言的步数间隔."""

YELLOW_INITIAL_TOTAL = 25
"""开局黄点总量 = 18 银行 + 1 空闲池 + 6 初始工人."""

BLUE_INITIAL_TOTAL = 16
"""开局蓝点总量(全在 blue_bank)."""

BLUE_GAIN_CARDS = ("justice_system", "civil_service")
"""研发时从盒中 +3 蓝点的特殊科技(官方规则: 取自盒, 突破 16 上限)."""

BLUE_GAIN_AMOUNT = 3

_AGE_ENDED_YELLOW_LOSS_COUNT = {Age.A: 0, Age.I: 0, Age.II: 1, Age.III: 2, Age.IV: 3}
"""当前时代 -> 已结束的时代 I/II/III 数(时代 A 结束不扣黄点)."""


@pytest.fixture(scope="module")
def db():
    return build_card_db()


def _universe(db, num_players: int) -> Counter:
    """牌库全集 multiset: 各时代内政/军事牌堆 + 每玩家初始科技/政体."""
    universe: Counter = Counter()
    for age in (Age.A, Age.I, Age.II, Age.III):
        universe.update(db.deck_for(age, num_players))
        universe.update(db.deck_for(age, num_players, DeckType.MILITARY))
    for _ in range(num_players):
        universe.update(db.initial_tableau)
        universe.update([db.initial_government])
    return universe


def _accounted(state: GameState) -> Counter:
    """当前状态中全部卡牌的去向 multiset(应与 _universe 恒等)."""
    accounted: Counter = Counter()
    accounted.update(card_id for card_id in state.card_row if card_id is not None)
    accounted.update(state.civil_deck)
    for deck in state.future_decks.values():
        accounted.update(deck)
    accounted.update(state.discard)
    accounted.update(state.removed)
    # 军事域: 牌堆/未来牌堆/弃牌堆/事件堆
    accounted.update(state.military_deck)
    for deck in state.future_military_decks.values():
        accounted.update(deck)
    accounted.update(state.military_discard)
    accounted.update(state.current_events)
    accounted.update(state.future_events)
    accounted.update(state.past_events)
    # 响应中的在途牌: 侵略揭示卡(aggression_defense pending context)、
    # 竞拍/牺牲中的地区牌(colonize pending context)与展示中的条约牌
    # (pact_offer pending context)暂不在任何牌域
    for e in state.pending:
        if e.kind == politics.KIND_AGGRESSION_DEFENSE:
            accounted.update([str(e.context["card"])])
        elif e.kind in (politics.KIND_COLONIZE_BID,
                        politics.KIND_COLONIZE_SACRIFICE):
            accounted.update([str(e.context["territory"])])
        elif e.kind == politics.KIND_PACT_OFFER:
            accounted.update([str(e.context["card"])])
    for p in state.players:
        accounted.update(p.hand_civil)
        accounted.update(p.hand_military)
        accounted.update(p.developed)
        accounted.update([p.government])
        if p.leader is not None:
            accounted.update([p.leader])
        accounted.update(p.wonders)
        if p.wonder_progress is not None:
            accounted.update([p.wonder_progress[0]])
        if p.tactics is not None and not p.tactics_copied:
            # 专属阵型实体卡(PlayTactics 入场); 复制引用无实体卡不计
            accounted.update([p.tactics])
        # 在途战争牌(DeclareWar 手牌 -> declared_wars, 次回合结算后入
        # 军事弃牌堆; 与 T8 侵略在途口径一致)
        accounted.update(card_id for card_id, _ in p.declared_wars)
        # 生效中的条约牌(游戏区域, 缔约双方各录 (卡 id, 侧), 只计一次)
        accounted.update(
            card_id for card_id, side in p.pacts if side == "A")
    return accounted


def _yellow_total(p: PlayerState) -> int:
    """黄点总量 = 银行 + 空闲工人池 + 各建筑上的工人."""
    return p.yellow_bank + workers_total(p)


def _yellow_expected(age: Age) -> int:
    return YELLOW_INITIAL_TOTAL - 2 * _AGE_ENDED_YELLOW_LOSS_COUNT[age]


def _blue_total(p: PlayerState) -> int:
    """蓝点总量 = 银行 + 卡上储存 + 进行中奇迹已付阶段数."""
    total = p.blue_bank + sum(p.card_tokens.values())
    if p.wonder_progress is not None:
        total += p.wonder_progress[1]
    return total


def _blue_ceiling(blue_gains: int) -> int:
    """蓝点总量上界 = 16 + 3 × 曾研发蓝点增益特殊科技次数.

    按"曾研发次数"计(驱动循环追踪): 同类型特殊科技替换会将等级较低者
    移出 developed, 但研发时从盒中取的 +3 蓝点不退回。
    """
    return BLUE_INITIAL_TOTAL + BLUE_GAIN_AMOUNT * blue_gains


def _colony_token_deltas(
    db, before: GameState, after: GameState,
) -> tuple[list[int], list[int]]:
    """本步每玩家殖民地永久黄/蓝标记变动(配件盒收支口径).

    殖民地永久黄/蓝标记来自配件盒(非 25/16 池内): 获得殖民地时自配件盒
    入银行(负值标记下限 0 截断, 与 politics._grant_colony 同口径; 黄点
    永久标记全卡池非负, 故步前银行口径精确), 失去殖民地(annex /
    independence_declaration)时按持有方银行下限 0 归还配件盒(与
    politics._annex_settle / events KIND_EVENT_LOSE_COLONY 同口径)。
    """
    yellow: list[int] = []
    blue: list[int] = []
    for i, p in enumerate(after.players):
        q = before.players[i]
        dyellow = 0
        dblue = 0
        for card_id in p.colonies:
            if card_id not in q.colonies:
                permanent = db.get(card_id).territory_permanent
                dyellow += (max(0, q.yellow_bank
                                + permanent.get("yellow_token", 0))
                            - q.yellow_bank)
                dblue += (max(0, q.blue_bank
                              + permanent.get("blue_token", 0))
                          - q.blue_bank)
        for card_id in q.colonies:
            if card_id not in p.colonies:
                permanent = db.get(card_id).territory_permanent
                dyellow -= min(permanent.get("yellow_token", 0), q.yellow_bank)
                dblue -= min(permanent.get("blue_token", 0), q.blue_bank)
        yellow.append(dyellow)
        blue.append(dblue)
    return yellow, blue


def _assert_player_invariants(
    db, state: GameState, p: PlayerState, blue_gains: int, yellow_adj: int = 0,
    blue_adj: int = 0,
) -> None:
    # 黄点守恒(精确等号, 口径见模块 docstring; yellow_adj = uncertain_borders
    # 净转入与殖民地配件盒标记补偿之和, 由驱动循环累计)
    assert _yellow_total(p) == _yellow_expected(state.age) + yellow_adj, (
        f"{p.name} 黄点不守恒: {_yellow_total(p)} != "
        f"{_yellow_expected(state.age)} + {yellow_adj} (age={state.age})"
    )
    # 蓝点精确守恒(支付/消耗/腐败/奇迹完成均放回供给区, 见模块 docstring;
    # blue_adj = 殖民地配件盒蓝标记补偿)
    assert _blue_total(p) == _blue_ceiling(blue_gains) + blue_adj, (
        f"{p.name} 蓝点不守恒: {_blue_total(p)} != "
        f"{_blue_ceiling(blue_gains)} + {blue_adj}"
    )
    # 资源/行动点非负, 银行区间(上界 = 总量: 工人回银行与配件盒标记均可
    # 使银行突破 18/16 轨道上限, 见 test_colonization 同名场景测试)
    assert p.culture >= 0
    assert p.science >= 0
    assert p.civil_actions >= 0
    assert p.military_actions >= 0
    assert 0 <= p.yellow_bank <= _yellow_expected(state.age) + max(0, yellow_adj)
    assert 0 <= p.blue_bank <= _blue_ceiling(blue_gains) + max(0, blue_adj)
    assert all(count >= 0 for count in p.card_tokens.values())
    # 翻面奇迹(ravages_of_time) ⊆ 已完成奇迹(翻面不位移, 仅效果失效)
    assert set(p.wonders_facedown) <= set(p.wonders)


_EVENT_LIKE = (CardCategory.EVENT, CardCategory.TERRITORY)
"""事件堆守恒口径: 事件牌与其揭示产物的类别子集."""


def _event_universe(db, num_players: int) -> Counter:
    """军事牌库中 EVENT/TERRITORY 类别子集 multiset."""
    universe: Counter = Counter()
    for age in (Age.A, Age.I, Age.II, Age.III):
        universe.update(
            card_id
            for card_id in db.deck_for(age, num_players, DeckType.MILITARY)
            if db.get(card_id).category in _EVENT_LIKE
        )
    return universe


def _assert_event_conservation(db, state: GameState, universe: Counter) -> None:
    """事件堆守恒: current+future+past+removed(事件类)+手牌中事件类+殖民地+在途.

    口径说明: 事件牌尚未抓出时在军事牌堆/未来军事堆/军事弃牌堆中(弃置未
    筹划的事件可经切洗回流); SeedEvent 手牌 -> future_events; 揭示结算
    -> past_events; TERRITORY 竞拍在途于 pending context, 赢家入
    colonies, 流拍入 past_events; 时代 A 事件堆余量与时代切换时的旧军事
    堆均入 removed。翻面奇迹与殖民地已在全局守恒(_accounted)计入玩家
    区域, 此处殖民地为 TERRITORY 类别的专项去向。
    """
    accounted: Counter = Counter()
    accounted.update(state.current_events)
    accounted.update(state.future_events)
    accounted.update(state.past_events)
    for pile in (state.military_deck, state.military_discard, state.removed,
                 *state.future_military_decks.values()):
        accounted.update(
            card_id for card_id in pile
            if db.get(card_id).category in _EVENT_LIKE
        )
    for p in state.players:
        accounted.update(
            card_id for card_id in p.hand_military
            if db.get(card_id).category in _EVENT_LIKE
        )
        accounted.update(p.colonies)
    for e in state.pending:
        if e.kind in (politics.KIND_COLONIZE_BID,
                      politics.KIND_COLONIZE_SACRIFICE):
            accounted.update([str(e.context["territory"])])
    assert accounted == universe, (
        f"事件堆不守恒: {accounted - universe} / {universe - accounted}")


def _assert_war_pact_legality(db, state: GameState) -> None:
    """战争/条约状态合法性(见模块 docstring 第 9 条)."""
    n = len(state.players)
    for i, p in enumerate(state.players):
        for card_id, target in p.declared_wars:
            assert db.get(card_id).category is CardCategory.WAR, card_id
            assert 0 <= target < n and target != i
            assert not state.players[target].resigned
        for card_id, side in p.pacts:
            assert db.get(card_id).category is CardCategory.PACT, card_id
            assert side in ("A", "B")
            # 双方同录: 恰有另一未退出玩家同录同卡异侧
            partners = [
                j for j, q in enumerate(state.players)
                if j != i and not q.resigned
                and (card_id, "B" if side == "A" else "A") in q.pacts
            ]
            assert len(partners) == 1, (
                f"{p.name} 条约 {card_id}({side}) 无唯一对方同录: {partners}")


def _assert_military_discard_pending_exact(db, state: GameState) -> None:
    """军事手牌上限执行(模块 docstring 第 7 条).

    上限 = civ 军事行动点 + military_hand_extra, 仅回合末弃牌点强制执行。
    引擎口径弃牌检查先于抓牌: pending 压入时 count = 当时手牌 − 上限,
    随后抓牌使手牌增大, 故存续期间不变量为 1 ≤ count ≤ 手牌数 − 上限
    (每次 DiscardMilitary 手牌与 count 同步 −1, 差值 = 抓取数不变)。
    """
    for e in state.pending:
        if e.kind != effects.KIND_DISCARD_MILITARY:
            continue
        idx = int(e.responder) if e.responder is not None else state.current_player
        p = state.players[idx]
        values = civ_values(db, p, state.players, idx)
        limit = values.military_actions + values.military_hand_extra
        count = int(e.context["count"])
        assert 1 <= count <= len(p.hand_military) - limit, (
            f"{p.name} 弃牌序列越界: count={count}, 手牌 "
            f"{len(p.hand_military)}, 上限 {limit}")


def _run_game_with_invariants(db, seed: int, num_players: int = 2) -> GameState:
    """跑一整局, 每步断言全部不变量, 返回终局状态."""
    state = new_game(db, num_players, seed)
    rng = random.Random(seed)
    universe = _universe(db, num_players)
    event_universe = _event_universe(db, num_players)
    blue_gains = [0] * num_players
    yellow_adj = [0] * num_players
    blue_adj = [0] * num_players
    steps = 0
    while not state.terminal:
        legal = legal_actions(db, state)
        # 驱动不主动体面退出(Resign 恒合法, 随机选取会提前终局, 丧失中后段
        # 不变量覆盖; 退出机制由 tests/engine/test_pacts.py 专项覆盖)
        choices = [a for a in legal if not isinstance(a, Resign)]
        action = rng.choice(choices or legal)
        if isinstance(action, DevelopTech) and action.card_id in BLUE_GAIN_CARDS:
            # 研发 justice_system/civil_service 各从盒中 +3 蓝点(含
            # breakthrough pending 子行动; 替换移除不影响已得蓝点)
            blue_gains[state.current_player] += 1
        # 黄点零和转移步骤识别(口径见模块 docstring 第 1 条):
        # ① uncertain_borders 揭示(筹划动作 + 当前事件堆顶即该事件);
        # ② 领土之战于本步结算(war_over_territory_ii 离开 declared_wars);
        # ③ 殖民地变动(竞拍赢得 / annex 转移 / independence 失去):
        # 永久黄/蓝标记自配件盒收支(非零和, 见 _colony_token_deltas)。
        uncertain = (
            isinstance(action, SeedEvent)
            and state.current_events[:1] == ("uncertain_borders",)
        )
        territory_wars_before = sum(
            card_id == "war_over_territory_ii"
            for p in state.players for card_id, _ in p.declared_wars
        )
        before = [_yellow_total(p) for p in state.players]
        blue_before = [_blue_total(p) for p in state.players]
        age_before = state.age
        prev = state
        state = apply(state, action, db)
        ended = (_AGE_ENDED_YELLOW_LOSS_COUNT[state.age]
                 - _AGE_ENDED_YELLOW_LOSS_COUNT[age_before])
        deltas = [
            _yellow_total(p) - before[i] + AGE_END_YELLOW_LOSS * ended
            for i, p in enumerate(state.players)
        ]
        blue_deltas = [
            _blue_total(p) - blue_before[i]
            for i, p in enumerate(state.players)
        ]
        territory_wars_after = sum(
            card_id == "war_over_territory_ii"
            for p in state.players for card_id, _ in p.declared_wars
        )
        colony_changed = any(
            p.colonies != prev.players[i].colonies
            for i, p in enumerate(state.players)
        )
        if (uncertain or territory_wars_after < territory_wars_before
                or colony_changed):
            # 转移/殖民步骤: 扣除殖民地配件盒收支后, 玩家间转移零和
            # (不足封顶仍零和), 实际差额全额累计为补偿项
            colony_yellow, colony_blue = _colony_token_deltas(db, prev, state)
            transfer_yellow = [
                deltas[i] - colony_yellow[i] for i in range(num_players)]
            transfer_blue = [
                blue_deltas[i] - colony_blue[i] for i in range(num_players)]
            assert sum(transfer_yellow) == 0, (
                f"seed {seed} step {steps} 黄点转移非零和: {transfer_yellow}")
            assert sum(transfer_blue) == 0, (
                f"seed {seed} step {steps} 蓝点转移非零和: {transfer_blue}")
            for i in range(num_players):
                yellow_adj[i] += deltas[i]
                blue_adj[i] += blue_deltas[i]
        else:
            # 其余步骤: 每人黄点总量仅随时代结束 -2(已加回)变化
            assert all(delta == 0 for delta in deltas), (
                f"seed {seed} step {steps} 非转移步骤黄点变动: {deltas}")
        steps += 1
        for i, p in enumerate(state.players):
            _assert_player_invariants(
                db, state, p, blue_gains[i], yellow_adj[i], blue_adj[i])
        assert _accounted(state) == universe, (
            f"seed {seed} step {steps} 卡牌守恒破坏: "
            f"{_accounted(state) - universe} / {universe - _accounted(state)}"
        )
        _assert_event_conservation(db, state, event_universe)
        _assert_war_pact_legality(db, state)
        _assert_military_discard_pending_exact(db, state)
        if steps % SERIALIZE_EVERY == 0:
            assert from_dict(to_dict(state)) == state, (
                f"seed {seed} step {steps} 序列化往返失败"
            )
    assert state.final_scores is not None
    if any(p.resigned for p in state.players):
        # 体面退出判胜(规则书 p4: 只剩 1 人直接获胜, 不比文化):
        # 唯一未退出者 final_scores 严格最高
        winner = max(range(len(state.players)),
                     key=lambda i: state.final_scores[i])
        assert not state.players[winner].resigned
        assert all(
            p.resigned for i, p in enumerate(state.players) if i != winner)
    else:
        assert state.final_scores == tuple(p.culture for p in state.players)
    return state


@pytest.mark.parametrize("seed", SEEDS)
def test_full_game_invariants(db, seed: int) -> None:
    """10 种子 2 人整局: 每步黄点/蓝点/非负/卡牌守恒 + 定期序列化往返."""
    _run_game_with_invariants(db, seed)


@pytest.mark.parametrize("seed", SEEDS_3P)
def test_full_game_invariants_3p(db, seed: int) -> None:
    """3 种子 3 人整局(T13): 覆盖条约双录/多目标战争/多方殖民竞拍."""
    _run_game_with_invariants(db, seed, num_players=3)


def test_state_hash_chain_deterministic(db) -> None:
    """同 seed 两次逐步走: 每步 state_hash 相等(含终局)."""
    hashes: list[str] = []
    for _ in range(2):
        state = new_game(db, 2, 7)
        rng = random.Random(7)
        run_hashes = [state_hash(state)]
        while not state.terminal:
            legal = legal_actions(db, state)
            choices = [a for a in legal if not isinstance(a, Resign)]
            state = apply(state, rng.choice(choices or legal), db)
            run_hashes.append(state_hash(state))
        hashes.append(run_hashes)
    assert len(hashes[0]) == len(hashes[1])
    for step, (h1, h2) in enumerate(zip(*hashes, strict=True)):
        assert h1 == h2, f"step {step} hash 分叉: {h1} != {h2}"


def _tableau_player(name: str) -> PlayerState:
    """初始 tableau 玩家(黄点总量 25 = 18 银行 + 1 池 + 6 工人, 蓝点 16)."""
    return PlayerState(
        name=name,
        developed=("agriculture", "agriculture", "bronze", "bronze",
                   "philosophy", "religion", "warriors"),
        buildings={
            "farm": {"agriculture": 2},
            "mine": {"bronze": 2},
            "lab": {"philosophy": 1},
            "infantry": {"warriors": 1},
        },
    )


def test_colony_permanent_tokens_compensated(db) -> None:
    """殖民配件盒补偿: 赢得发达地区(永久 1 黄 1 蓝)后守恒公式加补偿项.

    殖民地永久黄/蓝标记来自配件盒(非 25/16 池内), 不补偿则
    yellow_total = 26 ≠ 25 误报(I4)。
    """
    state = GameState(
        round=2,
        age=Age.A,
        current_player=0,
        card_row=(None,) * ROW_SLOTS,
        civil_deck=(),
        future_decks={},
        discard=(),
        removed=(),
        players=(_tableau_player("P0"), _tableau_player("P1")),
        rng_state=42,
        phase=Phase.ACTION,
        pending=(PendingEffect(
            politics.KIND_COLONIZE_SACRIFICE, 0, responder=0,
            context={"territory": "developed_territory_i", "bid": 1,
                     "bonus": 0}),),
    )
    # 基线: 时代 A 无 -2, 双方 25 黄 / 16 蓝严格守恒
    for p in state.players:
        _assert_player_invariants(db, state, p, 0)
    new = apply(state, ColonizeSacrifice(("warriors",)), db)
    assert new.players[0].colonies == ("developed_territory_i",)
    yellow_adj, blue_adj = _colony_token_deltas(db, state, new)
    assert yellow_adj == [1, 0]
    assert blue_adj == [1, 0]
    # 牺牲 1 武士回银行(总量不变) + 配件盒 +1 黄 -> 26; 配件盒 +1 蓝 -> 17
    assert _yellow_total(new.players[0]) == 26
    assert _blue_total(new.players[0]) == 17
    for i, p in enumerate(new.players):
        _assert_player_invariants(
            db, new, p, 0, yellow_adj[i], blue_adj[i])
