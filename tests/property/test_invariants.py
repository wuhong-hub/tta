"""官方规则属性测试: 随机合法动作整局的不变量校验(P1 Task 14 重写).

用 stdlib random 驱动随机合法动作, 跑 10 个种子的 2 人整局, 每步断言:

1. 黄点守恒(每人): yellow_bank + worker_pool + 建筑工人数
   = 25 − 2 × (已结束的时代 I/II/III 数) + 转移净转入。
   口径说明: 时代 A 结束官方规则 "nothing else happens"(无 −2),
   时代 I/II/III 结束各 −2(turn.py AGE_END_YELLOW_LOSS; III 结束进入
   时代 IV 前在 _enter_age_four 执行同一序列)。由 state.age 推断已结束的
   时代 I/II/III 数: A/I -> 0, II -> 1, III -> 2, IV -> 3。引擎对 −2 做
   下限 0 截断(max(0, bank − 2)), 时代结束时 yellow_bank 实际恒 ≥ 2,
   等号成立。玩家间零和转移 = uncertain_borders 事件(时代 I, 最弱银行
   转 1 黄点给最强银行)与领土之战(war_over_territory_ii, 黄点银行
   转移, P2-T9); 驱动循环在转移步骤按结算前后差值累计净转入
   (yellow_adj)并断言零和, 其余步骤严格等号。
2. 蓝点守恒(每人, 精确等号): blue_bank + Σ card_tokens + 进行中奇迹
   已付阶段数 == 16 + 3 × (本局已成功研发 justice_system +
   civil_service 的次数, 由驱动循环按 DevelopTech 动作追踪)。
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
   -> tactics 字段, 替换时实体卡入军事弃牌堆, 复制引用仅引用不计;
   宣告战争手牌 -> declared_wars(在途), 结算后入军事弃牌堆)。
5. 序列化往返: 每 10 步 from_dict(to_dict(state)) == state。
6. state_hash 链: 同 seed 两次逐步走, 每步 hash 相等(见独立测试)。
"""

import random
from collections import Counter

import pytest

from tta.cards import build_card_db
from tta.engine import politics
from tta.engine.actions import DevelopTech, SeedEvent
from tta.engine.apply import apply
from tta.engine.enums import Age, DeckType
from tta.engine.legal import legal_actions
from tta.engine.setup import new_game
from tta.engine.state import (
    GameState,
    PlayerState,
    from_dict,
    state_hash,
    to_dict,
    workers_total,
)
from tta.engine.turn import AGE_END_YELLOW_LOSS

SEEDS = range(10)
"""整局属性测试的种子集."""

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
    # 响应中的在途牌: 侵略揭示卡(aggression_defense pending context)与
    # 竞拍/牺牲中的地区牌(colonize pending context)暂不在任何牌域
    for e in state.pending:
        if e.kind == politics.KIND_AGGRESSION_DEFENSE:
            accounted.update([str(e.context["card"])])
        elif e.kind in (politics.KIND_COLONIZE_BID,
                        politics.KIND_COLONIZE_SACRIFICE):
            accounted.update([str(e.context["territory"])])
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


def _assert_player_invariants(
    db, state: GameState, p: PlayerState, blue_gains: int, yellow_adj: int = 0,
) -> None:
    # 黄点守恒(精确等号, 口径见模块 docstring; yellow_adj = uncertain_borders
    # 净转入, 由驱动循环累计)
    assert _yellow_total(p) == _yellow_expected(state.age) + yellow_adj, (
        f"{p.name} 黄点不守恒: {_yellow_total(p)} != "
        f"{_yellow_expected(state.age)} + {yellow_adj} (age={state.age})"
    )
    # 蓝点精确守恒(支付/消耗/腐败/奇迹完成均放回供给区, 见模块 docstring)
    assert _blue_total(p) == _blue_ceiling(blue_gains), (
        f"{p.name} 蓝点不守恒: {_blue_total(p)} != {_blue_ceiling(blue_gains)}"
    )
    # 资源/行动点非负, 银行区间
    assert p.culture >= 0
    assert p.science >= 0
    assert p.civil_actions >= 0
    assert p.military_actions >= 0
    assert 0 <= p.yellow_bank <= 18
    assert 0 <= p.blue_bank <= _blue_ceiling(blue_gains)
    assert all(count >= 0 for count in p.card_tokens.values())


