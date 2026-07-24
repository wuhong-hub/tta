"""SplitMix64 纯函数随机数发生器.

状态为单个 64 位整数, 可直接放入 GameState 序列化;
同一 (state, bound) 输入必得同一输出, 保证棋谱可凭 seed 精确重放.
"""

from collections.abc import Sequence

MASK64 = (1 << 64) - 1
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15


def _step(state: int) -> tuple[int, int]:
    """推进状态并输出一个 64 位随机值."""
    state = (state + _GOLDEN_GAMMA) & MASK64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return state, (z ^ (z >> 31)) & MASK64


def rng_below(state: int, bound: int) -> tuple[int, int]:
    """返回 (新状态, [0, bound) 内随机整数). 取模偏差对桌游场景可忽略."""
    if bound <= 0:
        raise ValueError(f"bound must be positive, got {bound}")
    state, z = _step(state)
    return state, z % bound


def rng_shuffle(state: int, items: Sequence[str]) -> tuple[int, list[str]]:
    """Fisher-Yates 洗牌, 返回 (新状态, 新列表), 不改动入参."""
    result = list(items)
    for i in range(len(result) - 1, 0, -1):
        state, j = rng_below(state, i + 1)
        result[i], result[j] = result[j], result[i]
    return state, result
