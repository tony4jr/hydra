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
    if url.startswith(S.URL_CHALLENGE_DP):
        return "DEAD"
    if url.startswith(S.URL_CHALLENGE_IPP):
        return "bypass_ipp"
    if url.startswith(S.URL_SIGNIN_IDENTIFIER):
        return "type_email"
    if url.startswith(S.URL_CHALLENGE_PWD):
        return "type_password"
    if url.startswith(S.URL_CHALLENGE_IPE_VERIFY):
        return "submit_recovery_code"
    if url.startswith(S.URL_CHALLENGE_SELECTION):
        return "pick_recovery_option"
    if url.startswith(S.URL_CHALLENGE_TOTP):
        return "submit_totp_code"
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

    # 911panel 탭 오픈 + 코드 추출 — 네트워크 블립 (net::ERR_ABORTED) 대응 위해 최대 3회 재시도
    code = None
    last_err = None
    for attempt in range(3):
        mail_page = None
        try:
            mail_page = await page.context.new_page()
            code = await fetch_2fa_code(mail_page, acct.recovery_email)
            if code:
                break
            last_err = "no code received"
        except Exception as e:
            last_err = str(e)
            log.warning(f"fetch_2fa_code attempt {attempt+1} failed: {e}")
        finally:
            if mail_page is not None:
                try:
                    await mail_page.close()
                except Exception:
                    pass
        if attempt < 2:
            await asyncio.sleep(3)  # backoff

    if not code:
        raise RuntimeError(f"911panel: no code after retries ({last_err})")

    await page.bring_to_front()
    await page.locator(S.RECOVERY_CODE_INPUT).first.wait_for(timeout=15_000)
    await type_human(page, "input[name='Pin']", code, typing_style="typist")
    await random_delay(0.5, 1.0)
    await page.keyboard.press("Enter")


async def _submit_totp_code(page, acct):
    """/challenge/totp — pyotp 로 현재 6자리 생성해 입력."""
    import pyotp
    from hydra.core import crypto
    if not acct.totp_secret:
        raise RuntimeError("no totp_secret in DB for this account")
    secret = crypto.decrypt(acct.totp_secret)
    code = pyotp.TOTP(secret).now()
    inp = page.locator(
        "input[type='tel'], input[type='text'][name*='totpPin'], input[name='Pin'], input[type='text']"
    ).first
    await inp.wait_for(timeout=10_000)
    await inp.click()
    await random_delay(0.3, 0.6)
    await page.keyboard.type(code, delay=random.randint(70, 140))
    await random_delay(0.4, 0.8)
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


async def _click_bbox_random(page, box: dict, *, x_frac=(0.25, 0.75), y_frac=(0.3, 0.7)):
    """요소 bounding box 내부 랜덤 좌표에 마우스로 이동 + 클릭 (해상도 무관).

    중앙 고정 방지 + 짧은 approach + 클릭 hold 지연으로 봇 패턴 회피.
    """
    cx = box["x"] + box["w"] * random.uniform(*x_frac)
    cy = box["y"] + box["h"] * random.uniform(*y_frac)
    await page.mouse.move(cx - 12, cy - 6, steps=6)
    await asyncio.sleep(random.uniform(0.15, 0.35))
    await page.mouse.move(cx, cy, steps=4)
    await page.mouse.click(cx, cy, delay=random.randint(40, 90))


