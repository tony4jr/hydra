"""계정 최초 세션 — 로그인 + 언어 설정 + 자연 탐색.

Google 로그인을 방금 통과한 계정이 언어만 바꾸고 바로 끄면 봇티가 강하다.
본 모듈은 같은 세션 안에서 언어 설정 직후 5~15분 자연 탐색을 수행해 실사람의
첫 로그인 세션 흐름을 흉내낸다.

흐름:
1. 로그인 (이미 cookies 로 로그인 상태면 스킵)
2. Google 포스트로그인 프롬프트 스킵 (전화번호 / 프로필 사진)
3. UI 언어를 한국어로 전환 + "기타 언어"에 남은 원본 언어 삭제
4. YouTube 홈 이동
5. 루프: 스크롤 / 영상 부분 시청 / 숏츠 스와이프 중 랜덤 액션
   - 중간 1회 검색 (persona age 기반 search_pool 에서 쿼리 픽)
6. 홈 복귀 후 세션 종료

워밍업 Day 1 의 언어 설정 호출은 그대로 유지 — idempotent 이므로 온보딩이
실패했을 때 안전망으로 동작.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from playwright.async_api import Page

from hydra.browser.actions import random_delay, scroll_page, watch_video, handle_ad, click_like_button
from hydra.core.logger import get_logger
from worker.language_setup import ensure_korean_language
from worker.login import auto_login, check_logged_in
from worker.search_pool import pick as pick_query

log = get_logger("onboard_session")

YOUTUBE_HOME = "https://www.youtube.com"
SHORTS_URL = "https://www.youtube.com/shorts"


@dataclass
class OnboardSessionResult:
    ok: bool
    duration_sec: int = 0
    actions: list[str] = field(default_factory=list)
    searched_query: str | None = None
    error: str | None = None


async def run_onboard_session(
    page: Page,
    *,
    persona: dict,
    email: str | None = None,
    password: str | None = None,
    recovery_email: str | None = None,
    duration_min_sec: int = 300,   # 5 min
    duration_max_sec: int = 900,   # 15 min
    search_probability: float = 0.6,
) -> OnboardSessionResult:
    """자연 탐색 온보딩. 이미 열린 page (AdsPower + Playwright CDP 연결)를 받음.

    persona: Account.persona (dict) — age 필요 (search_pool bucket 결정용)
    email/password/recovery_email: login 이 필요할 때만 사용. 이미 로그인 상태면 무시.
    """
    result = OnboardSessionResult(ok=False)
    started = time.time()

    # ── 0) 로그인 확인 / 수행 ────────────────────────────────────────
    try:
        await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
    except Exception as e:
        result.error = f"initial goto failed: {e}"
        return result
    await random_delay(2.0, 4.0)

    if not await check_logged_in(page):
        if not (email and password):
            result.error = "not logged in and no credentials provided"
            return result
        ok = await auto_login(
            page, email, password, recovery_email=recovery_email,
        )
        if not ok:
            result.error = "login failed"
            return result
        result.actions.append("login_ok")
    else:
        result.actions.append("already_logged_in")

    # ── 1) UI 언어를 한국어로 (기타 언어 삭제 포함) ────────────────
    # Google 로그인 흐름은 myaccount 에 착지할 수 있으므로 언어 설정 페이지로
    # 바로 이동 (ensure_korean_language 내부에서 /language 로 goto).
    try:
        lang_ok = await ensure_korean_language(page)
        result.actions.append("language_ko" if lang_ok else "language_failed")
    except Exception as e:
        log.warning(f"language setup error: {e}")
        result.actions.append(f"language_error:{e}")

    # 언어 설정 후 YouTube 홈으로 — 여기서부터 자연 탐색
    try:
        await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
    except Exception:
        pass
    await random_delay(3.0, 6.0)

    # ── 2) 초기 홈 스크롤 (도착하자마자 바로 둘러보기) ───────────────
    try:
        await scroll_page(page, scrolls=random.randint(2, 5))
        result.actions.append(f"scroll_initial")
    except Exception as e:
        log.debug(f"initial scroll failed: {e}")
    await random_delay(3.0, 7.0)

    # ── 3) 루프: 랜덤 액션 (duration 까지) ──────────────────────────
    target_duration = random.uniform(duration_min_sec, duration_max_sec)
    log.info(f"onboard target duration: {int(target_duration)}s")
    searched = False

    while (time.time() - started) < target_duration:
        remaining = target_duration - (time.time() - started)
        if remaining < 20:
            break

        # 중간 1회 검색 (한 세션에 한 번만, 확률 조건 통과 시)
        if not searched and random.random() < search_probability:
            q = pick_query(int(persona.get("age", 25)))
            try:
                await _do_search(page, q)
                result.actions.append(f"search:{q}")
                result.searched_query = q
                searched = True
            except Exception as e:
                log.warning(f"search failed: {e}")
            await random_delay(3.0, 8.0)
            continue

        # 주 액션 선택
        action = random.choices(
            ["watch_home_video", "browse_shorts", "scroll_home"],
            weights=[45, 30, 25],
        )[0]

        try:
            if action == "watch_home_video":
                await _watch_home_video(page)
                result.actions.append("watch_home_video")
            elif action == "browse_shorts":
                await _browse_shorts(page)
                result.actions.append("browse_shorts")
            elif action == "scroll_home":
                await _scroll_home(page)
                result.actions.append("scroll_home")
        except Exception as e:
            log.warning(f"action {action} failed: {e}")

        await random_delay(4.0, 10.0)

    # ── 4) 홈 복귀 + 마지막 스크롤 (자연스러운 마무리) ───────────────
    try:
        await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
        await random_delay(2.0, 4.0)
        await scroll_page(page, scrolls=random.randint(1, 3))
        result.actions.append("final_scroll")
    except Exception:
        pass

    result.duration_sec = int(time.time() - started)
    result.ok = True
    log.info(
        f"onboard done: {result.duration_sec}s, actions={len(result.actions)}, "
        f"searched={result.searched_query!r}"
    )
    return result


# ─── 보조 액션 구현 ──────────────────────────────────────────────────

async def _scroll_home(page: Page):
    await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
    await random_delay(2.0, 4.0)
    await scroll_page(page, scrolls=random.randint(2, 5))


async def _watch_home_video(page: Page):
    """홈에서 썸네일 하나 클릭 → 10~90초 시청 → 뒤로."""
    await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
    await random_delay(2.0, 4.0)

    thumbnails = page.locator("ytd-rich-item-renderer a#thumbnail")
    count = await thumbnails.count()
    if count == 0:
        return
    idx = random.randint(0, min(count - 1, 9))
    try:
        await thumbnails.nth(idx).click(timeout=5_000)
    except Exception:
        return
    await random_delay(2.0, 5.0)

    # 광고 처리
    try:
        await handle_ad(page)
    except Exception:
        pass

    duration = random.randint(10, 90)
    try:
        await watch_video(page, duration)
    except Exception:
        await random_delay(duration * 0.6, duration)

    # 드문 좋아요 (5%)
    if random.random() < 0.05:
        try:
            await click_like_button(page, target="video")
        except Exception:
            pass

    # 뒤로
    try:
        await page.go_back()
        await random_delay(1.5, 3.0)
    except Exception:
        pass


async def _browse_shorts(page: Page):
    """숏츠 URL 로 가서 2~8 개 스와이프 (자연 속도)."""
    try:
        await page.goto(SHORTS_URL, wait_until="domcontentloaded")
    except Exception:
        return
    await random_delay(1.5, 3.0)

    num_shorts = random.randint(2, 8)
    for _ in range(num_shorts):
        behavior = random.choices(
            ["skip", "short_watch", "full_watch", "rewatch"],
            weights=[40, 30, 25, 5],
        )[0]

        if behavior == "skip":
            await random_delay(1.0, 2.5)
        elif behavior == "short_watch":
            await random_delay(3.0, 10.0)
        elif behavior == "full_watch":
            await random_delay(15.0, 45.0)
        elif behavior == "rewatch":
            await random_delay(15.0, 30.0)
            continue

        if random.random() < 0.05:
            try:
                await click_like_button(page, target="video")
            except Exception:
                pass

        try:
            await page.keyboard.press("ArrowDown")
        except Exception:
            break
        await random_delay(0.4, 1.2)


async def _do_search(page: Page, query: str):
    """YouTube 검색창에 쿼리 입력 → 결과 하나 클릭 → 짧게 시청 → 뒤로."""
    from hydra.browser.actions import type_human

    await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
    await random_delay(1.5, 3.0)

    # 검색창 클릭 후 입력
    try:
        search_input = page.locator("input#search")
        await search_input.wait_for(timeout=10_000)
        await search_input.click()
        await search_input.fill("")
        await type_human(page, "input#search", query)
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(2.0, 4.0)
    except Exception as e:
        log.warning(f"search input failed: {e}")
        return

    # 결과 중 하나 클릭 (상위 5개 중 랜덤)
    results = page.locator("ytd-video-renderer a#thumbnail")
    count = await results.count()
    if count == 0:
        return
    idx = random.randint(0, min(count - 1, 4))
    try:
        await results.nth(idx).click(timeout=5_000)
    except Exception:
        return
    await random_delay(2.0, 4.0)

    try:
        await handle_ad(page)
    except Exception:
        pass

    duration = random.randint(15, 80)
    try:
        await watch_video(page, duration)
    except Exception:
        await random_delay(duration * 0.6, duration)

    try:
        await page.go_back()
        await random_delay(1.5, 3.0)
    except Exception:
        pass
