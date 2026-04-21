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
from worker.channel_actions import (
    rename_channel, change_handle, pick_avatar_file, upload_avatar, _enter_customization,
)
from hydra.core import crypto
from hydra.core.enums import WARMUP_DAYS
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from onboarding.login_fsm import run_login_fsm
from hydra.core.logger import get_logger
from datetime import datetime, timedelta, UTC

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


async def _read_studio_inputs(page) -> dict:
    """Studio 맞춤설정 페이지에서 name/handle 현재값 읽기."""
    await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=20_000)
    import asyncio as _a
    await _a.sleep(3)
    await _enter_customization(page)
    name = await page.evaluate("() => document.querySelector(\"input[placeholder='채널 이름 입력']\")?.value || ''")
    handle = await page.evaluate("() => document.querySelector(\"input[placeholder='핸들 설정']\")?.value || ''")
    return {"name": (name or "").strip(), "handle": (handle or "").strip()}


class ChannelNameGoal:
    name = "channel_name"
    required = True

    async def detect(self, page, acct) -> State:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("channel_plan") or {}).get("title", "").strip()
        if not target:
            return "blocked"
        try:
            cur = await _read_studio_inputs(page)
            return "done" if cur["name"] == target else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("channel_plan") or {}).get("title", "").strip()
        if not target:
            return "blocked"
        try:
            return "done" if await rename_channel(page, target) else "failed"
        except Exception as e:
            log.warning(f"channel_name apply err: {e}")
            return "failed"


class ChannelHandleGoal:
    """현재 핸들이 target 으로 시작하면 done (예: 'roaster91-x6p' 는 'roaster91' 로 시작)."""
    name = "channel_handle"
    required = False

    async def detect(self, page, acct) -> State:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("channel_plan") or {}).get("handle", "").strip()
        if not target:
            return "blocked"
        try:
            cur = await _read_studio_inputs(page)
            return "done" if cur["handle"].lower().startswith(target.lower()) else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("channel_plan") or {}).get("handle", "").strip()
        if not target:
            return "blocked"
        try:
            return "done" if await change_handle(page, target) else "failed"
        except Exception as e:
            log.warning(f"channel_handle apply err: {e}")
            return "failed"


class AvatarGoal:
    """avatar_policy == 'set_during_warmup' 일 때만 실행. 서버 avatar-btn src 로 판정."""
    name = "avatar"
    required = False

    def _policy_enabled(self, acct) -> bool:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        cp = persona.get("channel_plan") or {}
        return cp.get("avatar_policy") == "set_during_warmup"

    async def detect(self, page, acct) -> State:
        if not self._policy_enabled(acct):
            return "blocked"
        try:
            await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=20_000)
            import asyncio as _a
            await _a.sleep(3)
            src = await page.evaluate("() => document.querySelector('#avatar-btn img')?.src || ''")
            if not src:
                return "not_done"
            return "not_done" if "AIdro_" in src else "done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        import json as _json
        if not self._policy_enabled(acct):
            return "blocked"
        persona = _json.loads(acct.persona) if acct.persona else {}
        cp = persona.get("channel_plan") or {}
        path = pick_avatar_file(persona, cp)
        if not path:
            return "failed"
        try:
            return "done" if await upload_avatar(page, path) else "failed"
        except Exception as e:
            log.warning(f"avatar apply err: {e}")
            return "failed"


class FinalizeWarmupGoal:
    """필수 goals 모두 통과한 계정만 warmup 상태로 전이. DB 전용."""
    name = "finalize_warmup"
    required = False

    async def detect(self, page, acct) -> State:
        return "done" if acct.status == "warmup" else "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        db = SessionLocal()
        try:
            row = db.get(Account, acct.id)
            row.warmup_group = "B"
            if row.status != "warmup":
                row.status = "warmup"
            if not row.onboard_completed_at:
                row.onboard_completed_at = datetime.now(UTC)
            if not row.warmup_start_date:
                row.warmup_start_date = datetime.now(UTC)
            row.warmup_end_date = row.warmup_start_date + timedelta(
                days=WARMUP_DAYS.get("B", 3)
            )
            if (row.warmup_day or 0) == 0:
                row.warmup_day = 0
            db.commit()
        finally:
            db.close()
        return "done"


ALL_GOALS: list[Goal] = [
    LoginGoal(),
    UiLangKoGoal(),
    DisplayNameGoal(),
    TotpSecretGoal(),
    VideoLangKoGoal(),
    IdentityChallengeGoal(),
    ChannelNameGoal(),
    ChannelHandleGoal(),
    AvatarGoal(),
    FinalizeWarmupGoal(),
]