async def _bypass_ipp(page, acct):
    """/challenge/ipp/* (전화번호 인증) 우회.

    경로: 이메일 chip 클릭 → /accountchooser → 본인 계정 row 클릭 → /challenge/pwd
    이후 FSM 의 _type_password 핸들러가 이어받음.

    성공 시 acct._ipp_flagged=True 세팅 — LoginGoal/verifier 가 감지해서 Google
    계정 전용 goal (ui_lang_ko, display_name, totp_secret) 을 skip.

    참고: ipp 뜬 계정은 Google 계정 정보 수정 불가. YouTube 설정만 가능.
    """
    email = (acct.gmail or "").lower()

    # 1) 이메일 chip bounding box 찾기 — role=link/combobox 중 @gmail.com 포함 최소 너비
    chip = await page.evaluate(
        """(email) => {
          const cands = Array.from(document.querySelectorAll(
            '[role="link"], [role="combobox"], [role="button"]'
          )).filter(e => e.offsetParent !== null);
          let best = null, bestW = 9999;
          for (const e of cands) {
            const t = (e.innerText||'').toLowerCase();
            const a = (e.getAttribute('aria-label')||'').toLowerCase();
            if (!t.includes(email) && !a.includes(email)) continue;
            const r = e.getBoundingClientRect();
            if (r.width < 10 || r.height < 10) continue;
            if (r.width < bestW) { best = e; bestW = r.width; }
          }
          if (!best) return null;
          const r = best.getBoundingClientRect();
          return {x: r.x, y: r.y, w: r.width, h: r.height};
        }""",
        email,
    )
    if not chip:
        raise RuntimeError("ipp bypass: email chip not found")
    await _click_bbox_random(page, chip)

    # 2) accountchooser 대기
    async with asyncio.timeout(10):
        while "accountchooser" not in page.url:
            await asyncio.sleep(0.3)
    await asyncio.sleep(random.uniform(0.8, 1.5))

    # 3) accountchooser 에서 본인 계정 row — 이메일 포함하면서 면적 가장 작은 클릭 가능 요소
    row = await page.evaluate(
        """(email) => {
          const cands = Array.from(document.querySelectorAll(
            '[role="link"], [role="button"], li, div'
          )).filter(e => e.offsetParent !== null);
          let best = null, bestArea = 1e12;
          for (const e of cands) {
            const t = (e.innerText||'').toLowerCase();
            if (!t.includes(email)) continue;
            const r = e.getBoundingClientRect();
            if (r.width < 50 || r.height < 30) continue;
            const area = r.width * r.height;
            if (area < bestArea) { best = e; bestArea = area; }
          }
          if (!best) return null;
          const r = best.getBoundingClientRect();
          return {x: r.x, y: r.y, w: r.width, h: r.height};
        }""",
        email,
    )
    if not row:
        raise RuntimeError("ipp bypass: account row not found on accountchooser")
    await _click_bbox_random(page, row)

    # 4) pwd 페이지로 이동 대기 (FSM loop 이 _type_password 로 받음)
    async with asyncio.timeout(10):
        while "/signin/challenge/pwd" not in page.url:
            await asyncio.sleep(0.3)

    # 플래그 세팅 — LoginGoal → verifier 에서 Google 계정 전용 goal skip
    acct._ipp_flagged = True
    log.info(f"ipp bypass succeeded for {email} — _ipp_flagged=True")


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
    "submit_totp_code": _submit_totp_code,
    "pick_recovery_option": _pick_recovery_option,
    "bypass_ipp": _bypass_ipp,
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
        if hname == "DEAD":
            # /challenge/dp — Google 이 사실상 계정 차단. 프로필과 함께 폐기.
            return "dead", url
        if hname == "DONE":
            # myaccount.google.com 에 도달 = Google 로그인 완료 확실. (이 URL 접근
            # 자체가 로그인 요구 — 미로그인이면 signin 으로 리다이렉트됨)
            if url.startswith(S.URL_MYACCOUNT):
                return "done", url
            # youtube.com 홈 은 비로그인 상태로도 URL 이 일치함 → YT avatar-btn 으로
            # 실제 로그인 여부 재확인.
            if await check_logged_in(page):
                return "done", url
            # YT 홈이지만 미로그인 — signin 으로 강제 이동 후 loop 재개
            log.info(f"[fsm iter={i}] YT DONE URL but not logged in — navigate to signin")
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
