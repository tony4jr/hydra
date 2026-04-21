"""Login URL state machine.

현재 URL 을 감지해 해당 핸들러를 실행하고, URL 전이될 때까지 대기 → 반복.
같은 URL 이 2회 연속 나오면 '막힘' 으로 판정, abort.
"""
import asyncio
import random

from hydra.browser.actions import type_human, random_delay
from hydra.core.logger import get_logger
from onboarding import selectors as S

log = get_logger("onboarding.login_fsm")

MAX_ITER = 20
URL_CHANGE_TIMEOUT_MS = 15_000


def match_handler_name(url: str) -> str | None:
    """URL → 핸들러 이름. None 이면 unknown 상태."""
    if url.startswith(S.URL_MYACCOUNT) or url.startswith(S.URL_YOUTUBE):
        return "DONE"
    if url.startswith(S.URL_SIGNIN_IDENTIFIER):
        return "type_email"
    if url.startswith(S.URL_CHALLENGE_PWD):
        return "type_password"
    if url.startswith(S.URL_CHALLENGE_IPE_VERIFY):
        return "submit_recovery_code"
    if url.startswith(S.URL_CHALLENGE_SELECTION):
        return "pick_recovery_option"
    if url.startswith(S.URL_GDS_PREFIX):
        return "click_skip"
    return None


async def _type_email(page, acct):
    inp = page.locator(S.EMAIL_INPUT)
    await inp.wait_for(timeout=10_000)
    await type_human(page, S.EMAIL_INPUT, acct.gmail, typing_style="typist")
    await random_delay(0.5, 1.2)
    await page.keyboard.press("Enter")


async def _type_password(page, acct):
    from hydra.core import crypto
    pwd = crypto.decrypt(acct.password) if acct.password else None
    if not pwd:
        raise RuntimeError("no password in DB")
    await page.locator(S.PASSWORD_INPUT).wait_for(timeout=10_000)
    await type_human(page, S.PASSWORD_INPUT, pwd, typing_style="typist")
    await random_delay(0.5, 1.2)
    await page.keyboard.press("Enter")


async def _submit_recovery_code(page, acct):
    from worker.mail_911panel import fetch_2fa_code
    if not acct.recovery_email:
        raise RuntimeError("no recovery_email in DB")
    mail_page = await page.context.new_page()
    try:
        code = await fetch_2fa_code(mail_page, acct.recovery_email)
    finally:
        try:
            await mail_page.close()
        except Exception:
            pass
    if not code:
        raise RuntimeError("911panel: no code")
    await page.bring_to_front()
    await page.locator(S.RECOVERY_CODE_INPUT).first.wait_for(timeout=15_000)
    await type_human(page, "input[name='Pin']", code, typing_style="typist")
    await random_delay(0.5, 1.0)
    await page.keyboard.press("Enter")


async def _pick_recovery_option(page, acct):
    """Challenge selection 페이지에서 복구 이메일 옵션 클릭."""
    if not acct.recovery_email:
        raise RuntimeError("no recovery_email")
    user0 = acct.recovery_email.split("@")[0][:1].lower()
    domain = acct.recovery_email.split("@")[1][:3].lower()
    clicked = await page.evaluate(
        """({user0, domain}) => {
          const items = Array.from(document.querySelectorAll('[role="link"], [role="button"]'))
            .filter(el => el.offsetParent !== null);
          const hit = items.find(el => {
            const t = (el.textContent || '').toLowerCase();
            if (!t.includes('@' + domain)) return false;
            const before = t.split('@')[0].replace(/[^a-z0-9]/g, '');
            return before.startsWith(user0);
          });
          if (hit) { hit.click(); return true; }
          return false;
        }""",
        {"user0": user0, "domain": domain},
    )
    if not clicked:
        raise RuntimeError("recovery option not found")


async def _click_skip(page, acct):
    """GDS 프롬프트 skip — Huỷ/Bỏ qua/Cancel 등 여러 로컬 지원."""
    labels = [
        "Huỷ", "Hủy", "Bỏ qua", "Bo qua", "Skip",
        "Cancel", "취소", "건너뛰기", "나중에",
        "Nhắc lại sau", "Maybe later",
    ]
    clicked = await page.evaluate(
        """(labels) => {
          const btns = Array.from(document.querySelectorAll('button, a[role="button"]'))
            .filter(b => b.offsetParent !== null);
          const hit = btns.find(b => labels.includes((b.innerText||'').trim()));
          if (hit) { hit.click(); return true; }
          return false;
        }""",
        labels,
    )
    if not clicked:
        raise RuntimeError("no skip button on gds page")


HANDLERS = {
    "type_email": _type_email,
    "type_password": _type_password,
    "submit_recovery_code": _submit_recovery_code,
    "pick_recovery_option": _pick_recovery_option,
    "click_skip": _click_skip,
}


async def run_login_fsm(page, acct) -> tuple[str, str]:
    """FSM 실행. (status, final_url) 반환.

    status: done | failed_unknown | failed_stuck | failed_max_iter | failed_handler

    시작부 강제로 signin URL 로 navigate — 어떤 page 상태든 FSM 이 항상 같은 시작점.
    """
    from worker.login import check_logged_in
    try:
        await page.goto("https://accounts.google.com/signin", wait_until="domcontentloaded", timeout=20_000)
    except Exception as e:
        log.warning(f"signin goto err: {e}")

    prev_url = None
    same_count = 0
    for i in range(MAX_ITER):
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8_000)
        except Exception:
            pass
        await asyncio.sleep(random.uniform(1.0, 2.0))

        url = page.url
        hname = match_handler_name(url)
        log.info(f"[fsm iter={i}] url={url[:80]} → {hname}")

        if hname is None:
            return "failed_unknown", url
        if hname == "DONE":
            # URL 만으론 부족 — 실제 로그인 여부 재확인 (fresh 계정 youtube.com 홈은
            # URL 은 일치해도 실제 로그인 안 된 상태가 있음)
            if await check_logged_in(page):
                return "done", url
            # 로그인 안 된 youtube/myaccount — signin 으로 강제 이동 후 loop 재개
            log.info(f"[fsm iter={i}] DONE URL but not logged in — navigate to signin")
            try:
                await page.goto("https://accounts.google.com/signin",
                                wait_until="domcontentloaded", timeout=20_000)
            except Exception:
                pass
            prev_url = None  # 새 시작점이므로 stuck 카운터 리셋
            continue

        if url == prev_url:
            same_count += 1
            # 같은 URL 이 2회 연속 (첫 방문 후 전이 안 됨 + 재방문) → 막힘
            if same_count >= 1:
                return "failed_stuck", url
        else:
            same_count = 0
        prev_url = url

        handler = HANDLERS.get(hname)
        try:
            await handler(page, acct)
        except Exception as e:
            log.warning(f"handler {hname} raised: {e}")
            return "failed_handler", url

        # URL 전이 대기 — 같은 URL 이면 타임아웃 후 다시 loop
        try:
            async with asyncio.timeout(URL_CHANGE_TIMEOUT_MS / 1000):
                while page.url == url:
                    await asyncio.sleep(0.5)
        except TimeoutError:
            pass  # URL 전이 안 일어남 — 다음 루프에서 재평가

    return "failed_max_iter", page.url
