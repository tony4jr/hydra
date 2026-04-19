"""유튜브/Google 검색 쿼리 풀 — age bucket 별로 랜덤 픽.

data/search_keywords.json 을 프로세스 수명 동안 한 번만 로드하여 메모리 상주.
세션 중 `pick(age)` 호출마다 해당 버킷에서 임의 쿼리 반환.

설계 원칙:
- **per-account seed 사용 안 함** — 같은 계정이 여러 세션에서 서로 다른 쿼리 쓰게
- age 매핑: 18-29 → 20s / 30-39 → 30s / 40-49 → 40s / 50-59 → 50s / 60+ → 60s
- pool 로드 실패하거나 bucket 비어있으면 SAFE_FALLBACK 사용 (워커 죽지 않게)
"""
import json
import random
from functools import lru_cache
from pathlib import Path

from hydra.core.logger import get_logger

log = get_logger("search_pool")

POOL_PATH = Path(__file__).resolve().parent.parent / "data" / "search_keywords.json"

# 풀 로드 실패 시 기본 쿼리 (워커가 죽지 않도록)
SAFE_FALLBACK = ["오늘 날씨", "맛집 추천", "영화 추천", "뉴스", "운동법"]


def age_to_bucket(age: int) -> str:
    """나이를 age bucket key 로 변환."""
    if age < 30:
        return "20s"
    if age < 40:
        return "30s"
    if age < 50:
        return "40s"
    if age < 60:
        return "50s"
    return "60s"


@lru_cache(maxsize=1)
def _load_pool() -> dict[str, list[str]]:
    """JSON 풀 로드. 프로세스 단 1회."""
    try:
        data = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"Failed to load search pool from {POOL_PATH}: {e}")
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def pick(age: int) -> str:
    """age 에 맞는 버킷에서 임의 쿼리 1개 반환."""
    bucket = age_to_bucket(age)
    pool = _load_pool()
    queries = pool.get(bucket) or []
    if not queries:
        return random.choice(SAFE_FALLBACK)
    return random.choice(queries)


def pick_many(age: int, n: int) -> list[str]:
    """age 버킷에서 n 개 유니크 쿼리 반환 (풀이 작으면 중복 허용)."""
    bucket = age_to_bucket(age)
    pool = _load_pool()
    queries = pool.get(bucket) or []
    if not queries:
        return [random.choice(SAFE_FALLBACK) for _ in range(n)]
    if n >= len(queries):
        return list(queries)
    return random.sample(queries, n)


def pool_size(age: int | None = None) -> int | dict[str, int]:
    """풀 크기 확인 (디버그용). age 주면 그 버킷 크기, 없으면 전체 dict."""
    pool = _load_pool()
    if age is None:
        return {k: len(v) for k, v in pool.items()}
    return len(pool.get(age_to_bucket(age)) or [])
