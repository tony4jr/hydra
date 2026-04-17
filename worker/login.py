"""자동 로그인 + 2FA."""
import pyotp

from hydra.browser.actions import random_delay, type_human


async def check_logged_in(page):
    try:
        avatar = page.locator(
            "button#avatar-btn, img.yt-spec-avatar-shape__image"
        )
        await avatar.wait_for(timeout=5000)
        return True
    except Exception:
        return False


async def auto_login(page, email, password, totp_secret=None):
    try:
        await page.goto("https://accounts.google.com/signin")
        await random_delay(2.0, 4.0)

        email_input = page.locator("input[type='email']")
        await email_input.wait_for(timeout=10000)
        await type_human(page, "input[type='email']", email)
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(2.0, 4.0)

        password_input = page.locator("input[type='password']")
        await password_input.wait_for(timeout=10000)
        await type_human(page, "input[type='password']", password)
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 5.0)

        if totp_secret:
            await _handle_2fa(page, totp_secret)

        await page.wait_for_url("**/myaccount.google.com/**", timeout=15000)
        return True
    except Exception as e:
        print(f"[Login] Failed: {e}")
        return False


async def _handle_2fa(page, totp_secret):
    try:
        totp_input = page.locator("input[name='totpPin'], input#totpPin")
        await totp_input.wait_for(timeout=10000)
        code = pyotp.TOTP(totp_secret).now()
        await type_human(page, "input[name='totpPin'], input#totpPin", code)
        await random_delay(0.5, 1.0)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 5.0)
    except Exception:
        pass


async def ensure_logged_in(page, email, password, totp_secret=None):
    if await check_logged_in(page):
        return True
    return await auto_login(page, email, password, totp_secret)
