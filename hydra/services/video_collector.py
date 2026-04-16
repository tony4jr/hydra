from datetime import datetime, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Brand, Keyword, Video


def collect_videos_for_brand(db: Session, brand_id: int, max_per_keyword: int = 10) -> list[dict]:
    """브랜드의 타겟 키워드로 YouTube 영상 수집.

    실제 YouTube API 호출은 기존 hydra.collection.youtube_api 모듈 사용.
    이 함수는 수집된 데이터를 DB에 저장하는 역할.
    """
    brand = db.get(Brand, brand_id)
    if not brand:
        return []

    keywords = db.query(Keyword).filter(
        Keyword.brand_id == brand_id,
        Keyword.status == "active",
    ).all()

    collected = []
    for kw in keywords:
        try:
            # YouTube API 호출은 별도 모듈 — 여기서는 키워드 검색 시간만 업데이트
            kw.last_searched_at = datetime.now(UTC)
            collected.append({"keyword_id": kw.id, "keyword": kw.text})
        except Exception:
            continue

    db.commit()
    return collected


def add_video_manually(db: Session, url: str, keyword_id: int | None = None) -> Video | None:
    """URL로 영상 수동 추가."""
    from hydra.services.campaign_service import extract_video_id
    video_id = extract_video_id(url)
    if not video_id:
        return None

    existing = db.get(Video, video_id)
    if existing:
        return existing

    video = Video(
        id=video_id,
        url=url,
        keyword_id=keyword_id,
        status="available",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video
