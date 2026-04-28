"""Smart video collection — multi-order search + long-tail expansion.

설계:
  Pass 1 (원본 키워드): 3 정렬 (viewCount, date, relevance) × 5년치
  Pass 2 (long-tail): 키워드 변형 N개 × 2 정렬 (viewCount, date) × 5년치
  Pass 3 (매일 신규): publishedAfter=어제 모든 키워드+변형

기존 video_collector.py 와 공존 — feature flag 로 선택적 활성화.
시간 슬라이싱은 사용 안 함 (search.list 의 ~500개 상한 + 정렬·변형 다양화로 우회).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, UTC
from typing import Iterable

from sqlalchemy.orm import Session

from hydra.collection.youtube_api import search_videos, enrich_videos
from hydra.db.models import Brand, Keyword, Video

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Collection depth profiles — Brand.collection_depth 와 매칭
# ─────────────────────────────────────────────────────────────────

DEPTH_PROFILES = {
    "quick": {
        "publishedAfter_years": 1,
        "orders_for_root": ["viewCount"],
        "orders_for_variants": ["viewCount"],
        "longtail_count": 0,
    },
    "standard": {
        "publishedAfter_years": 5,
        "orders_for_root": ["viewCount", "date", "relevance"],
        "orders_for_variants": ["viewCount", "date"],
        "longtail_count": 5,
    },
    "deep": {
        "publishedAfter_years": 5,
        "orders_for_root": ["viewCount", "date", "relevance"],
        "orders_for_variants": ["viewCount", "date"],
        "longtail_count": 15,
    },
    "max": {
        "publishedAfter_years": 10,
        "orders_for_root": ["viewCount", "date", "relevance"],
        "orders_for_variants": ["viewCount", "date", "relevance"],
        "longtail_count": 30,
    },
}


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _published_after_iso(years: int) -> str:
    return (datetime.now(UTC) - timedelta(days=365 * years)).isoformat()


def _matches_keyword(video_title: str, video_desc: str, keyword: str) -> bool:
    """제목 또는 설명에 키워드가 포함되는지 (대소문자 무시)."""
    if not keyword:
        return True
    kw_l = keyword.lower()
    return kw_l in (video_title or "").lower() or kw_l in (video_desc or "").lower()


def _save_videos(
    db: Session,
    raw_results: list[dict],
    keyword: Keyword,
    discovered_via: str,
    discovery_keyword: str,
    require_keyword_match: bool = True,
) -> int:
    """raw search 결과를 DB에 저장. 이미 존재하면 skip. 신규 개수 리턴."""
    if not raw_results:
        return 0

    video_ids = [r["video_id"] for r in raw_results if r.get("video_id")]
    if not video_ids:
        return 0

    # dedup 1차 — 이미 풀에 있는 영상
    existing_ids = {
        v.id for v in db.query(Video.id).filter(Video.id.in_(video_ids)).all()
    }
    new_results = [r for r in raw_results if r["video_id"] not in existing_ids]
    if not new_results:
        return 0

    # 메타데이터 보강 (조회수, 댓글 활성화, duration 등)
    new_ids = [r["video_id"] for r in new_results]
    metadata = enrich_videos(new_ids)

    saved = 0
    for v_data in new_results:
        vid = v_data["video_id"]
        meta = metadata.get(vid, {})

        title = v_data.get("title", "")
        desc = v_data.get("description", "")

        # 키워드 매칭 검증 (제목/설명에 실제로 등장)
        if require_keyword_match and not _matches_keyword(title, desc, discovery_keyword):
            continue

        # 댓글 비활성 영상 skip
        if meta.get("comments_enabled") is False:
            continue

        # published_at 파싱
        pub_str = v_data.get("published_at")
        published = None
        if pub_str:
            try:
                published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        view_count = meta.get("view_count", 0) or 0
        # popularity_score: log10 정규화 (0 ~ 1 사이, 1000만뷰 ≈ 0.7)
        import math
        popularity = math.log10(view_count + 1) / 7.0 if view_count > 0 else 0.0

        video = Video(
            id=vid,
            url=f"https://www.youtube.com/watch?v={vid}",
            title=title,
            channel_id=v_data.get("channel_id", ""),
            channel_title=v_data.get("channel_title", ""),
            description=desc,
            view_count=view_count,
            like_count=meta.get("like_count", 0),
            comment_count=meta.get("comment_count", 0),
            duration_sec=meta.get("duration_sec"),
            published_at=published,
            is_short=meta.get("is_short", False),
            comments_enabled=meta.get("comments_enabled", True),
            keyword_id=keyword.id,
            status="available",
            popularity_score=popularity,
            discovered_via=discovered_via,
            discovery_keyword=discovery_keyword,
        )
        db.add(video)
        saved += 1

    keyword.last_searched_at = datetime.now(UTC)
    keyword.total_videos_found = (keyword.total_videos_found or 0) + saved
    return saved


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def collect_initial_for_brand(db: Session, brand_id: int) -> dict:
    """브랜드 등록 후 1회 호출 — Pass 1 + Pass 2.

    Returns: {"keywords_processed": N, "videos_added": M, "variants_created": V}
    """
    brand = db.get(Brand, brand_id)
    if not brand:
        return {"error": "brand not found"}

    profile = DEPTH_PROFILES.get(brand.collection_depth or "standard", DEPTH_PROFILES["standard"])
    pa_iso = _published_after_iso(profile["publishedAfter_years"])

    # 원본 (variant 가 아닌) 키워드만 처리
    root_keywords = (
        db.query(Keyword)
        .filter(Keyword.brand_id == brand_id, Keyword.status == "active",
                Keyword.is_variant == False)  # noqa: E712
        .all()
    )

    total_added = 0
    total_variants = 0

    for root in root_keywords:
        # Pass 1 — 원본 키워드 멀티 order
        for order in profile["orders_for_root"]:
            try:
                results = search_videos(
                    root.text, max_results=500, order=order,
                    published_after=pa_iso,
                )
                added = _save_videos(
                    db, results, root,
                    discovered_via=f"search_{order}",
                    discovery_keyword=root.text,
                )
                total_added += added
                log.info(f"Pass1 [{root.text}] order={order} → {added} new")
            except Exception as e:
                log.error(f"Pass1 [{root.text}] order={order} failed: {e}")

        db.commit()

        # Pass 2 — Long-tail 변형 생성 + 검색
        if profile["longtail_count"] > 0:
            try:
                from hydra.ai.agents.keyword_agent import expand_keywords
                variants = expand_keywords(db, root, max_count=profile["longtail_count"])
                total_variants += len(variants)
                log.info(f"Pass2 [{root.text}] generated {len(variants)} variants")
            except Exception as e:
                log.error(f"Pass2 [{root.text}] keyword_expand failed: {e}")
                variants = []

            for variant in variants:
                for order in profile["orders_for_variants"]:
                    try:
                        results = search_videos(
                            variant.text, max_results=500, order=order,
                            published_after=pa_iso,
                        )
                        added = _save_videos(
                            db, results, variant,
                            discovered_via=f"longtail_{order}",
                            discovery_keyword=variant.text,
                        )
                        total_added += added
                        log.info(f"Pass2 [{variant.text}] order={order} → {added} new")
                    except Exception as e:
                        log.error(f"Pass2 [{variant.text}] order={order} failed: {e}")
                db.commit()

    return {
        "keywords_processed": len(root_keywords),
        "videos_added": total_added,
        "variants_created": total_variants,
    }


def collect_daily_new(db: Session, brand_id: int, hours: int = 24) -> int:
    """매일 자동 호출 — 신규만 (publishedAfter=어제).

    원본 + 변형 키워드 모두 대상. order=date.
    """
    brand = db.get(Brand, brand_id)
    if not brand:
        return 0

    pa_iso = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    keywords = (
        db.query(Keyword)
        .filter(Keyword.brand_id == brand_id, Keyword.status == "active")
        .all()
    )

    total = 0
    for kw in keywords:
        try:
            results = search_videos(
                kw.text, max_results=50, order='date',
                published_after=pa_iso,
            )
            via = "longtail_date" if kw.is_variant else "search_date"
            added = _save_videos(
                db, results, kw,
                discovered_via=via,
                discovery_keyword=kw.text,
            )
            total += added
        except Exception as e:
            log.error(f"daily_new [{kw.text}] failed: {e}")

    db.commit()
    return total
