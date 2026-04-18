"""계정 최초 온보딩 오케스트레이터.

계정 × AdsPower 프로필 쌍에 대해 다음을 자동 실행:
1. Google 로그인 (이메일 + 비번, 필요시 recovery email 2FA)
2. 포스트로그인 프롬프트 스킵 (전화번호 / 프로필 사진)
3. UI 언어를 한국어로 정렬 (베트남어 원본 계정 → ko-KR)
4. YouTube 홈 도달 확인

이 모듈은 이미 열린 브라우저 `page` 를 받아 위 과정을 동기적으로 진행하고
성공 여부와 단계별 로그를 반환한다.

호출측은 HYDRA Worker 세션 시작 직후, 아직 로그인되지 않은 계정에 대해
한 번만 실행하면 된다 (이후 세션은 AdsPower 프로필에 저장된 쿠키로 자동 로그인).
"""

from dataclasses import dataclass, field
from playwright.async_api import Page

from hydra.core.logger import get_logger
from hydra.browser.actions import random_delay
from worker.login import auto_login, check_logged_in
from worker.language_setup import ensure_korean_language

log = get_logger("auto_onboard")


@dataclass
class OnboardResult:
    ok: bool
    steps: list[str] = field(default_factory=list)
    error: str | None = None


async def onboard_account(
    page: Page,
    *,
    email: str,
    password: str,
    totp_secret: str | None = None,
    recovery_email: str | None = None,
) -> OnboardResult:
    result = OnboardResult(ok=False)

    # 이미 로그인 상태면 로그인 스킵
    if await check_logged_in(page):
        result.steps.append("already_logged_in")
    else:
        ok = await auto_login(
            page, email, password,
            totp_secret=totp_secret,
            recovery_email=recovery_email,
        )
        if not ok:
            result.error = "login_failed"
            return result
        result.steps.append("login_ok")

    # YouTube 로 이동 (어떤 경로로 로그인 끝났든)
    await page.goto("https://www.youtube.com", wait_until="domcontentloaded")
    await random_delay(2.0, 4.0)

    # 언어 정렬
    lang_ok = await ensure_korean_language(page)
    result.steps.append("language_ko" if lang_ok else "language_setup_failed")

    # 최종 YouTube 홈 복귀 + 로그인 확인
    await page.goto("https://www.youtube.com", wait_until="domcontentloaded")
    await random_delay(2.0, 4.0)
    final = await check_logged_in(page)
    if not final:
        result.error = "post_onboard_logged_out"
        return result

    result.ok = True
    result.steps.append("youtube_ready")
    return result
