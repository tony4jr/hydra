"""_cache.py 단위 테스트.

PR-2b-1.
"""
from __future__ import annotations

import time

from hydra.services import _cache


def setup_function() -> None:
    """각 테스트 전 캐시 초기화."""
    _cache.invalidate()


def test_cache_hit_returns_cached_value() -> None:
    calls = {"count": 0}
    def compute() -> int:
        calls["count"] += 1
        return 42

    v1 = _cache.cached("k1", ttl=60, compute=compute)
    v2 = _cache.cached("k1", ttl=60, compute=compute)

    assert v1 == 42
    assert v2 == 42
    assert calls["count"] == 1  # 두 번째는 캐시에서


def test_cache_miss_recomputes_after_ttl() -> None:
    calls = {"count": 0}
    def compute() -> int:
        calls["count"] += 1
        return calls["count"]

    v1 = _cache.cached("k1", ttl=1, compute=compute)
    time.sleep(1.1)
    v2 = _cache.cached("k1", ttl=1, compute=compute)

    assert v1 == 1
    assert v2 == 2
    assert calls["count"] == 2


def test_invalidate_specific_key() -> None:
    _cache.cached("k1", ttl=60, compute=lambda: "v1")
    _cache.cached("k2", ttl=60, compute=lambda: "v2")

    _cache.invalidate("k1")

    assert _cache._peek("k1") is None
    assert _cache._peek("k2") is not None


def test_invalidate_all() -> None:
    _cache.cached("k1", ttl=60, compute=lambda: "v1")
    _cache.cached("k2", ttl=60, compute=lambda: "v2")

    _cache.invalidate()

    assert _cache._peek("k1") is None
    assert _cache._peek("k2") is None


def test_different_keys_independent() -> None:
    v1 = _cache.cached("k1", ttl=60, compute=lambda: "a")
    v2 = _cache.cached("k2", ttl=60, compute=lambda: "b")

    assert v1 == "a"
    assert v2 == "b"


def test_compute_exception_does_not_cache() -> None:
    calls = {"count": 0}
    def fail() -> int:
        calls["count"] += 1
        raise ValueError("boom")

    try:
        _cache.cached("k1", ttl=60, compute=fail)
    except ValueError:
        pass
    try:
        _cache.cached("k1", ttl=60, compute=fail)
    except ValueError:
        pass

    assert calls["count"] == 2  # 둘 다 호출됨, 캐시 안 됨
