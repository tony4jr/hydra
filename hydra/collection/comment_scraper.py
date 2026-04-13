"""Scrape real YouTube comments for AI training dataset.

MKT_TUBE ScanComment pattern:
- Visit video → scroll comments → extract all → save to DB
- Used as few-shot examples for Claude comment generation
"""

import hashlib
from datetime import datetime, timezone

from playwright.async_api import Page
from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.browser import actions
from hydra.db.models import ScrapedComment

log = get_logger("scraper")


async def scrape_comments(page: Page, video_id: str, max_comments: int = 50) -> list[dict]:
    """Scrape comments from current page.

    Assumes page is already on a YouTube video.
    """
    # Scroll to load comments
    found = await actions.scroll_to_comments(page)
    if not found:
        return []

    # Keep scrolling to load more
    for _ in range(5):
        await actions.scroll_page(page, scrolls=3)
        await actions.random_delay(1, 2)

    comments = []
    elements = page.locator("ytd-comment-thread-renderer")
    count = await elements.count()

    for i in range(min(count, max_comments)):
        try:
            el = elements.nth(i)

            author = await el.locator("#author-text span").first.text_content()
            content = await el.locator("#content-text").first.text_content()
            time_text = await el.locator(".published-time-text a").first.text_content()

            # Try to get like count
            like_text = ""
            try:
                like_text = await el.locator("#vote-count-middle").first.text_content()
            except Exception:
                pass

            like_count = 0
            if like_text:
                like_text = like_text.strip().replace(",", "")
                if like_text.endswith("천"):
                    like_count = int(float(like_text[:-1]) * 1000)
                elif like_text.endswith("만"):
                    like_count = int(float(like_text[:-1]) * 10000)
                elif like_text.isdigit():
                    like_count = int(like_text)

            author_channel = ""
            try:
                author_channel = await el.locator("#author-text").first.get_attribute("href")
            except Exception:
                pass

            if content and content.strip():
                comments.append({
                    "video_id": video_id,
                    "author_name": (author or "").strip(),
                    "author_channel": (author_channel or "").strip(),
                    "content": content.strip(),
                    "like_count": like_count,
                    "time_text": (time_text or "").strip(),
                })

        except Exception:
            continue

    log.info(f"Scraped {len(comments)} comments from video {video_id}")
    return comments


def save_scraped_comments(db: Session, comments: list[dict]) -> int:
    """Save scraped comments to DB with dedup."""
    saved = 0
    for c in comments:
        content_hash = hashlib.md5(c["content"].encode()).hexdigest()

        # Dedup check
        existing = (
            db.query(ScrapedComment)
            .filter(ScrapedComment.content_hash == content_hash)
            .first()
        )
        if existing:
            continue

        record = ScrapedComment(
            video_id=c["video_id"],
            author_name=c["author_name"],
            author_channel=c["author_channel"],
            content=c["content"],
            content_hash=content_hash,
            like_count=c["like_count"],
            time_text=c["time_text"],
        )
        db.add(record)
        saved += 1

    db.commit()
    log.info(f"Saved {saved} new comments (skipped {len(comments) - saved} dupes)")
    return saved


def get_training_comments(db: Session, limit: int = 20, min_likes: int = 5) -> list[str]:
    """Get high-quality comments for few-shot prompts."""
    comments = (
        db.query(ScrapedComment)
        .filter(
            ScrapedComment.like_count >= min_likes,
            ScrapedComment.used_for_training == False,
        )
        .order_by(ScrapedComment.like_count.desc())
        .limit(limit)
        .all()
    )
    return [c.content for c in comments]
