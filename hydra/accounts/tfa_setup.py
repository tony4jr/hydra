"""TOTP 2FA setup automation.

After an account has been created and soaked (숙성) for 1-2 days,
enable 2-Step Verification with an authenticator app so HYDRA can
generate codes on demand via pyotp.

Flow:
1. Open myaccount.google.com/security (logged in via cookies)
2. Click "2-Step Verification" → authenticate again if challenged
3. Choose "Authenticator app"
4. Click "Show setup key" / "Can't scan it?" to reveal the base32 secret
5. Copy secret → generate code with pyotp → enter code → confirm
6. Save secret (encrypted) to Account.totp_secret

Google's UI changes frequently; every step uses multiple selectors
and will abort (return False) rather than guess.
"""

import asyncio
import re

import pyotp
from sqlalchemy.orm import Session

from hydra.browser import actions
from hydra.browser.driver import open_browser
from hydra.core.crypto import encrypt
from hydra.core.logger import get_logger
from hydra.db.models import Account

log = get_logger("tfa_setup")


async def _click_any(page, selectors: list[str], timeout_ms: int = 2000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible(timeout=timeout_ms):
                continue
            await loc.click()
            return True
        except Exception:
            continue
    return False


async def _extract_secret_from_page(page) -> str | None:
    """Find a base32 TOTP secret on the current page.

    Google shows it as spaced groups like 'BK5V TVQ7 X96V 37DS ...' — 16 or
    32 base32 characters in 4-char chunks.
    """
    # Try common containers first
    for sel in [
        'span:has-text("Setup key")',
        'div:has-text("설정 키")',
        "#setup-key",
        ".totp-secret",
        "code",
        "strong",
    ]:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                text = await loc.nth(i).inner_text()
                m = re.search(r"([A-Z2-7]{4}\s+){3,7}[A-Z2-7]{2,4}", text)
                if m:
                    return m.group(0).replace(" ", "")
        except Exception:
            continue

    # Fallback: scan entire body
    body = await page.locator("body").inner_text()
    m = re.search(r"([A-Z2-7]{4}\s+){3,7}[A-Z2-7]{2,4}", body)
    if m:
        return m.group(0).replace(" ", "")
    return None


async def setup_totp(db: Session, account: Account) -> bool:
    """Enable TOTP 2FA on the account and save the secret to DB.

    Requires that `account.adspower_profile_id` is active and cookies are
    good (account already logged in recently). Returns True on success.
    """
    if account.totp_secret:
        log.info(f"TOTP already set for {account.gmail}")
        return True

    log.info(f"Starting TOTP setup: {account.gmail}")

    async with open_browser(account.adspower_profile_id) as session:
        page = session.page

        # Load cookies if any
        from hydra.accounts.setup import load_cookies, login_gmail
        if not await load_cookies(session, account):
            if not await login_gmail(session, account):
                log.error(f"Cannot log in for TOTP setup: {account.gmail}")
                return False

        # Navigate to security settings
        await session.goto("https://myaccount.google.com/signinoptions/two-step-verification/enroll-welcome")
        await actions.random_delay(3, 5)

        # "Get started" / "시작하기"
        await _click_any(page, [
            'button:has-text("시작하기")',
            'button:has-text("Get started")',
            'button:has-text("Start")',
        ])
        await actions.random_delay(2, 4)

        # Google may ask to re-enter password
        pw_input = page.locator('input[type="password"]').first
        if await pw_input.count() and await pw_input.is_visible(timeout=2000):
            from hydra.core.crypto import decrypt
            await pw_input.click()
            for char in decrypt(account.password):
                await page.keyboard.type(char)
                await asyncio.sleep(0.08)
            await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")'])
            await actions.random_delay(3, 5)

        # Choose Authenticator app option
        await _click_any(page, [
            'div[role="link"]:has-text("인증 앱")',
            'div[role="link"]:has-text("Authenticator")',
            'button:has-text("인증 앱")',
            'button:has-text("Authenticator app")',
        ])
        await actions.random_delay(2, 4)

        # Click "Set up" if there's another level
        await _click_any(page, [
            'button:has-text("설정")',
            'button:has-text("Set up")',
            'button:has-text("추가")',
        ])
        await actions.random_delay(2, 4)

        # Reveal the setup key (text secret)
        await _click_any(page, [
            'button:has-text("설정 키")',
            'button:has-text("Setup key")',
            'a:has-text("Can\'t scan it")',
            'button:has-text("수동 입력")',
        ])
        await actions.random_delay(1, 2)

        # Extract secret
        secret = await _extract_secret_from_page(page)
        if not secret:
            log.error(f"Could not find TOTP secret on page: {account.gmail}")
            return False

        log.info(f"TOTP secret captured ({len(secret)} chars)")

        # Continue to code input
        await _click_any(page, [
            'button:has-text("다음")',
            'button:has-text("Next")',
        ])
        await actions.random_delay(2, 4)

        # Generate code and enter
        totp = pyotp.TOTP(secret)
        code = totp.now()
        code_input = page.locator('input[type="tel"], input[name="code"], input[aria-label*="코드"]').first
        if not await code_input.count():
            log.error(f"TOTP code input not found: {account.gmail}")
            return False
        await code_input.click()
        for char in code:
            await page.keyboard.type(char)
            await asyncio.sleep(0.1)
        await actions.random_delay(1, 2)
        await _click_any(page, [
            'button:has-text("다음")',
            'button:has-text("확인")',
            'button:has-text("Next")',
            'button:has-text("Verify")',
        ])
        await actions.random_delay(3, 5)

        # Turn on 2FA if there's a confirm step
        await _click_any(page, [
            'button:has-text("사용 설정")',
            'button:has-text("Turn on")',
            'button:has-text("Enable")',
            'button:has-text("완료")',
            'button:has-text("Done")',
        ])
        await actions.random_delay(2, 4)

        # Persist secret
        account.totp_secret = encrypt(secret)
        db.commit()

        log.info(f"TOTP enabled successfully: {account.gmail}")
        return True
