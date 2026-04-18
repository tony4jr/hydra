"""자동 로그인 + 2FA (TOTP + 복구 이메일 경유 6자리 코드) + 포스트로그인 프롬프트 스킵."""
import asyncio

import pyotp

from hydra.browser.actions import random_delay, type_human
from hydra.core.logger import get_logger
from worker.mail_911panel import fetch_2fa_code

log = get_logger("login")


# 복구 이메일 경유 2FA 을 위해 조회 가능한 도메인 목록
RECOVERY_MAIL_DOMAINS = ("911panel.us",)

# 포스트로그인 "건너뛰기" 버튼 후보 (locale 무관)
SKIP_ARIA_PATTERNS = [
    "skip", "not now", "나중에", "건너뛰기", "취소",
    "bỏ qua", "bo qua", "không phải", "không, cảm ơn",
    "skip for now",
]


async def check_logged_in(page):
    try:
        avatar = page.locator(
            "button#avatar-btn, img.yt-spec-avatar-shape__image"
        )
        await avatar.wait_for(timeout=5000)
        return True
    except Exception:
        return False


async def auto_login(
    page,
    email: str,
    password: str,
    *,
    totp_secret: str | None = None,
    recovery_email: str | None = None,
    post_login_timeout_ms: int = 30_000,
):
    """Google 로그인 자동화. 성공 시 True.

    2FA 전략:
      1) totp_secret 있으면 TOTP 사용 (pyotp)
      2) 없고 recovery_email 이 지원 도메인이면 해당 인박스에서 6자리 코드 추출
      3) 둘 다 없으면 2FA 단계에서 실패할 가능성 있음

    로그인 성공 후 "복구 전화번호 추가", "프로필 사진 추가" 프롬프트는 자동 스킵.
    """
    try:
        await page.goto("https://accounts.google.com/signin")
        await random_delay(2.0, 4.0)

        # Step 1: email
        email_input = page.locator("input[type='email']")
        await email_input.wait_for(timeout=10_000)
        await type_human(page, "input[type='email']", email)
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(2.0, 4.0)

        # Step 2: password (Google 의 "실패한 시도 횟수가 너무 많음" 경고에도 입력 필드 존재)
        password_input = page.locator("input[type='password'][name='Passwd']")
        await password_input.wait_for(timeout=10_000)
        await type_human(page, "input[type='password'][name='Passwd']", password)
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 6.0)

        # Step 3: 2FA — TOTP 우선, 없으면 recovery email
        if totp_secret:
            await _handle_totp(page, totp_secret)
        elif recovery_email and _is_supported_recovery_domain(recovery_email):
            ok = await _handle_email_2fa(page, recovery_email)
            if not ok:
                log.error("Email 2FA flow failed")
                return False

        # Step 4: 포스트로그인 프롬프트 (전화/사진) 스킵
        await _skip_post_login_prompts(page, max_attempts=3)

        # Step 5: 최종 착지 — myaccount 또는 youtube 로 리다이렉트되면 성공으로 본다
        try:
            await page.wait_for_url(
                lambda url: "myaccount.google.com" in url or "youtube.com" in url,
                timeout=post_login_timeout_ms,
            )
        except Exception:
            # url 매치 실패해도 avatar 로 로그인 상태 체크
            pass
        return True
    except Exception as e:
        log.error(f"Login failed: {e}")
        return False


def _is_supported_recovery_domain(email: str) -> bool:
    return any(email.lower().endswith("@" + d) for d in RECOVERY_MAIL_DOMAINS)


async def _handle_totp(page, totp_secret: str):
    try:
        totp_input = page.locator("input[name='totpPin'], input#totpPin")
        await totp_input.wait_for(timeout=10_000)
        code = pyotp.TOTP(totp_secret).now()
        await type_human(page, "input[name='totpPin'], input#totpPin", code)
        await random_delay(0.5, 1.0)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 5.0)
    except Exception:
        pass


