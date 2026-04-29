"""간단한 in-memory TTL 캐시.

PR-2b-1 — dashboard_metrics 의 30s 캐싱용. 외부 의존성 없음.

설계 결정 (CLAUDE.md/PR-2 사전점검):
- lock 없음. Python GIL 이 dict 단일 op 보호.
  race 발생 시 최악은 compute 중복. 데이터 손상 0.
- 30s TTL × 10s polling 환경 → 평균 3 hit/cache.
  동시 miss 확률 매우 낮아 lock 비용 불필요.
- Redis 등 외부 캐시는 운영 인프라 변경 — YAGNI.
"""
from __future__ import annotations

import time
from typing import Any, Callable

_store: dict[str, tuple[float, Any]] = {}


def cached(key: str, ttl: int, compute: Callable[[], Any]) -> Any:
    """key 의 값을 ttl 초 동안 캐시. miss 시 compute() 호출.

    Args:
        key: 캐시 키. 호출자가 namespace 책임.
        ttl: 만료 초.
        compute: miss 시 호출되는 무인자 함수.

    Returns:
        캐시된 값 또는 compute() 결과.
    """
    now = time.time()
    entry = _store.get(key)
    if entry and now - entry[0] < ttl:
        return entry[1]
    value = compute()
    _store[key] = (now, value)
    return value


def invalidate(key: str | None = None) -> None:
    """전체 캐시 또는 특정 key 무효화.

    Args:
        key: None 이면 전체 clear, 문자열이면 해당 key 만 제거.
    """
    if key is None:
        _store.clear()
    else:
        _store.pop(key, None)


def _peek(key: str) -> tuple[float, Any] | None:
    """테스트용 — 캐시 entry 직접 조회. 프로덕션 코드에서 사용 X."""
    return _store.get(key)
