"""자동 로그인 + 2FA (TOTP + 복구 이메일 경유 6자리 코드) + 포스트로그인 프롬프트 스킵."""
import asyncio
import random

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
    # 복구 옵션/집 주소 등 GDS(accounts 2차 안내) 페이지 — "Huỷ/Hủy" 취소
    "huỷ", "hủy", "cancel", "nhắc lại sau", "maybe later",
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

        # Step 0: 이미 Google 쪽 로그인된 경우 이 단계를 스킵하고 post-login 프롬프트
        # 만 처리. Google 은 signin URL 접속 시 로그인 쿠키가 있으면 myaccount 로
        # 리다이렉트 시키거나 AccountChooser 화면 (email input 없음) 을 보여줌.
        # 그대로 wait_for(email input) 을 돌리면 10초 타임아웃 → False 반환되는 버그.
        cur_url = page.url
        if "myaccount.google.com" in cur_url or "youtube.com" in cur_url:
            log.info("auto_login: already logged in (redirected to myaccount/youtube)")
            await _skip_post_login_prompts(page, max_attempts=6)
            return True
        # signin 에 머물러 있으면 email input 짧게 선확인. 없으면 다음 두 가지 케이스:
        #   (a) 이미 로그인된 채로 acccountchooser/myaccount 등에 도달 → skip 처리
        #   (b) "본인 인증" (confirmidentifier) 페이지 — 5일+ 휴면 / 새 IP 후 재로그인 시
        #       email 없이 "다음" 만 보임. 다음 클릭 → /pwd 로 진행
        try:
            await page.wait_for_selector("input[type='email']", timeout=3_000)
        except Exception:
            cur = page.url
            # case (b): confirmidentifier or signin/identifier with email pre-filled
            if "confirmidentifier" in cur or "signin/identifier" in cur:
                log.info("auto_login: identity-challenge (confirmidentifier) — clicking 다음/Next")
                try:
                    next_btn = page.locator(
                        "#identifierNext button, button:has-text('다음'), button:has-text('Next')"
                    )
                    await next_btn.first.click(timeout=5_000)
                    await random_delay(2.0, 4.0)
                except Exception as e:
                    log.warning(f"identity-challenge 다음 click failed: {e}")
                # fall through to password step below
            # case: accountchooser - click the saved account
            elif "accountchooser" in cur:
                log.info("auto_login: accountchooser — clicking saved account")
                try:
                    chooser = page.locator(f"div[data-email='{email}'], li[data-email='{email}']")
                    if await chooser.count() == 0:
                        chooser = page.locator(f"div:has-text('{email}')")
                    await chooser.first.click(timeout=5_000)
                    await random_delay(2.0, 4.0)
                except Exception as e:
                    log.warning(f"accountchooser click failed: {e}")
            else:
                log.info(f"auto_login: no email input at {cur[:80]}, treating as logged-in")
                await _skip_post_login_prompts(page, max_attempts=6)
                return True

        # Step 1: email
        # ⚠ typing_style="typist" 강제 — paster (clipboard paste) 는 일부 브라우저
        # 환경에서 clipboard 권한 거부로 silent 실패 → input 이 빈 채로 Enter 되어
        # "이메일을 입력하세요" 에러 → 이후 password 화면 안 뜸.
        email_input = page.locator("input[type='email']")
        await email_input.wait_for(timeout=10_000)
        await type_human(page, "input[type='email']", email, typing_style="typist")
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(2.0, 4.0)

        # Step 2: password
        # Google 이 input name 을 'Passwd' 에서 자주 바꾸므로 (Identifier UI v3 등)
        # type=password 만으로 매칭하고, 보이는(=visible) 첫 번째만 사용 — pwd 페이지엔
        # 보통 1개뿐 (recovery 입력같은 추가 input 은 다른 페이지).
        pw_selector = "input[type='password']:visible"
        password_input = page.locator(pw_selector)
        await password_input.first.wait_for(state="visible", timeout=15_000)
        await random_delay(0.5, 1.5)
        # type_human 은 selector 를 받아서 page.click(selector) 후 type. visible-only
        # filter 가 type_human 의 default selector 와 호환 안 되므로 직접 fill.
        await password_input.first.click()
        await random_delay(0.3, 0.8)
        # 글자 단위 타이핑 (anti-detection)
        for char in password:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.04, 0.15))
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

        # Step 4: 최종 착지 먼저 기다림 (myaccount/youtube) — 이후 프롬프트는 안정된
        # 페이지에서 처리. 네비게이션 중간에 evaluate 하면 context 파괴 에러 난다.
        try:
            await page.wait_for_url(
                lambda url: "myaccount.google.com" in url or "youtube.com" in url,
                timeout=post_login_timeout_ms,
            )
        except Exception:
            pass

        # Step 5: 포스트로그인 프롬프트 (전화/사진) 스킵
        # GDS 안내 페이지가 연속으로 여러 개 뜰 수 있음 (복구전화번호, 복구이메일,
        # 집 주소, 프로필 사진 등) — 충분히 많이 시도.
        await _skip_post_login_prompts(page, max_attempts=6)
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
        await type_human(page, "input[name='totpPin'], input#totpPin", code, typing_style="typist")
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
    await type_human(page, "input[name='Pin']", code, typing_style="typist")
    await random_delay(0.5, 1.0)
    await page.keyboard.press("Enter")
    await random_delay(3.0, 6.0)
    return True


