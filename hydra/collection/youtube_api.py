"""YouTube Data API v3 — video collection pipeline.

Spec Part 5:
- search.list (keyword) → videos.list (metadata) → DB
- Core keywords: every 4 hours
- Normal keywords: once daily
- Dedup by video_id
- Shorts detection: duration ≤ 60s or /shorts/ in URL
"""

import re
from datetime import datetime, timezone, timedelta

from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.core.enums import VideoStatus, VideoPriority
from hydra.db.models import Video, Keyword

log = get_logger("collection")

# API key rotation state
_key_index = 0


def _get_youtube_service():
    """Build YouTube service with key rotation."""
    global _key_index
    keys = settings.youtube_api_keys
    if not keys:
        raise RuntimeError("No YouTube API keys configured")
    key = keys[_key_index % len(keys)]
    return build("youtube", "v3", developerKey=key)


def _rotate_key():
    """Switch to next API key on quota error."""
    global _key_index
    _key_index += 1
    log.info(f"Rotated to YouTube API key index {_key_index}")


def _parse_duration(iso_duration: str) -> int:
    """Parse ISO 8601 duration (PT1H2M3S) to seconds."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not match:
        return 0
    h, m, s = (int(x or 0) for x in match.groups())
    return h * 3600 + m * 60 + s


def search_videos(keyword_text: str, max_results: int = 50) -> list[dict]:
    """Search YouTube for videos matching keyword. Returns raw items."""
    yt = _get_youtube_service()
    results = []
    next_page = None

    while len(results) < max_results:
        try:
            resp = yt.search().list(
                q=keyword_text,
                part="id,snippet",
                type="video",
                relevanceLanguage="ko",
                regionCode="KR",
                maxResults=min(50, max_results - len(results)),
                pageToken=next_page,
            ).execute()
        except Exception as e:
            if "quotaExceeded" in str(e):
                _rotate_key()
                continue
            raise

        for item in resp.get("items", []):
            if item["id"]["kind"] == "youtube#video":
                results.append({
                    "video_id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "channel_id": item["snippet"]["channelId"],
                    "channel_title": item["snippet"]["channelTitle"],
                    "description": item["snippet"].get("description", ""),
                    "published_at": item["snippet"]["publishedAt"],
                })

        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    return results


def enrich_videos(video_ids: list[str]) -> dict[str, dict]:
    """Fetch detailed metadata for video IDs (batch of 50)."""
    yt = _get_youtube_service()
    enriched = {}

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            resp = yt.videos().list(
                id=",".join(batch),
                part="contentDetails,statistics,status",
            ).execute()
        except Exception as e:
            if "quotaExceeded" in str(e):
                _rotate_key()
                continue
            raise

        for item in resp.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})
            duration = _parse_duration(details.get("duration", ""))

            enriched[vid] = {
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)) if "commentCount" in stats else None,
                "duration_sec": duration,
                "is_short": duration <= 60,
                "comments_enabled": "commentCount" in stats,
            }

    return enriched


def collect_for_keyword(db: Session, keyword: Keyword) -> int:
    """Full pipeline: search → enrich → upsert DB. Returns new video count."""
    log.info(f"Collecting videos for keyword: {keyword.text}")

    raw_results = search_videos(keyword.text)
    if not raw_results:
        log.info(f"No results for '{keyword.text}'")
        return 0

    video_ids = [r["video_id"] for r in raw_results]

    # Filter already existing
    existing = {v.id for v in db.query(Video.id).filter(Video.id.in_(video_ids)).all()}
    new_results = [r for r in raw_results if r["video_id"] not in existing]

    if not new_results:
        log.info(f"All {len(raw_results)} videos already in DB for '{keyword.text}'")
        keyword.last_searched_at = datetime.now(timezone.utc)
        db.commit()
        return 0

    # Enrich new videos
    new_ids = [r["video_id"] for r in new_results]
    metadata = enrich_videos(new_ids)

    # Determine priority
    now = datetime.now(timezone.utc)
    count = 0

    for r in new_results:
        vid = r["video_id"]
        meta = metadata.get(vid, {})

        # Parse published date
        pub_str = r["published_at"]
        try:
            published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            published = None

        # Priority: fresh (24h) = urgent
        priority = VideoPriority.NORMAL
        if published and (now - published) < timedelta(hours=24):
            priority = VideoPriority.URGENT

        # Status
        status = VideoStatus.AVAILABLE
        if meta.get("comments_enabled") is False:
            status = VideoStatus.COMMENTS_DISABLED

        video = Video(
            id=vid,
            url=f"https://www.youtube.com/watch?v={vid}",
            title=r["title"],
            channel_id=r["channel_id"],
            channel_title=r["channel_title"],
            description=r["description"],
            published_at=published,
            view_count=meta.get("view_count"),
            like_count=meta.get("like_count"),
            comment_count=meta.get("comment_count"),
            duration_sec=meta.get("duration_sec"),
            is_short=meta.get("is_short", False),
            comments_enabled=meta.get("comments_enabled", True),
            status=status,
            keyword_id=keyword.id,
            priority=priority,
        )
        db.add(video)
        count += 1

    # Update keyword stats
    keyword.total_videos_found = (keyword.total_videos_found or 0) + count
    keyword.last_searched_at = now
    db.commit()

    log.info(f"Collected {count} new videos for '{keyword.text}' (skipped {len(existing)} existing)")
    return count


def refresh_video_status(db: Session, max_videos: int = 200) -> dict:
    """Re-check status of active/available videos via YouTube API.

    Updates: view_count, like_count, comment_count, comments_enabled, status.
    Returns summary dict.
    """
    videos = (
        db.query(Video)
        .filter(Video.status.in_([VideoStatus.AVAILABLE, VideoStatus.COMMENTS_DISABLED]))
        .order_by(Video.collected_at.desc())
        .limit(max_videos)
        .all()
    )

    if not videos:
        return {"checked": 0, "updated": 0, "removed": 0}

    video_ids = [v.id for v in videos]
    video_map = {v.id: v for v in videos}

    # Batch enrich
    metadata = enrich_videos(video_ids)

    updated = 0
    removed = 0

    # Videos not returned by API = deleted/private
    returned_ids = set(metadata.keys())
    for vid in video_ids:
        if vid not in returned_ids:
            video_map[vid].status = VideoStatus.DELETED
            removed += 1

    # Update metadata for returned videos
    for vid, meta in metadata.items():
        v = video_map.get(vid)
        if not v:
            continue

        changed = False
        if v.view_count != meta.get("view_count"):
            v.view_count = meta["view_count"]
            changed = True
        if v.like_count != meta.get("like_count"):
            v.like_count = meta["like_count"]
            changed = True
        if v.comment_count != meta.get("comment_count"):
            v.comment_count = meta["comment_count"]
            changed = True

        new_enabled = meta.get("comments_enabled", True)
        if v.comments_enabled != new_enabled:
            v.comments_enabled = new_enabled
            v.status = VideoStatus.AVAILABLE if new_enabled else VideoStatus.COMMENTS_DISABLED
            changed = True

        if changed:
            updated += 1

    db.commit()
    log.info(f"Video status refresh: checked={len(video_ids)}, updated={updated}, removed={removed}")
    return {"checked": len(video_ids), "updated": updated, "removed": removed}


def collect_all(db: Session, core_only: bool = False):
    """Run collection for all active keywords.

    Args:
        core_only: If True, only high-priority keywords (for 4-hour cycle).
    """
    from hydra.infra import telegram

    query = db.query(Keyword).filter(Keyword.status == "active")
    if core_only:
        query = query.filter(Keyword.priority >= 8)

    keywords = query.all()
    total_new = 0

    for kw in keywords:
        try:
            n = collect_for_keyword(db, kw)
            total_new += n
        except Exception as e:
            log.error(f"Collection failed for '{kw.text}': {e}")
            telegram.warning(f"영상 수집 실패: {kw.text} — {e}")

    log.info(f"Collection complete: {total_new} new videos from {len(keywords)} keywords")
    if total_new > 0:
        telegram.info(f"영상 수집 완료: {len(keywords)}개 키워드 → {total_new}개 신규 영상")

    return total_new
