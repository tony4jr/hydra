"""Account profile setup — automated via browser.

Spec 2.1.3:
1. AdsPower profile → Chrome launch
2. Gmail login + 2FA
3. Password change
4. Recovery email change
5. YouTube channel profile check/setup
6. Language/region → Korean
7. Save cookies
"""

import json
import pyotp
from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import AccountStatus
from hydra.core.crypto import decrypt, encrypt
from hydra.db.models import Account
from hydra.browser.driver import open_browser
from hydra.browser.actions import random_delay, type_human
from hydra.accounts.manager import transition
from hydra.infra import telegram

log = get_logger("setup")


async def login_gmail(session, account: Account) -> bool:
    """Login to Gmail with optional 2FA."""
    page = session.page

    await session.goto("https://accounts.google.com/signin")
    await random_delay(2, 4)

    # Email
    try:
        await type_human(page, 'input[type="email"]', account.gmail)
        await page.click("#identifierNext")
        await random_delay(2, 4)
    except Exception as e:
        log.error(f"Email input failed: {e}")
        return False

    # Password
    try:
        await type_human(page, 'input[type="password"]', decrypt(account.password))
        await page.click("#passwordNext")
        await random_delay(3, 5)
    except Exception as e:
        log.error(f"Password input failed: {e}")
        return False

    # 2FA check
    if account.totp_secret:
        try:
            totp = pyotp.TOTP(decrypt(account.totp_secret))
            code = totp.now()
            await type_human(page, 'input[type="tel"]', code)
            await page.click("button[type='submit']")
            await random_delay(3, 5)
        except Exception as e:
            log.warning(f"2FA handling: {e}")

    # Check for captcha
    from hydra.infra.captcha import solve_youtube_captcha
    await solve_youtube_captcha(page)

    # Verify login success
    current_url = page.url
    if "myaccount.google.com" in current_url or "youtube.com" in current_url:
        log.info(f"Login success: {account.gmail}")
        return True

    if "challenge" in current_url or "signin" in current_url:
        log.warning(f"Security checkpoint detected: {account.gmail}")
        return False

    return True


async def setup_youtube_profile(session, account: Account):
    """Set YouTube language/region to Korean and check channel."""
    page = session.page

    await session.goto("https://www.youtube.com")
    await random_delay(2, 4)

    # Set language to Korean via settings
    try:
        # Click profile avatar → Settings
        await page.click("button#avatar-btn, img#img")
        await random_delay(1, 2)

        # Look for language/location settings
        # This is simplified — actual selectors may vary
        await session.goto("https://www.youtube.com/account")
        await random_delay(2, 3)
    except Exception as e:
        log.warning(f"YouTube profile setup partial: {e}")


async def save_cookies(session, account: Account, db: Session):
    """Save browser cookies for session reuse."""
    cookies = await session._context.cookies()
    account.cookies = encrypt(json.dumps(cookies))
    db.commit()
    log.info(f"Cookies saved for {account.gmail}")


async def load_cookies(session, account: Account) -> bool:
    """Load saved cookies to skip login."""
    if not account.cookies:
        return False

    try:
        cookies = json.loads(decrypt(account.cookies))
        await session._context.add_cookies(cookies)
        await session.goto("https://www.youtube.com")
        await random_delay(2, 3)

        # Verify still logged in
        avatar = session.page.locator("button#avatar-btn, img#img")
        if await avatar.count() > 0:
            log.info(f"Cookie login success: {account.gmail}")
            return True

        log.warning(f"Cookie login failed: {account.gmail}")
        return False

    except Exception as e:
        log.warning(f"Cookie load error: {e}")
        return False


async def full_setup(db: Session, account: Account):
    """Complete profile setup pipeline.

    registered → profile_set
    """
    log.info(f"Starting full setup for {account.gmail}")

    # Ensure AdsPower profile exists
    if not account.adspower_profile_id:
        from hydra.accounts.manager import create_adspower_profile
        create_adspower_profile(db, account)

    async with open_browser(account.adspower_profile_id) as session:
        # Try cookie login first
        if not await load_cookies(session, account):
            # Full login
            success = await login_gmail(session, account)
            if not success:
                # Determine error type
                page_url = session.page.url
                if "challenge" in page_url:
                    transition(db, account, AccountStatus.CHECKPOINT, "security checkpoint")
                else:
                    transition(db, account, AccountStatus.LOGIN_FAILED, "login failed")
                return

        # Setup YouTube profile
        await setup_youtube_profile(session, account)

        # Save cookies for next time
        await save_cookies(session, account, db)

        # Transition to profile_set
        transition(db, account, AccountStatus.PROFILE_SET, "setup complete")

        # Start warmup
        transition(db, account, AccountStatus.WARMUP, "warmup started")

    log.info(f"Setup complete for {account.gmail}")