async def _handle_email_2fa(page, recovery_email: str) -> bool:
    """Google 의 challenge selection 페이지에서 '복구 이메일' 옵션 선택 → 911panel
    에서 코드 추출 → 입력.
    """
    # Challenge selection 페이지: "이메일로 코드 받기" / "복구 이메일 확인" 등
    # 옵션 중 하나를 클릭해서 코드를 발송시켜야 함
    selection_ok = await _select_recovery_email_challenge(page, recovery_email)
    if not selection_ok:
        log.error("Could not select recovery-email challenge option")
        return False

    # 코드 도착 대기 + 911panel 에서 추출 — 새 탭에서 수행
    mail_page = await page.context.new_page()
    try:
        code = await fetch_2fa_code(mail_page, recovery_email)
    finally:
        await mail_page.close()

    if not code:
        return False

    # 원래 Google 탭에서 코드 입력
    code_input = page.locator(
        "input[name='Pin'], input[type='text'][name='Pin'], input[type='tel']"
    ).first
    try:
        await code_input.wait_for(timeout=15_000)
    except Exception:
        log.error("Pin input not found on Google challenge page")
        return False
    await type_human(page, "input[name='Pin']", code)
    await random_delay(0.5, 1.0)
    await page.keyboard.press("Enter")
    await random_delay(3.0, 6.0)
    return True


async def _select_recovery_email_challenge(page, recovery_email: str) -> bool:
    """Challenge 선택 페이지에서 recovery email 옵션 버튼 클릭."""
    try:
        # 옵션은 li 또는 div[role="link"] 형태. aria-label 이 recovery 이메일 힌트를 포함.
        clicked = await page.evaluate(f"""
            (hintFragment) => {{
              const items = Array.from(document.querySelectorAll('li, div[role="link"], [jsaction]'))
                .filter(el => el.offsetParent !== null);
              // 복구 이메일 항목 찾기 — 텍스트에 마스킹된 도메인 또는 '이메일' 포함
              const hit = items.find(el => {{
                const t = (el.textContent || '').toLowerCase();
                return t.includes(hintFragment) || /email|이메일|thư điện tử|gmail/.test(t);
              }});
              if (hit) {{
                hit.click();
                return true;
              }}
              return false;
            }}
        """, recovery_email.split("@")[0][:3])
        if clicked:
            await random_delay(2.0, 4.0)
            return True
    except Exception as e:
        log.error(f"challenge selection error: {e}")
    return False


async def _skip_post_login_prompts(page, max_attempts: int = 3):
    """전화번호/프로필 사진 등 로그인 직후 간섭 프롬프트를 '건너뛰기' 로 해소.

    Google 은 ko/en/vi 등 locale 에 따라 버튼 텍스트가 다르므로 여러 패턴을 시도.
    """
    for _ in range(max_attempts):
        clicked = await page.evaluate(f"""
            (patterns) => {{
              const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'))
                .filter(el => el.offsetParent !== null);
              const hit = buttons.find(b => {{
                const label = ((b.getAttribute('aria-label') || '') + ' ' + (b.textContent || '')).toLowerCase();
                return patterns.some(p => label.includes(p));
              }});
              if (hit) {{ hit.click(); return hit.textContent?.trim().slice(0, 40) || hit.getAttribute('aria-label'); }}
              return null;
            }}
        """, SKIP_ARIA_PATTERNS)
        if not clicked:
            break
        log.info(f"post-login prompt skipped: {clicked}")
        await random_delay(1.5, 3.0)


async def ensure_logged_in(
    page,
    email: str,
    password: str,
    *,
    totp_secret: str | None = None,
    recovery_email: str | None = None,
):
    """Backward-compatible wrapper."""
    if await check_logged_in(page):
        return True
    return await auto_login(
        page, email, password,
        totp_secret=totp_secret,
        recovery_email=recovery_email,
    )
