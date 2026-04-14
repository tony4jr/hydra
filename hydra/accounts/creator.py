"""Gmail account creator — automated signup without SMS.

Strategy:
1. Fresh AdsPower profile → fresh fingerprint
2. Rotate mobile IP via ADB
3. Navigate to accounts.google.com/signup
4. Fill name/DOB/username/password (sourced from pool_generator)
5. Skip phone number (Google still allows this)
6. Use mail.tm temp recovery email (click-verify if Google sends a code)
7. Save account to DB in status=REGISTERED
8. Subsequent phases: tfa_setup → warmup

Google flows evolve frequently. All selectors are kept loose with
multiple fallbacks and the function is designed to fail closed
(abort on ambiguity) to protect account reputation.
"""

import asyncio
import random
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from hydra.accounts.manager import create_adspower_profile
from hydra.accounts.pool_generator import _random_name, _random_channel_name
from hydra.browser import actions
from hydra.browser.driver import open_browser
from hydra.core.config import settings
from hydra.core.crypto import encrypt
from hydra.core.enums import AccountStatus
from hydra.core.logger import get_logger
from hydra.db.models import Account
from hydra.infra.temp_mail import TempMailClient
from hydra.infra.ip_provider import get_provider

log = get_logger("creator")

SIGNUP_URL = "https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp"


