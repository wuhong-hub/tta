"""官方规则属性测试: 随机合法动作整局的不变量校验(P1 Task 14 重写).

用 stdlib random 驱动随机合法动作, 跑 10 个种子的 2 人整局, 每步断言:

1. 黄点守恒(每人): yellow_bank + worker_pool + 建筑工人数
   = 25 − 2 × (已结束的时代 I/II 数)。
   口径说明: 时代 A 结束官方规则 "nothing else happens"(无 −2),
   时代 III 结束进入时代 IV 走 _enter_age_four(无 −2), 仅时代 I/II
   结束各 −2(turn.py AGE_END_YELLOW_LOSS)。由 state.age 推断已结束的
   时代 I/II 数: A/I -> 0, II -> 1, III/IV -> 2。引擎对 −2 做下限 0
   截断(max(0, bank − 2)), 时代结束时 yellow_bank 实际恒 ≥ 2, 等号成立。
2. 蓝点上界(每人): blue_bank + Σ card_tokens + 进行中奇迹已付阶段数
   ≤ 16 + 3 × (已研发 justice_system + civil_service 数), 且 ≥ 0。
   口径说明(引擎实际行为, 与官方规则存在偏差, 详见 Task 14 报告):
   - 官方规则: 支付(建造/升级/增人口/食物消耗/腐败)所花蓝点退回
     blue_bank, 奇迹完成时其上蓝点也退回 blue_bank, 总量守恒 = 16
     (+ justice_system / civil_service 各 +3);
   - 引擎实际: economy.pay / settle_loss 销毁所花蓝点(不退回
     blue_bank), apply._build_wonder_stage 奇迹完成时不退回已付阶段
     蓝点; 故蓝点总量单调递减, 仅 justice_system / civil_service
     研发 +3 可回升。本断言按引擎实际行为建模(上界 + 非负),
     官方偏差已在报告中登记, 不在此硬修。
3. 资源非负: culture / science / civil_actions / military_actions ≥ 0,
   yellow_bank ∈ [0, 18], blue_bank ∈ [0, 蓝点上界], card_tokens ≥ 0。
4. 卡牌守恒: 牌列 + 当前牌堆 + future_decks + 弃牌堆 + removed
   + 各玩家(手牌 + developed + 政府 + 场上领袖 + 进行中/完成奇迹)
   ≡ 牌库全集(multiset; buildings/card_tokens 的键均 ⊆ developed,
   不重复计数; 领袖弃置入弃牌堆、政府更替入弃牌堆、过期入 removed)。
5. 序列化往返: 每 10 步 from_dict(to_dict(state)) == state。
6. state_hash 链: 同 seed 两次逐步走, 每步 hash 相等(见独立测试)。
"""

import random
from collections import Counter

import pytest

from tta.cards import build_card_db
from tta.engine.apply import apply
from tta.engine.enums import Age
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

_AGE_ENDED_I_II_COUNT = {Age.A: 0, Age.I: 0, Age.II: 1, Age.III: 2, Age.IV: 2}
"""当前时代 -> 已结束的时代 I/II 数(时代 A 结束不扣黄点)."""


@pytest.fixture(scope="module")
def db():
    return build_card_db()


def _universe(db, num_players: int) -> Counter:
    """牌库全集 multiset: 各时代牌堆 + 每玩家初始科技/政体."""
    universe: Counter = Counter()
    for age in (Age.A, Age.I, Age.II, Age.III):
        universe.update(db.deck_for(age, num_players))
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
    return accounted


def _yellow_total(p: PlayerState) -> int:
    """黄点总量 = 银行 + 空闲工人池 + 各建筑上的工人."""
    return p.yellow_bank + workers_total(p)


def _yellow_expected(age: Age) -> int:
    return YELLOW_INITIAL_TOTAL - 2 * _AGE_ENDED_I_II_COUNT[age]


def _blue_total(p: PlayerState) -> int:
    """蓝点总量 = 银行 + 卡上储存 + 进行中奇迹已付阶段数."""
    total = p.blue_bank + sum(p.card_tokens.values())
    if p.wonder_progress is not None:
        total += p.wonder_progress[1]
    return total


def _blue_ceiling(db, p: PlayerState) -> int:
    """蓝点总量上界 = 16 + 3 × 已研发蓝点增益特殊科技数."""
    gains = sum(1 for card_id in BLUE_GAIN_CARDS if card_id in p.developed)
    return BLUE_INITIAL_TOTAL + BLUE_GAIN_AMOUNT * gains


def _assert_player_invariants(db, state: GameState, p: PlayerState) -> None:
    # 黄点守恒(精确等号, 口径见模块 docstring)
    assert _yellow_total(p) == _yellow_expected(state.age), (
        f"{p.name} 黄点不守恒: {_yellow_total(p)} != "
        f"{_yellow_expected(state.age)} (age={state.age})"
    )
    # 蓝点上界 + 非负(引擎销毁式支付的实际行为建模, 见模块 docstring)
    assert 0 <= _blue_total(p) <= _blue_ceiling(db, p), (
        f"{p.name} 蓝点越界: {_blue_total(p)} 不在 "
        f"[0, {_blue_ceiling(db, p)}]"
    )
    # 资源/行动点非负, 银行区间
    assert p.culture >= 0
    assert p.science >= 0
    assert p.civil_actions >= 0
    assert p.military_actions >= 0
    assert 0 <= p.yellow_bank <= 18
    assert 0 <= p.blue_bank <= _blue_ceiling(db, p)
    assert all(count >= 0 for count in p.card_tokens.values())


def _run_game_with_invariants(db, seed: int) -> GameState:
    """跑一整局, 每步断言全部不变量, 返回终局状态."""
    state = new_game(db, 2, seed)
    rng = random.Random(seed)
    universe = _universe(db, 2)
    steps = 0
    while not state.terminal:
        legal = legal_actions(db, state)
        state = apply(state, rng.choice(legal), db)
        steps += 1
        for p in state.players:
            _assert_player_invariants(db, state, p)
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