def _run_game_with_invariants(db, seed: int) -> GameState:
    """跑一整局, 每步断言全部不变量, 返回终局状态."""
    state = new_game(db, 2, seed)
    rng = random.Random(seed)
    universe = _universe(db, 2)
    blue_gains = [0, 0]
    yellow_adj = [0, 0]
    steps = 0
    while not state.terminal:
        legal = legal_actions(db, state)
        action = rng.choice(legal)
        if isinstance(action, DevelopTech) and action.card_id in BLUE_GAIN_CARDS:
            # 研发 justice_system/civil_service 各从盒中 +3 蓝点(含
            # breakthrough pending 子行动; 替换移除不影响已得蓝点)
            blue_gains[state.current_player] += 1
        # 黄点零和转移步骤识别(口径见模块 docstring 第 1 条):
        # ① uncertain_borders 揭示(筹划动作 + 当前事件堆顶即该事件);
        # ② 领土之战于本步结算(war_over_territory_ii 离开 declared_wars)。
        uncertain = (
            isinstance(action, SeedEvent)
            and state.current_events[:1] == ("uncertain_borders",)
        )
        territory_wars_before = sum(
            card_id == "war_over_territory_ii"
            for p in state.players for card_id, _ in p.declared_wars
        )
        before = [_yellow_total(p) for p in state.players]
        age_before = state.age
        state = apply(state, action, db)
        ended = (_AGE_ENDED_YELLOW_LOSS_COUNT[state.age]
                 - _AGE_ENDED_YELLOW_LOSS_COUNT[age_before])
        deltas = [
            _yellow_total(p) - before[i] + AGE_END_YELLOW_LOSS * ended
            for i, p in enumerate(state.players)
        ]
        territory_wars_after = sum(
            card_id == "war_over_territory_ii"
            for p in state.players for card_id, _ in p.declared_wars
        )
        if uncertain or territory_wars_after < territory_wars_before:
            # 转移步骤: 玩家间零和(不足封顶仍零和), 累计净转入
            assert sum(deltas) == 0, (
                f"seed {seed} step {steps} 黄点转移非零和: {deltas}")
            for i, delta in enumerate(deltas):
                yellow_adj[i] += delta
        else:
            # 其余步骤: 每人黄点总量仅随时代结束 -2(已加回)变化
            assert all(delta == 0 for delta in deltas), (
                f"seed {seed} step {steps} 非转移步骤黄点变动: {deltas}")
        steps += 1
        for i, p in enumerate(state.players):
            _assert_player_invariants(
                db, state, p, blue_gains[i], yellow_adj[i])
        assert _accounted(state) == universe, (
            f"seed {seed} step {steps} 卡牌守恒破坏: "
            f"{_accounted(state) - universe} / {universe - _accounted(state)}"
        )
        if steps % SERIALIZE_EVERY == 0:
            assert from_dict(to_dict(state)) == state, (
                f"seed {seed} step {steps} 序列化往返失败"
            )
    assert state.final_scores is not None
    assert state.final_scores == tuple(p.culture for p in state.players)
    return state


@pytest.mark.parametrize("seed", SEEDS)
def test_full_game_invariants(db, seed: int) -> None:
    """10 种子 2 人整局: 每步黄点/蓝点/非负/卡牌守恒 + 定期序列化往返."""
    _run_game_with_invariants(db, seed)


def test_state_hash_chain_deterministic(db) -> None:
    """同 seed 两次逐步走: 每步 state_hash 相等(含终局)."""
    hashes: list[str] = []
    for _ in range(2):
        state = new_game(db, 2, 7)
        rng = random.Random(7)
        run_hashes = [state_hash(state)]
        while not state.terminal:
            legal = legal_actions(db, state)
            state = apply(state, rng.choice(legal), db)
            run_hashes.append(state_hash(state))
        hashes.append(run_hashes)
    assert len(hashes[0]) == len(hashes[1])
    for step, (h1, h2) in enumerate(zip(*hashes, strict=True)):
        assert h1 == h2, f"step {step} hash 分叉: {h1} != {h2}"
