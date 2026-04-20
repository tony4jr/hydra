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

from hydra.browser.actions import (
    human_click, random_delay, scroll_page, watch_video, handle_ad, click_like_button,
    set_speed_multiplier, set_typing_style, set_activity_multiplier, rep_count,
)
from hydra.core.logger import get_logger
from worker.channel_actions import (
    pick_avatar_file, rename_channel, set_description, upload_avatar,
)
from worker.data_saver import set_primary_video_language
from worker.google_account import (
    register_otp_authenticator, update_account_name,
)
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
    otp_secret: str | None = None  # pyotp base32 시크릿 (등록 성공 시). caller 가 DB 저장.
    # critical_failures: 재시도 필요한 실패들 (브라우저 끊김, 중요 단계 실패 등).
    # 비어있지 않으면 complete_task 가 account 를 warmup 으로 전이하지 않음.
    critical_failures: list[str] = field(default_factory=list)


def _is_connection_error(e: BaseException) -> bool:
    """브라우저/드라이버 연결 끊김 관련 예외인지 판별."""
    msg = str(e)
    return any(
        s in msg for s in (
            "Connection closed",
            "Target page, context or browser has been closed",
            "browser has been closed",
            "Protocol error",
        )
    )


async def run_onboard_session(
    page: Page,
    *,
    persona: dict,
    email: str | None = None,
    password: str | None = None,
    recovery_email: str | None = None,
    duration_min_sec: int = 120,   # 2 min
    duration_max_sec: int = 300,   # 5 min
    search_probability: float = 0.6,
) -> OnboardSessionResult:
    """자연 탐색 온보딩. 이미 열린 page (AdsPower + Playwright CDP 연결)를 받음.

    persona: Account.persona (dict) — age 필요 (search_pool bucket 결정용)
    email/password/recovery_email: login 이 필요할 때만 사용. 이미 로그인 상태면 무시.
    """
    result = OnboardSessionResult(ok=False)
    started = time.time()

    # 세션 템포 + 타이핑 스타일 + 활동량 설정 — persona 별 프로파일 (anti-detection)
    speed = (persona or {}).get("speed_multiplier") or random.uniform(0.6, 1.8)
    set_speed_multiplier(speed)
    typing_style = (persona or {}).get("typing_style") or random.choice(["typist", "typist", "paster"])
    set_typing_style(typing_style)
    activity = (persona or {}).get("activity_multiplier") or random.uniform(0.6, 1.5)
    set_activity_multiplier(activity)
    log.info(f"onboard: speed={speed:.2f} typing={typing_style} activity={activity:.2f}")

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

    # ── 1.5) Google 계정 display name 을 한국어 풀네임으로 교체 ───
    # persona.name 은 실제 한국 이름(예: "박민재"). YouTube/Gmail 등에서 표시됨.
    # Legal name 은 대부분 계정에 없어 건드리지 않음 (에러 페이지 뜨는 계정 많음).
    persona_name = (persona or {}).get("name") or ""
    if persona_name:
        try:
            if await update_account_name(page, persona_name, password=password):
                result.actions.append(f"google_name:{persona_name}")
        except Exception as e:
            log.warning(f"update_account_name error: {e}")
            if _is_connection_error(e):
                result.critical_failures.append("update_account_name:disconnected")
                result.error = f"browser disconnected during account name update: {e}"
                return result

    # ── 1.7) OTP Authenticator 시크릿 등록 (2FA 최종 활성화는 전화번호 필요해서 보통 실패) ──
    # 시크릿만 확보해도 가치 있음: 향후 Google 이 TOTP 챌린지 요구하면 pyotp 로 대응 가능.
    if password:
        try:
            otp_secret, activated = await register_otp_authenticator(page, password)
            if otp_secret:
                result.otp_secret = otp_secret
                result.actions.append(f"otp_registered{':activated' if activated else ''}")
        except Exception as e:
            log.warning(f"register_otp_authenticator error: {e}")

    # YT 기본 시청 언어를 한국어로 설정 — /account_playback 페이지 "언어" 섹션.
    # Google 추천/자동 번역이 참조하는 언어 선호도. UI 언어와는 별개 설정.
    # (구 Data Saver 라디오는 YT UI 개편으로 제거됨 → 언어 설정만 수행.)
    try:
        if await set_primary_video_language(page, "한국어"):
            result.actions.append("primary_video_language_ko")
    except Exception as e:
        log.debug(f"set_primary_video_language skipped: {e}")

    # 언어 설정 후 YouTube 홈으로 — 여기서부터 자연 탐색
    try:
        await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
    except Exception:
        pass
    await random_delay(3.0, 6.0)

    # ── 2) 초기 홈 스크롤 (도착하자마자 바로 둘러보기) ───────────────
    try:
        await scroll_page(page, scrolls=rep_count(2, 5))
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
        await scroll_page(page, scrolls=rep_count(1, 3))
        result.actions.append("final_scroll")
    except Exception:
        pass

    # ── 5) 채널 맞춤 설정 — 이름 / 설명 / 아바타 ─────────────────────
    # "유튜브 구경하고 마음에 드니 프로필 꾸미자" 흐름. persona.channel_plan 에
    # 미리 결정된 title/description/avatar_plan 을 사용.
    plan = (persona or {}).get("channel_plan") or {}
    if plan:
        await random_delay(3.0, 6.0)

        # 이름 변경 (title 이 있으면 무조건 실행 — 100% 계정)
        title = plan.get("title") or ""
        if title:
            try:
                if await rename_channel(page, title):
                    result.actions.append(f"rename:{title}")
                    # description 은 15% 계정만 비어있지 않음
                    desc = plan.get("description") or ""
                    if desc:
                        if await set_description(page, desc):
                            result.actions.append("set_description")
                else:
                    result.critical_failures.append("rename_channel:returned_false")
            except Exception as e:
                log.warning(f"rename_channel error: {e}")
                result.actions.append(f"rename_error:{e}")
                if _is_connection_error(e):
                    result.critical_failures.append("rename_channel:disconnected")
                    result.error = f"browser disconnected during channel rename: {e}"
                    return result

        # 아바타 업로드 — avatar_policy == "set_during_warmup" 인 50% 계정
        if plan.get("avatar_policy") == "set_during_warmup":
            avatar_path = pick_avatar_file(persona, plan)
            if avatar_path:
                try:
                    if await upload_avatar(page, avatar_path):
                        result.actions.append(
                            f"upload_avatar:{avatar_path.rsplit('/', 1)[-1]}"
                        )
                    else:
                        result.critical_failures.append("upload_avatar:returned_false")
                except Exception as e:
                    log.warning(f"upload_avatar error: {e}")
                    result.actions.append(f"avatar_error:{e}")
                    if _is_connection_error(e):
                        result.critical_failures.append("upload_avatar:disconnected")
                        result.error = f"browser disconnected during avatar upload: {e}"
                        return result

        # 설정 끝나면 유튜브 홈으로 돌아와 마지막에 한 번 더 둘러보기
        try:
            await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
            await random_delay(2.0, 4.0)
            await scroll_page(page, scrolls=rep_count(1, 2))
            result.actions.append("post_channel_scroll")
        except Exception:
            pass

    result.duration_sec = int(time.time() - started)
    # critical_failures 있으면 ok=False → complete_task 가 warmup 전이 skip + 재시도 유도
    result.ok = len(result.critical_failures) == 0
    log.info(
        f"onboard done: {result.duration_sec}s, actions={len(result.actions)}, "
        f"searched={result.searched_query!r}, ok={result.ok}, "
        f"critical_failures={result.critical_failures or 'none'}"
    )
    return result


