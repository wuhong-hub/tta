"""SplitMix64 纯函数随机数测试."""

import pytest

from tta.engine.rng import rng_below, rng_shuffle


def test_deterministic() -> None:
    assert rng_below(42, 100) == rng_below(42, 100)


def test_state_advances() -> None:
    s1, _ = rng_below(42, 100)
    s2, _ = rng_below(s1, 100)
    assert s1 != 42 and s2 != s1


def test_bound() -> None:
    state = 7
    for _ in range(200):
        state, v = rng_below(state, 6)
        assert 0 <= v < 6


def test_invalid_bound() -> None:
    with pytest.raises(ValueError):
        rng_below(1, 0)


def test_shuffle_is_permutation_and_deterministic() -> None:
    items = [f"c{i}" for i in range(20)]
    s1, a = rng_shuffle(42, items)
    s2, b = rng_shuffle(42, items)
    assert (s1, a) == (s2, b)
    assert sorted(a) == sorted(items)
    assert a != items  # 20 个元素原序概率可忽略


def test_shuffle_empty_and_single() -> None:
    _, empty = rng_shuffle(1, [])
    assert empty == []
    _, one = rng_shuffle(1, ["x"])
    assert one == ["x"]
