"""Low-level YouTube page actions — human-like interactions.

Spec Part 7: typing simulation, scrolling, clicking, watching.
All delays use random ranges to mimic real behavior.
"""

import asyncio
import random
from playwright.async_api import Page

from hydra.core.config import settings
from hydra.core.logger import get_logger
from worker.mouse import human_click  # re-export for callers using actions module

log = get_logger("actions")


def _paste_modifier() -> str:
    """Choose paste modifier based on the browser's spoofed OS (not host OS).

    AdsPower profiles can emulate any OS; the modifier must match
    `settings.adspower_profile_os` so the target page sees a
    consistent OS + keyboard combo.
    """
    return "Meta" if settings.adspower_profile_os.lower() == "mac" else "Control"


async def random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """Human-like random delay."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def type_human(page: Page, selector: str, text: str, paste: bool = False):
    """Type text with human-like delays.

    Spec 7.5:
    - 80% clipboard paste, 20% char-by-char
    - Typing: 50~200ms per char
    """
    el = page.locator(selector)
    await el.click()
    await random_delay(1.0, 3.0)  # "thinking"

    if paste:
        # Clipboard paste
        await page.evaluate(f"navigator.clipboard.writeText({repr(text)})")
        await page.keyboard.press(f"{_paste_modifier()}+v")
    else:
        # Char-by-char
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.05, 0.20))

    await random_delay(0.5, 2.0)  # "re-reading"


async def scroll_page(page: Page, scrolls: int = 3, direction: str = "down"):
    """Scroll page with human-like pauses."""
    for _ in range(scrolls):
        delta = random.randint(300, 800)
        if direction == "up":
            delta = -delta
        await page.mouse.wheel(0, delta)
        await random_delay(1.0, 4.0)


async def scroll_to_comments(page: Page):
    """Scroll down to YouTube comments section."""
    # YouTube loads comments lazily, need to scroll past description
    for _ in range(5):
        await page.mouse.wheel(0, random.randint(400, 700))
        await random_delay(1.5, 3.0)

        # Check if comments loaded
        comments = page.locator("#comments #contents ytd-comment-thread-renderer")
        if await comments.count() > 0:
            return True

    log.warning("Comments section not found after scrolling")
    return False


async def watch_video(page: Page, duration_sec: int):
    """Watch video for given duration with occasional interactions.

    Spec 7.4: during watch — 20% scroll to comments, 10% expand description,
    5% pause briefly, 3% change quality.
    """
    elapsed = 0
    chunk = min(duration_sec, 15)

    while elapsed < duration_sec:
        wait = min(chunk, duration_sec - elapsed)
        await asyncio.sleep(wait)
        elapsed += wait

        # Random mid-watch action
        roll = random.random()
        if roll < 0.05:
            # Pause briefly
            await page.keyboard.press("k")
            await random_delay(2.0, 5.0)
            await page.keyboard.press("k")
        elif roll < 0.15:
            # Scroll to comments and back
            await page.mouse.wheel(0, random.randint(500, 1000))
            await random_delay(2.0, 5.0)
            await page.mouse.wheel(0, -random.randint(500, 1000))


async def click_like_button(page: Page, target: str = "video") -> bool:
    """Click like button on video or comment.

    Returns True if successful.
    """
    try:
        if target == "video":
            btn = page.locator(
                "#top-level-buttons-computed ytd-toggle-button-renderer:first-child button,"
                "like-button-view-model button"
            ).first
        else:
            # Comment like — target should be the comment element selector
            btn = page.locator(target).locator("#like-button button").first

        await btn.scroll_into_view_if_needed()
        await random_delay(0.5, 1.5)
        await btn.click()
        await random_delay(1.0, 2.0)
        return True
    except Exception as e:
        log.warning(f"Like button click failed: {e}")
        return False


async def post_comment(page: Page, text: str) -> str | None:
    """Type and submit a comment.

    Spec 7.5: click box → think → paste/type → re-read → submit → confirm.
    Returns youtube_comment_id if captured, empty string if posted but ID unknown, None on failure.
    """
    try:
        # Click comment input placeholder
        placeholder = page.locator("#simplebox-placeholder, #placeholder-area")
        await placeholder.first.click()
        await random_delay(1.0, 3.0)

        # Type into active input
        input_box = page.locator("#contenteditable-root")
        await input_box.first.click()

        # 80% paste, 20% type
        use_paste = random.random() < 0.80
        if use_paste:
            await page.evaluate(f"navigator.clipboard.writeText({repr(text)})")
            await page.keyboard.press(f"{_paste_modifier()}+v")
        else:
            for char in text:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.05, 0.20))

        await random_delay(1.0, 3.0)  # re-read

        # Submit
        submit = page.locator("#submit-button, tp-yt-paper-button#submit-button")
        await submit.first.click()
        await random_delay(2.0, 4.0)  # confirm

        # Try to capture youtube_comment_id from DOM
        comment_id = await _extract_new_comment_id(page)

        log.info(f"Comment posted ({len(text)} chars, id={comment_id or 'unknown'})")
        return comment_id if comment_id else ""

    except Exception as e:
        log.error(f"Comment post failed: {e}")
        return None


async def post_reply(page: Page, comment_selector: str, text: str) -> str | None:
    """Reply to an existing comment.

    Returns youtube_comment_id if captured, empty string if posted but ID unknown, None on failure.
    """
    try:
        comment = page.locator(comment_selector)

        # Click reply button
        reply_btn = comment.locator("#reply-button-end button, button.yt-spec-button-shape-next")
        await reply_btn.first.click()
        await random_delay(1.0, 2.0)

        # Type reply
        reply_box = comment.locator("#contenteditable-root")
        await reply_box.first.click()

        use_paste = random.random() < 0.80
        if use_paste:
            await page.evaluate(f"navigator.clipboard.writeText({repr(text)})")
            await page.keyboard.press(f"{_paste_modifier()}+v")
        else:
            for char in text:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.05, 0.20))

        await random_delay(1.0, 3.0)

        # Submit reply
        submit = comment.locator("#submit-button")
        await submit.first.click()
        await random_delay(2.0, 4.0)

        # Try to capture reply ID
        comment_id = await _extract_new_comment_id(page)

        log.info(f"Reply posted ({len(text)} chars, id={comment_id or 'unknown'})")
        return comment_id if comment_id else ""

    except Exception as e:
        log.error(f"Reply post failed: {e}")
        return None


async def handle_ad(page: Page):
    """Handle YouTube pre-roll ads.

    Spec 7.4: 60% skip after 5s, 25% watch full, 15% back.
    """
    try:
        # Wait briefly for ad
        skip_btn = page.locator(".ytp-skip-ad-button, .ytp-ad-skip-button-modern")
        ad_overlay = page.locator(".ytp-ad-player-overlay")

        # Check if ad is playing
        if not await ad_overlay.is_visible(timeout=3000):
            return  # No ad

        roll = random.random()

        if roll < 0.60:
            # Wait for skip button then skip
            try:
                await skip_btn.wait_for(state="visible", timeout=10000)
                await random_delay(0.5, 2.0)
                await skip_btn.click()
            except Exception:
                pass  # Skip button never appeared, ad was short
        elif roll < 0.85:
            # Watch full ad (wait for it to end)
            await asyncio.sleep(random.uniform(15, 30))
        else:
            # Back out (annoyed)
            await page.go_back()
            await random_delay(1.0, 2.0)

    except Exception:
        pass  # No ad or ad already gone


async def _extract_new_comment_id(page: Page) -> str | None:
    """Try to extract the youtube_comment_id of the most recently posted comment.

    YouTube renders new comments at the top of the list after posting.
    """
    try:
        newest = page.locator("ytd-comment-renderer").first
        comment_id = await newest.get_attribute("data-comment-id")
        return comment_id
    except Exception:
        return None


async def check_ghost(page: Page, youtube_comment_id: str) -> str:
    """Check if a comment is visible (ghost detection).

    Spec 8.4: DOM check during like boost visit.
    Returns: 'visible' | 'suspicious'
    """
    try:
        await scroll_to_comments(page)
        # Look for our comment by its ID in the DOM
        comment = page.locator(f"[data-comment-id='{youtube_comment_id}']")
        if await comment.count() > 0:
            return "visible"

        # Try scrolling more
        for _ in range(3):
            await scroll_page(page, scrolls=2)
            await random_delay(1.0, 2.0)
            if await comment.count() > 0:
                return "visible"

        return "suspicious"

    except Exception as e:
        log.warning(f"Ghost check error: {e}")
        return "suspicious"
