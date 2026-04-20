"""Low-level YouTube page actions — human-like interactions.

Spec Part 7: typing simulation, scrolling, clicking, watching.
All delays use random ranges to mimic real behavior.
"""

import asyncio
import contextvars
import random
from playwright.async_api import Page

from hydra.core.config import settings
from hydra.core.logger import get_logger
from worker.mouse import human_click  # re-export for callers using actions module

log = get_logger("actions")


# ─── 세션/계정별 속도 조절 (anti-detection) ──────────────────────────────
# 모든 random_delay 에 곱해지는 배수. persona 별로 0.6~1.8 랜덤 세팅해 세션
# 특유의 "템포" 를 만듦 — 모든 계정이 동일 분포로 움직이면 정규분포 봇 시그니처.
_speed_multiplier: contextvars.ContextVar[float] = contextvars.ContextVar(
    "hydra_speed_multiplier", default=1.0
)
_typing_style: contextvars.ContextVar[str] = contextvars.ContextVar(
    "hydra_typing_style", default="typist"  # typist | paster
)
_activity_multiplier: contextvars.ContextVar[float] = contextvars.ContextVar(
    "hydra_activity_multiplier", default=1.0
)


def set_speed_multiplier(value: float) -> None:
    """Context-local speed multiplier 설정 (session 시작 시 호출).

    value 0.6 = 40% 빠름. value 1.8 = 80% 느림. 합리적 범위: 0.5~2.0.
    """
    _speed_multiplier.set(max(0.3, min(3.0, float(value))))


def get_speed_multiplier() -> float:
    return _speed_multiplier.get()


def set_typing_style(style: str) -> None:
    """Context-local 타이핑 스타일. 'typist' (타이핑) 또는 'paster' (붙여넣기)."""
    if style in ("typist", "paster"):
        _typing_style.set(style)


def get_typing_style() -> str:
    return _typing_style.get()


def set_activity_multiplier(value: float) -> None:
    """Context-local 활동량 배수. 스크롤/숏츠/클릭 반복 횟수에 곱해짐.

    0.5 = 조용한 유저(적게 클릭), 1.5 = 활발한 유저(많이 클릭).
    """
    _activity_multiplier.set(max(0.3, min(3.0, float(value))))


def get_activity_multiplier() -> float:
    return _activity_multiplier.get()


def rep_count(base_min: int, base_max: int) -> int:
    """반복 횟수 선택. activity_multiplier 적용. 최소 1 보장."""
    mult = _activity_multiplier.get()
    lo = max(1, int(base_min * mult))
    hi = max(lo, int(base_max * mult))
    return random.randint(lo, hi)


def _paste_modifier() -> str:
    """Choose paste modifier based on the browser's spoofed OS (not host OS).

    AdsPower profiles can emulate any OS; the modifier must match
    `settings.adspower_profile_os` so the target page sees a
    consistent OS + keyboard combo.
    """
    return "Meta" if settings.adspower_profile_os.lower() == "mac" else "Control"


async def random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """Human-like random delay. 세션의 speed_multiplier 가 적용됨."""
    mult = _speed_multiplier.get()
    await asyncio.sleep(random.uniform(min_sec * mult, max_sec * mult))


def _typing_delay() -> float:
    """한 글자 입력 사이 간격. 로그노말 분포 (사람의 자연 분포와 흡사).

    평균 약 120ms, 꼬리가 길어 가끔 300~500ms pause 발생 — 봇의 균등 분포 회피.
    speed_multiplier 도 적용.
    """
    mult = _speed_multiplier.get()
    # lognormal: mu=-2.2, sigma=0.55 → 평균 ~120ms, 95th ~300ms
    base = random.lognormvariate(-2.2, 0.55)
    return max(0.03, min(0.8, base)) * mult


async def type_human(
    page: Page,
    selector: str,
    text: str,
    paste: bool = False,
    typing_style: str | None = None,
):
    """사람처럼 타이핑. persona.typing_style 전달 시 'paster' 는 clipboard 붙여넣기.

    - 'typist': 한 글자씩 로그노말 간격 (가끔 멍하니 pause, 단어 경계에서 긴 pause)
    - 'paster': 한번에 클립보드 붙여넣기 (마치 옆 창에서 복사한 것처럼)
    - paste=True 가 명시되면 typing_style 무시하고 paste
    """
    from worker.mouse import human_click as _hc

    el = page.locator(selector).first
    try:
        await _hc(el)
    except Exception:
        await el.click()
    await random_delay(0.6, 2.5)  # "thinking"

    # typing_style 명시 안 되면 context 에서 가져옴 (세션 persona 기반)
    effective_style = typing_style or _typing_style.get()
    use_paste = paste or (effective_style == "paster")

    if use_paste:
        # Clipboard paste — fill() 은 instant 라 대신 clipboard API 사용하고
        # 실제 paste 키 이벤트 발생시킴 (keyup 이벤트 트래킹하는 사이트 대응)
        try:
            await page.evaluate(
                f"navigator.clipboard.writeText({repr(text)})"
            )
            await random_delay(0.15, 0.5)
            await page.keyboard.press(f"{_paste_modifier()}+v")
        except Exception:
            # clipboard 권한 없으면 fill 로 폴백
            await el.fill(text)
    else:
        # Char-by-char — 로그노말 간격 + 단어 경계에서 긴 pause + 오타 확률
        from worker.typo import ADJACENT_KEYS
        i = 0
        while i < len(text):
            ch = text[i]
            # 간헐적 오타 (5%) — 인접 키 치고 백스페이스로 수정
            if random.random() < 0.05 and ch in ADJACENT_KEYS:
                wrong = random.choice(ADJACENT_KEYS[ch])
                await page.keyboard.type(wrong)
                await asyncio.sleep(_typing_delay())
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.08, 0.2))
            await page.keyboard.type(ch)
            await asyncio.sleep(_typing_delay())
            # 공백 뒤 (단어 경계) 에서 가끔 긴 "생각" pause
            if ch == " " and random.random() < 0.1:
                await asyncio.sleep(random.uniform(0.2, 0.6) * _speed_multiplier.get())
            i += 1

    await random_delay(0.4, 2.0)  # "re-reading"


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
