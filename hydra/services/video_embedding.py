"""Phase 1 — 영상 임베딩 분류 (Stage A).

OpenAI text-embedding-3-small (싸고 빠름, $0.02/1k 영상).
타겟별 reference text 한 번 임베딩 → 캐시 → 영상 텍스트와 cosine similarity.

embedding_threshold (default 0.65) 미만이면 'blacklisted' (low_embedding).
"""
from __future__ import annotations

import logging
import math
from typing import Iterable

from sqlalchemy.orm import Session

from hydra.db.models import Video, TargetCollectionConfig

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Reference embedding 캐시 — 메모리 (target_id → vector)
# ─────────────────────────────────────────────────────────────────

_REF_CACHE: dict[int, tuple[str, list[float]]] = {}


def _get_openai_key() -> str | None:
    """OpenAI API 키 — system_config 또는 .env 에서."""
    try:
        from hydra.db.session import SessionLocal
        from hydra.db.models import SystemConfig
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == "openai_api_key").first()
            if row and row.value:
                return row.value
        finally:
            db.close()
    except Exception:
        pass
    import os
    return os.getenv("OPENAI_API_KEY")


def _embed_text(text: str) -> list[float] | None:
    """OpenAI text-embedding-3-small 호출. 실패 시 None."""
    key = _get_openai_key()
    if not key:
        log.warning("OpenAI key missing — embedding skip")
        return None
    if not text or not text.strip():
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        # text-embedding-3-small: dim=1536, $0.02/1M tokens
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],  # 토큰 제한 회피
        )
        return resp.data[0].embedding
    except Exception as e:
        log.error(f"OpenAI embedding failed: {e}")
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """0~1 (텍스트 임베딩은 일반적으로 양수)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_target_reference_embedding(
    db: Session,
    target_id: int,
) -> list[float] | None:
    """타겟의 reference text 를 임베딩. 캐시 우선."""
    cfg = db.get(TargetCollectionConfig, target_id)
    if cfg is None or not cfg.embedding_reference_text:
        return None

    ref_text = cfg.embedding_reference_text
    cached = _REF_CACHE.get(target_id)
    if cached and cached[0] == ref_text:
        return cached[1]

    vec = _embed_text(ref_text)
    if vec:
        _REF_CACHE[target_id] = (ref_text, vec)
    return vec


def compute_embedding_score(
    db: Session,
    video: Video,
    target_id: int,
) -> float | None:
    """영상의 임베딩 점수 (0~1). 실패 시 None.

    영상 텍스트 = 제목 + 설명 첫 500자.
    """
    ref_vec = get_target_reference_embedding(db, target_id)
    if ref_vec is None:
        return None

    title = video.title or ""
    desc = (video.description or "")[:500]
    video_text = f"{title} {desc}".strip()
    if not video_text:
        return None

    video_vec = _embed_text(video_text)
    if video_vec is None:
        return None

    return _cosine_similarity(ref_vec, video_vec)


def classify_by_embedding(
    db: Session,
    video: Video,
    target_id: int,
) -> tuple[bool, str | None]:
    """임베딩 점수 계산 + threshold 검사.

    Returns:
        (passed, blacklist_reason).
        passed=True 면 video.embedding_score 채워짐.
        passed=False 면 video.state='blacklisted' + reason.
    """
    score = compute_embedding_score(db, video, target_id)
    if score is None:
        # 임베딩 실패 (키 없거나 API 에러) — 정책: 통과시킴 (false negative 보다 낫음)
        log.debug(f"embedding skip for {video.id} (no score)")
        return True, None

    video.embedding_score = score

    cfg = db.get(TargetCollectionConfig, target_id)
    threshold = (cfg.embedding_threshold if cfg else 0.65) or 0.65

    if score < threshold:
        return False, f"low_embedding:{score:.3f}"

    return True, None


def reset_reference_cache(target_id: int | None = None) -> None:
    """Reference text 변경 시 호출 — 캐시 무효화."""
    if target_id is None:
        _REF_CACHE.clear()
    else:
        _REF_CACHE.pop(target_id, None)
