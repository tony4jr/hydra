"""영상 수집 — 신규 (최신순) + 인기 (조회수순)."""
from datetime import datetime, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Brand, Keyword, Video


def collect_new_videos(db: Session, brand_id: int, max_per_keyword: int = 50) -> list[Video]:
    """전략 1: 최신순 영상 수집 (4시간마다)."""
    return _collect_videos(db, brand_id, order="date", max_per_keyword=max_per_keyword)


def collect_popular_videos(db: Session, brand_id: int, max_per_keyword: int = 50) -> list[Video]:
    """전략 2: 조회수순 영상 수집 (1일 1회)."""
    return _collect_videos(db, brand_id, order="viewCount", max_per_keyword=max_per_keyword)


def collect_initial_videos(db: Session, brand_id: int, max_per_keyword: int = 500) -> list[Video]:
    """초기 세팅: 조회수순 대량 수집."""
    return _collect_videos(db, brand_id, order="viewCount", max_per_keyword=max_per_keyword)


def _collect_videos(db: Session, brand_id: int, order: str, max_per_keyword: int) -> list[Video]:
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
            from hydra.collection.youtube_api import search_videos, enrich_videos

            results = search_videos(kw.text, max_results=max_per_keyword, order=order)

            # 중복 체크용 — 이미 DB에 있는 video_id 필터
            video_ids = [r["video_id"] for r in results]
            existing_ids = {
                v.id for v in db.query(Video.id).filter(Video.id.in_(video_ids)).all()
            } if video_ids else set()

            new_results = [r for r in results if r["video_id"] not in existing_ids]
            if not new_results:
                kw.last_searched_at = datetime.now(UTC)
                continue

            # 메타데이터 보강
            new_ids = [r["video_id"] for r in new_results]
            metadata = enrich_videos(new_ids)

            kw_collected = 0
            for v_data in new_results:
                vid = v_data.get("video_id", "")
                if not vid:
                    continue

                meta = metadata.get(vid, {})

                # published_at 파싱
                pub_str = v_data.get("published_at")
                published = None
                if pub_str:
                    try:
                        published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass

                video = Video(
                    id=vid,
                    url=f"https://www.youtube.com/watch?v={vid}",
                    title=v_data.get("title", ""),
                    channel_id=v_data.get("channel_id", ""),
                    channel_title=v_data.get("channel_title", ""),
                    description=v_data.get("description", ""),
                    view_count=meta.get("view_count", 0),
                    like_count=meta.get("like_count", 0),
                    comment_count=meta.get("comment_count", 0),
                    duration_sec=meta.get("duration_sec"),
                    published_at=published,
                    is_short=meta.get("is_short", False),
                    comments_enabled=meta.get("comments_enabled", True),
                    keyword_id=kw.id,
                    status="available",
                )
                db.add(video)
                collected.append(video)
                kw_collected += 1

            kw.last_searched_at = datetime.now(UTC)
            kw.total_videos_found = (kw.total_videos_found or 0) + kw_collected
        except Exception as e:
            print(f"[VideoCollector] Error for keyword '{kw.text}': {e}")
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
