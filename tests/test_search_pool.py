"""search_pool 유틸 테스트."""
import random
from pathlib import Path


def test_age_to_bucket_boundaries():
    from worker.search_pool import age_to_bucket
    assert age_to_bucket(18) == "20s"
    assert age_to_bucket(29) == "20s"
    assert age_to_bucket(30) == "30s"
    assert age_to_bucket(39) == "30s"
    assert age_to_bucket(40) == "40s"
    assert age_to_bucket(49) == "40s"
    assert age_to_bucket(50) == "50s"
    assert age_to_bucket(59) == "50s"
    assert age_to_bucket(60) == "60s"
    assert age_to_bucket(75) == "60s"


def test_pick_returns_string_from_pool():
    from worker.search_pool import pick, _load_pool
    pool = _load_pool()
    assert pool, "pool should load from JSON"
    for age in [22, 31, 45, 55, 65]:
        q = pick(age)
        assert isinstance(q, str) and q


def test_pick_respects_age_bucket():
    """20 대에 20s 풀에서만 나와야 함."""
    from worker.search_pool import pick, _load_pool
    pool = _load_pool()
    s20 = set(pool.get("20s", []))
    rng = random.Random(0)
    random.seed(0)
    for _ in range(30):
        q = pick(25)
        assert q in s20, f"query '{q}' not in 20s pool"


def test_pick_many_unique_and_count():
    from worker.search_pool import pick_many, _load_pool
    pool = _load_pool()
    n = min(10, len(pool.get("30s", [])))
    out = pick_many(35, n)
    assert len(out) == n
    assert len(set(out)) == n, "should be unique"


def test_pick_fallback_when_bucket_missing(monkeypatch):
    from worker import search_pool as sp
    monkeypatch.setattr(sp, "_load_pool", lambda: {})
    # clear cache
    sp._load_pool.cache_clear() if hasattr(sp._load_pool, "cache_clear") else None
    q = sp.pick(25)
    assert q in sp.SAFE_FALLBACK


def test_pool_size_dict():
    from worker.search_pool import pool_size
    sizes = pool_size()
    assert isinstance(sizes, dict)
    assert "20s" in sizes
    assert sizes["20s"] > 0