# ─── 보조 액션 구현 ──────────────────────────────────────────────────

async def _scroll_home(page: Page):
    await page.goto(YOUTUBE_HOME, wait_until="domcontentloaded")
    await random_delay(2.0, 4.0)
    await scroll_page(page, scrolls=rep_count(2, 5))


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
        await human_click(thumbnails.nth(idx), timeout=5_000)
    except Exception:
        return
    await random_delay(2.0, 5.0)

    # 광고 처리
    try:
        await handle_ad(page)
    except Exception:
        pass

    # 데이터 절감을 위해 시청 시간 축소 (10~45s, 기존 10~90s)
    duration = random.randint(10, 45)
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

    num_shorts = rep_count(2, 8)
    for _ in range(num_shorts):
        # 데이터 절감: full_watch 가중치 25 → 10, skip 가중치 ↑
        behavior = random.choices(
            ["skip", "short_watch", "full_watch", "rewatch"],
            weights=[55, 30, 10, 5],
        )[0]

        if behavior == "skip":
            await random_delay(1.0, 2.5)
        elif behavior == "short_watch":
            await random_delay(3.0, 10.0)
        elif behavior == "full_watch":
            await random_delay(15.0, 30.0)  # 45 → 30
        elif behavior == "rewatch":
            await random_delay(15.0, 25.0)
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

    # 검색창 클릭 후 입력 — YT UI 개편으로 id 제거. name 속성으로 타겟.
    try:
        search_sel = "input[name='search_query']"
        search_input = page.locator(search_sel)
        await search_input.wait_for(timeout=10_000)
        await human_click(search_input)
        await search_input.fill("")
        await type_human(page, search_sel, query)
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
        await human_click(results.nth(idx), timeout=5_000)
    except Exception:
        return
    await random_delay(2.0, 4.0)

    try:
        await handle_ad(page)
    except Exception:
        pass

    duration = random.randint(15, 40)  # 80 → 40 (데이터 절감)
    try:
        await watch_video(page, duration)
    except Exception:
        await random_delay(duration * 0.6, duration)

    try:
        await page.go_back()
        await random_delay(1.5, 3.0)
    except Exception:
        pass