async def _select_recovery_email_challenge(page, recovery_email: str) -> bool:
    """Challenge 선택 페이지에서 recovery email 옵션 버튼 클릭.

    Google 은 각 옵션을 `div[role="link"]` 로 렌더링하고, 복구 이메일 옵션엔
    마스킹된 이메일 텍스트 (예: `huy••••••••••••@911•••••.••`) 가 포함된다.
    이메일 로컬파트 앞 3글자 + `@` + 도메인 앞 3글자 조합으로 매칭하면 locale
    무관하게 올바른 옵션을 잡을 수 있다.
    """
    try:
        # Google 이 옵션 텍스트에서 이메일을 마스킹함 (예: `d••••••••@911•••••.us`).
        # 로컬파트 앞 3글자는 거의 보이지 않으므로 user 의 첫 글자 + 도메인 앞 3글자
        # (`@911` 등) 로 매칭. TLD 는 도메인에 포함된 걸 그대로 사용.
        user0 = recovery_email.split("@")[0][:1].lower()
        domain = recovery_email.split("@")[1][:3].lower()
        clicked = await page.evaluate(f"""
            ({{ user0, domain }}) => {{
              const items = Array.from(document.querySelectorAll('[role="link"], [role="button"]'))
                .filter(el => el.offsetParent !== null);
              const hit = items.find(el => {{
                const t = (el.textContent || '').toLowerCase();
                // 이메일 형태(@domain 부분 존재) + 로컬파트 첫 글자와 일치
                if (!t.includes('@' + domain)) return false;
                // 첫 글자 검증: 텍스트에서 @ 앞 부분의 첫 영숫자가 user0 인지
                const before = t.split('@')[0].replace(/[^a-z0-9]/g, '');
                return before.startsWith(user0);
              }});
              if (hit) {{ hit.click(); return true; }}
              return false;
            }}
        """, {"user0": user0, "domain": domain})
        if clicked:
            await random_delay(2.0, 4.0)
            return True
        log.error(f"challenge selection: no option matched user0={user0}/@{domain}")
    except Exception as e:
        log.error(f"challenge selection error: {e}")
    return False


async def _skip_post_login_prompts(page, max_attempts: int = 3):
    """전화번호/프로필 사진 등 로그인 직후 간섭 프롬프트를 '건너뛰기' 로 해소.

    Google 은 ko/en/vi 등 locale 에 따라 버튼 텍스트가 다르므로 여러 패턴을 시도.
    클릭 직후 리다이렉트가 일어나 evaluate 컨텍스트가 파괴될 수 있으므로 예외를
    무시하고 다음 시도로 넘어간다. 매번 load 대기로 안정된 DOM 을 본다.
    """
    for _ in range(max_attempts):
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8_000)
        except Exception:
            pass

        try:
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
        except Exception as e:
            log.debug(f"skip-prompt evaluate threw (navigation likely): {e}")
            await random_delay(1.5, 3.0)
            continue

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
