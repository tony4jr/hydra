"""각 온보딩 목표의 detect + apply 인터페이스.

Goal 은 동일 인터페이스로 호출되어 verifier 가 순차 실행한다.
실행 가능한 goals 는 이 파일 하단의 ALL_GOALS 리스트에 등록.
"""
from typing import Literal, Protocol, runtime_checkable


State = Literal["done", "not_done", "blocked"]
ApplyResult = Literal["done", "failed", "blocked"]


@runtime_checkable
class Goal(Protocol):
    name: str
    required: bool

    async def detect(self, page, acct) -> State: ...
    async def apply(self, page, acct) -> ApplyResult: ...


# --- 실제 goal 구현 ---
from worker.login import check_logged_in
from worker.language_setup import ensure_korean_language
from worker.google_account import update_account_name
from worker.google_account import register_otp_authenticator, handle_identity_challenge
from worker.data_saver import set_primary_video_language
from hydra.core import crypto
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from onboarding.login_fsm import run_login_fsm
from hydra.core.logger import get_logger

log = get_logger("onboarding.goals")


class LoginGoal:
    name = "login"
    required = True

    async def detect(self, page, acct) -> State:
        try:
            await page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            pass
        return "done" if await check_logged_in(page) else "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        status, final_url = await run_login_fsm(page, acct)
        log.info(f"login_fsm → {status} @ {final_url[:80]}")
        return "done" if status == "done" else "failed"


class UiLangKoGoal:
    name = "ui_lang_ko"
    required = True

    async def detect(self, page, acct) -> State:
        try:
            await page.goto("https://myaccount.google.com/language",
                            wait_until="domcontentloaded", timeout=20_000)
            ok = await page.evaluate("""() => {
              const t = document.body.innerText || '';
              return /선호 언어[\\s\\S]{0,40}한국어/.test(t);
            }""")
            return "done" if ok else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        try:
            return "done" if await ensure_korean_language(page) else "failed"
        except Exception as e:
            log.warning(f"ui_lang_ko apply err: {e}")
            return "failed"


class DisplayNameGoal:
    name = "display_name"
    required = True

    async def detect(self, page, acct) -> State:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("name") or "").strip()
        if not target:
            return "blocked"
        try:
            await page.goto("https://myaccount.google.com/profile/name",
                            wait_until="domcontentloaded", timeout=20_000)
            txt = await page.evaluate("() => document.body.innerText || ''")
            compact = target.replace(" ", "")
            return "done" if compact in txt.replace(" ", "") else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("name") or "").strip()
        if not target:
            return "blocked"
        pwd = crypto.decrypt(acct.password) if acct.password else None
        try:
            return "done" if await update_account_name(page, target, password=pwd) else "failed"
        except Exception as e:
            log.warning(f"display_name apply err: {e}")
            return "failed"


class TotpSecretGoal:
    """B그룹 — DB 에 totp_secret 있으면 done. 외부 관찰 불가."""
    name = "totp_secret"
    required = False

    async def detect(self, page, acct) -> State:
        return "done" if acct.totp_secret else "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        pwd = crypto.decrypt(acct.password) if acct.password else None
        if not pwd:
            return "failed"
        try:
            secret, _activated = await register_otp_authenticator(page, pwd)
        except Exception as e:
            log.warning(f"totp apply err: {e}")
            return "failed"
        if not secret:
            return "failed"
        db = SessionLocal()
        try:
            row = db.get(Account, acct.id)
            if not row.totp_secret:
                row.totp_secret = crypto.encrypt(secret)
                db.commit()
        finally:
            db.close()
        return "done"


class VideoLangKoGoal:
    name = "video_lang_ko"
    required = False

    async def detect(self, page, acct) -> State:
        try:
            await page.goto("https://www.youtube.com/account_playback",
                            wait_until="domcontentloaded", timeout=20_000)
            ok = await page.evaluate("""() => {
              const t = document.body.innerText || '';
              return /기본 언어[\\s\\S]{0,120}한국어/.test(t);
            }""")
            return "done" if ok else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        try:
            return "done" if await set_primary_video_language(page, "한국어") else "failed"
        except Exception as e:
            log.warning(f"video_lang apply err: {e}")
            return "failed"


class IdentityChallengeGoal:
    """Studio 진입 → 본인 인증 모달 감지. locked 면 blocked + 쿨다운."""
    name = "identity_challenge"
    required = True

    async def detect(self, page, acct) -> State:
        try:
            await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=20_000)
            import asyncio as _a
            await _a.sleep(3)
            has = await page.evaluate("""() => {
              const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role="dialog"]'))
                .filter(d => d.offsetParent !== null);
              return dlgs.some(d => (d.innerText||'').includes('본인 인증'));
            }""")
            return "not_done" if has else "done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        pwd = crypto.decrypt(acct.password) if acct.password else None
        try:
            result = await handle_identity_challenge(page, pwd)
        except Exception as e:
            log.warning(f"identity apply err: {e}")
            return "failed"
        if result == "locked":
            from datetime import datetime, timedelta, UTC
            db = SessionLocal()
            try:
                row = db.get(Account, acct.id)
                row.status = "identity_challenge"
                row.identity_challenge_until = datetime.now(UTC) + timedelta(days=7)
                row.identity_challenge_count = (row.identity_challenge_count or 0) + 1
                db.commit()
            finally:
                db.close()
            return "blocked"
        return "done"


ALL_GOALS: list[Goal] = [
    LoginGoal(),
    UiLangKoGoal(),
    DisplayNameGoal(),
    TotpSecretGoal(),
    VideoLangKoGoal(),
    IdentityChallengeGoal(),
]