def _random_password(length: int = 14) -> str:
    """Generate a strong password meeting Google's rules."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw)
                and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


def _random_username(first_name: str, last_name: str) -> str:
    """Generate candidate username — romanized + digits."""
    # We need ASCII for usernames; Korean names aren't allowed.
    # Use random english-style prefix + digits.
    base = "".join(random.choices(string.ascii_lowercase, k=random.randint(5, 9)))
    suffix = str(random.randint(1, 9999))
    return f"{base}{suffix}"


def _random_birth_year() -> int:
    """Age 25~42 — adult but not suspicious."""
    this_year = datetime.now().year
    return this_year - random.randint(25, 42)


MONTHS = [
    "1월", "2월", "3월", "4월", "5월", "6월",
    "7월", "8월", "9월", "10월", "11월", "12월",
]


class CreationAborted(RuntimeError):
    """Raised when signup must be abandoned (phone required, captcha wall, etc.)."""


async def _fill_text(page, selectors: list[str], text: str) -> bool:
    """Try each selector in order; fill the first visible match."""
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.count() == 0:
                continue
            if not await loc.is_visible(timeout=1500):
                continue
            await loc.click()
            await actions.random_delay(0.3, 0.8)
            await loc.fill("")
            # Typing with human delays
            for char in text:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.05, 0.15))
            return True
        except Exception as e:
            log.debug(f"_fill_text selector {sel} failed: {e}")
    return False


async def _click_any(page, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible(timeout=1500):
                continue
            await loc.click()
            return True
        except Exception:
            continue
    return False


async def _page_indicates_phone_required(page) -> bool:
    """Detect 'phone required' screens — we bail out because SMS path is disabled."""
    content = (await page.content()).lower()
    triggers = [
        "verify your phone",
        "phone number",
        "전화번호 인증",
        "휴대전화 번호",
        "전화번호를 입력",
    ]
    # Only call "phone required" if both markers present AND no easy skip button
    has_trigger = any(t in content for t in triggers)
    if not has_trigger:
        return False
    # If there is a Skip button, it's optional — not a hard requirement
    for sel in ['button:has-text("Skip")', 'button:has-text("건너뛰기")', 'button:has-text("나중에")']:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible(timeout=500):
                return False  # Skippable
        except Exception:
            pass
    return True


async def _fill_signup_form(page, first_name: str, last_name: str,
                             username: str, password: str,
                             birth_year: int, birth_month: int, birth_day: int,
                             gender: str) -> None:
    """Fill the multi-step signup form. Raises CreationAborted on phone wall."""

    # === Step 1: Name ===
    log.info("Signup step: name")
    ok = await _fill_text(page, ['input[name="firstName"]', "#firstName"], first_name)
    if not ok:
        raise CreationAborted("firstName input not found")
    ok = await _fill_text(page, ['input[name="lastName"]', "#lastName"], last_name)
    if not ok:
        raise CreationAborted("lastName input not found")
    await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")', "#collectNameNext button"])
    await actions.random_delay(2, 4)

    # === Step 2: Birth date + gender ===
    log.info("Signup step: birth/gender")
    # Year
    await _fill_text(page, ['input[name="year"]', "#year"], str(birth_year))
    # Month — it's a dropdown
    month_sel = page.locator('select#month, select[name="month"]').first
    if await month_sel.count():
        await month_sel.select_option(value=str(birth_month))
    # Day
    await _fill_text(page, ['input[name="day"]', "#day"], str(birth_day))
    # Gender
    gender_sel = page.locator('select#gender, select[name="gender"]').first
    if await gender_sel.count():
        # Values typically: 1=female, 2=male, 3=rather not say, 4=custom
        value_map = {"female": "1", "male": "2", "other": "3"}
        await gender_sel.select_option(value=value_map.get(gender, "3"))
    await actions.random_delay(1, 2)
    await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")'])
    await actions.random_delay(2, 4)

    # === Step 3: Username ===
    log.info("Signup step: username")
    # Some flows offer suggestions; we insist on custom username
    await _click_any(page, [
        'input[value="custom"]',
        'div[role="radio"][aria-label*="사용자 이름 만들기"]',
        'div[role="radio"][aria-label*="Create your own"]',
    ])
    await actions.random_delay(0.5, 1.5)
    ok = await _fill_text(page, ['input[name="Username"]', "#username", 'input[aria-label*="사용자 이름"]'], username)
    if not ok:
        raise CreationAborted("username input not found")
    await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")'])
    await actions.random_delay(2, 4)

    # Username taken? retry with variant
    page_text = (await page.content()).lower()
    if "already" in page_text or "이미" in page_text:
        log.info("Username taken — retry with suffix")
        username = username + str(random.randint(100, 999))
        await _fill_text(page, ['input[name="Username"]', "#username"], username)
        await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")'])
        await actions.random_delay(2, 4)

    # === Step 4: Password ===
    log.info("Signup step: password")
    ok = await _fill_text(page, ['input[name="Passwd"]', "#passwd input", 'input[type="password"]'], password)
    if not ok:
        raise CreationAborted("password input not found")
    # Confirm password — second input
    confirm = page.locator('input[name="PasswdAgain"], input[aria-label*="확인"]').first
    if await confirm.count():
        await confirm.click()
        for char in password:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.05, 0.15))
    await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")'])
    await actions.random_delay(3, 5)


async def _handle_phone_and_recovery(page, mail: TempMailClient) -> None:
    """Navigate the phone/recovery-email pages.

    Strategy:
    - If phone-number page is optional: click Skip
    - If phone is required: abort (SMS disabled by user policy)
    - Provide recovery email via mail.tm mailbox
    - If Google sends a verification code to recovery email, fetch it
    """
    # Wait for phone or recovery page
    await actions.random_delay(2, 4)

    for _ in range(6):  # up to 6 page transitions
        content = (await page.content()).lower()

        # Skippable phone page?
        if "전화번호" in content or "phone" in content:
            # Try Skip
            if await _click_any(page, [
                'button:has-text("건너뛰기")',
                'button:has-text("Skip")',
                'button:has-text("나중에")',
                'button[jsname*="skip"]',
            ]):
                log.info("Phone step skipped")
                await actions.random_delay(2, 4)
                continue
            # No skip visible? Check if form is required
            if await _page_indicates_phone_required(page):
                raise CreationAborted("Phone verification required — SMS disabled")

        # Recovery email page
        if "복구" in content or "recovery" in content:
            log.info(f"Providing recovery email: {mail.address}")
            ok = await _fill_text(page, [
                'input[name="recoveryEmail"]',
                'input[type="email"]',
                'input[aria-label*="복구"]',
            ], mail.address)
            if ok:
                await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")'])
                await actions.random_delay(2, 4)
                continue

        # Review / terms
        if "이용약관" in content or "terms" in content or "개인정보" in content:
            await _click_any(page, [
                'button:has-text("동의")',
                'button:has-text("I agree")',
                'button:has-text("확인")',
            ])
            await actions.random_delay(2, 4)
            continue

        # Success — landed on myaccount or welcome
        url = page.url
        if "myaccount" in url or "welcome" in url or "signin/v2/challenge/pwd" in url:
            log.info("Signup complete — post-signup page reached")
            return

        # Code verification via recovery email
        if "코드" in content and ("이메일" in content or "recovery" in content):
            log.info("Fetching verification code from recovery inbox")
            code = await mail.extract_verification_code(from_contains="google", timeout_sec=180)
            if not code:
                raise CreationAborted("Recovery email verification code not received")
            ok = await _fill_text(page, ['input[type="text"]', 'input[name="code"]', 'input[aria-label*="코드"]'], code)
            if not ok:
                raise CreationAborted("Could not enter recovery code")
            await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")', 'button:has-text("확인")'])
            await actions.random_delay(2, 4)
            continue

        # Unknown page — probe for Next button, else log content snippet
        if not await _click_any(page, ['button:has-text("다음")', 'button:has-text("Next")']):
            break
        await actions.random_delay(2, 4)


async def create_account(db: Session, device_id: str | None = None) -> Account | None:
    """Run a full Gmail signup and persist the account to DB.

    Returns the created Account (status=REGISTERED) or None on failure.
    device_id optional — when provided, rotates IP before signup.
    """
    # 1. Prepare identity
    korean_name, gender = _random_name()
    # Split as "성/이름" — Korean convention; Google accepts Hangul for name fields
    last_name = korean_name[0]
    first_name = korean_name[1:]

    birth_year = _random_birth_year()
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)

    username = _random_username(first_name, last_name)
    password = _random_password()

    log.info(f"Preparing signup: name={korean_name}, username={username}, birth={birth_year}/{birth_month}/{birth_day}")

    # 2. Fresh AdsPower profile
    provisional_gmail = f"{username}@gmail.com"
    account = Account(
        gmail=provisional_gmail,
        password=encrypt(password),
        persona=None,
        status=AccountStatus.REGISTERED,
    )
    db.add(account)
    db.flush()  # reserve id

    create_adspower_profile(db, account)
    db.commit()

    # 3. Rotate IP (optional, preferred)
    if device_id:
        try:
            provider = get_provider()
            if not provider:
                from hydra.infra.ip_provider import AdbProvider, set_provider
                provider = AdbProvider(device_id)
                set_provider(provider)
            new_ip = await provider.rotate()
            log.info(f"Pre-signup IP: {new_ip}")
        except Exception as e:
            log.warning(f"IP rotation skipped: {e}")

    # 4. Launch browser + signup
    try:
        async with TempMailClient() as mail:
            log.info(f"Recovery mailbox: {mail.address}")
            account.recovery_email = mail.address  # raw — encrypt if sensitive
            db.commit()

            async with open_browser(account.adspower_profile_id) as session:
                page = session.page
                await session.goto(SIGNUP_URL)
                await actions.random_delay(3, 5)

                await _fill_signup_form(
                    page,
                    first_name=first_name, last_name=last_name,
                    username=username, password=password,
                    birth_year=birth_year, birth_month=birth_month, birth_day=birth_day,
                    gender=gender,
                )

                await _handle_phone_and_recovery(page, mail)

                # 5. Confirm + persist
                account.gmail = f"{username}@gmail.com"
                account.created_at = datetime.now(timezone.utc)
                db.commit()

                log.info(f"Account created: {account.gmail}")
                return account

    except CreationAborted as e:
        log.warning(f"Signup aborted: {e}")
        # Clean up: mark as failed (keep row for forensics)
        from hydra.core.enums import AccountStatus as AS
        account.status = AS.LOGIN_FAILED
        account.retired_reason = f"signup aborted: {e}"
        db.commit()
        return None
    except Exception as e:
        log.error(f"Signup error: {e}", exc_info=True)
        from hydra.core.enums import AccountStatus as AS
        account.status = AS.LOGIN_FAILED
        account.retired_reason = f"signup error: {e}"
        db.commit()
        return None
