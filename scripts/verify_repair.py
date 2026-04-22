"""계정 1~17 검증 + 미비 작업 보정.

각 계정에 대해 온보딩 단계를 순서대로 체크하고, 미완성 항목만 즉시 보정.
자연 탐색(Phase 7) 은 제외. identity_challenge 잠긴 계정은 skip.

에러 발생 시 그 즉시 중단 + 어떤 단계에서 왜 실패했는지 로그.

계정 간 IP 로테이션 필수.
"""
import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

from hydra.browser.adspower import AdsPowerClient
from hydra.core import crypto
from hydra.core.enums import WARMUP_DAYS
from hydra.db.models import Account
from hydra.db.session import SessionLocal
from worker.channel_actions import (
    change_handle, pick_avatar_file, rename_channel, upload_avatar,
)
from worker.data_saver import set_primary_video_language
from worker.google_account import (
    handle_identity_challenge, register_otp_authenticator, update_account_name,
)
from worker.language_setup import ensure_korean_language
from worker.login import auto_login, check_logged_in


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger("verify_repair")

LOG_PATH = Path("/tmp/hydra_verify_repair.log")


def llog(msg: str):
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def rotate_ip() -> str:
    try:
        subprocess.run(["adb", "shell", "svc", "data", "disable"], check=True, timeout=10)
        time.sleep(3)
        subprocess.run(["adb", "shell", "svc", "data", "enable"], check=True, timeout=10)
        time.sleep(8)
        return subprocess.check_output(["curl", "-s", "--max-time", "10", "https://api.ipify.org"], timeout=12).decode().strip()
    except Exception as e:
        llog(f"  ip rotate error: {e}")
        return ""


async def verify_account(acct_id: int) -> dict:
    """한 계정 검증 + 보정. 결과 dict."""
    result = {"id": acct_id, "status": "pending", "fixed": [], "error": ""}

    db = SessionLocal()
    try:
        acct = db.get(Account, acct_id)
        if not acct:
            result["status"] = "not_found"
            return result
        if acct.status in ("identity_challenge", "suspended", "retired"):
            result["status"] = "skipped"
            result["reason"] = f"status={acct.status}"
            return result
        profile_id = acct.adspower_profile_id
        if not profile_id:
            result["status"] = "no_profile"
            return result
        email = acct.gmail
        password = crypto.decrypt(acct.password)
        recovery = acct.recovery_email
        persona = json.loads(acct.persona) if acct.persona else {}
        needs_totp = not acct.totp_secret
    finally:
        db.close()

    persona_name = persona.get("name") or ""
    cp = persona.get("channel_plan") or {}
    target_title = cp.get("title") or ""
    target_handle = cp.get("handle") or ""
    avatar_policy = cp.get("avatar_policy")

    # IP rotate
    new_ip = rotate_ip()
    llog(f"  IP → {new_ip or 'FAILED'}")
    if not new_ip:
        result["status"] = "ip_fail"
        return result

    adsp = AdsPowerClient()
    browser_info = adsp.start_browser(profile_id)
    ws = browser_info.get("ws_endpoint")
    debug_port = browser_info.get("debug_port")
    cdp = f"http://127.0.0.1:{debug_port}"
    llog(f"  AdsPower profile={profile_id} port={debug_port}")
    await asyncio.sleep(3)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp)
            ctx = browser.contexts[0]
            work = None
            for pg in ctx.pages:
                if "youtube.com" in pg.url or "google.com" in pg.url:
                    work = pg; break
            if work is None:
                work = ctx.pages[0] if ctx.pages else await ctx.new_page()
            for pg in list(ctx.pages):
                if pg is not work:
                    try: await pg.close()
                    except: pass
            page = work
            page.on("dialog", lambda d: asyncio.create_task(d.accept()))

            # 이후 자동 열리는 잉여 탭 (AdsPower 알림/extension 팝업 등) 자동 close
            def _close_extra(new_pg):
                async def _do():
                    try:
                        if new_pg is not page:
                            await asyncio.sleep(0.5)
                            await new_pg.close()
                    except Exception:
                        pass
                asyncio.create_task(_do())
            ctx.on("page", _close_extra)

            # 각 phase 전 자연스러운 "생각" 딜레이 — persona speed 반영
            async def phase_gap():
                import random as _r
                await asyncio.sleep(_r.uniform(5.0, 12.0))

            # Phase 1 login
            try:
                await page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(3)
            except Exception:
                pass
            if not await check_logged_in(page):
                llog("  [P1] login required")
                ok = await auto_login(page, email, password, recovery_email=recovery)
                if not ok:
                    result["status"] = "error"
                    result["error"] = "P1 login failed"
                    return result
                result["fixed"].append("login")
            else:
                llog("  [P1] already logged in")

            await phase_gap()
            # Phase 2 UI 언어
            llog("  [P2] UI language check")
            try:
                if await ensure_korean_language(page):
                    result["fixed"].append("ui_lang_ko")
            except Exception as e:
                llog(f"  [P2] error: {e}")

            await phase_gap()
            # Phase 3 display name
            if persona_name:
                llog(f"  [P3] display name check → {persona_name}")
                try:
                    if await update_account_name(page, persona_name, password=password):
                        result["fixed"].append(f"name:{persona_name}")
                except Exception as e:
                    result["status"] = "error"
                    result["error"] = f"P3 name: {e}"
                    return result

            await phase_gap()
            # Phase 5 OTP
            if needs_totp:
                llog("  [P5] OTP register")
                try:
                    secret, activated = await register_otp_authenticator(page, password)
                    if secret:
                        db = SessionLocal()
                        try:
                            a = db.get(Account, acct_id)
                            if not a.totp_secret:
                                a.totp_secret = crypto.encrypt(secret)
                                db.commit()
                                result["fixed"].append("otp_secret")
                        finally:
                            db.close()
                except Exception as e:
                    llog(f"  [P5] error: {e}")
            else:
                llog("  [P5] otp_secret already set")

            await phase_gap()
            # Phase 6 Primary video language
            llog("  [P6] primary video lang")
            try:
                if await set_primary_video_language(page, "한국어"):
                    result["fixed"].append("video_lang_ko")
            except Exception as e:
                llog(f"  [P6] error: {e}")

            await phase_gap()
            # Phase 8.1 Identity challenge pre-check
            llog("  [P8.1] identity challenge pre-check")
            try:
                await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
                await asyncio.sleep(3)
                ch = await handle_identity_challenge(page, password)
                if ch == "locked":
                    db = SessionLocal()
                    try:
                        a = db.get(Account, acct_id)
                        a.status = "identity_challenge"
                        a.identity_challenge_until = datetime.now(UTC) + timedelta(days=7)
                        a.identity_challenge_count = (a.identity_challenge_count or 0) + 1
                        db.commit()
                    finally:
                        db.close()
                    result["status"] = "locked"
                    result["error"] = "identity_challenge locked"
                    return result
            except Exception as e:
                llog(f"  [P8.1] error: {e}")

            await phase_gap()
            # Phase 8.2 Channel name
            if target_title:
                llog(f"  [P8.2] channel rename → {target_title}")
                try:
                    if await rename_channel(page, target_title):
                        result["fixed"].append(f"rename:{target_title}")
                    else:
                        llog("  [P8.2] rename returned False")
                except Exception as e:
                    llog(f"  [P8.2] error: {e}")

            await phase_gap()
            # Phase 8.3 Handle
            if target_handle:
                llog(f"  [P8.3] handle → {target_handle}")
                try:
                    if await change_handle(page, target_handle):
                        result["fixed"].append(f"handle:{target_handle}")
                    else:
                        llog("  [P8.3] change_handle returned False")
                except Exception as e:
                    llog(f"  [P8.3] error: {e}")

            await phase_gap()
            # Phase 9 Avatar
            if avatar_policy == "set_during_warmup":
                avatar_path = pick_avatar_file(persona, cp)
                if avatar_path:
                    # 실제 avatar-btn src 먼저 확인 — 이미 업로드돼있으면 skip
                    try:
                        await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
                        await asyncio.sleep(3)
                        cur_src = await page.evaluate(
                            "() => document.querySelector('#avatar-btn img')?.src || ''"
                        )
                    except Exception:
                        cur_src = ""
                    is_placeholder = ("AIdro_" in cur_src) or ("AJL4" in cur_src) or not cur_src
                    if is_placeholder:
                        llog(f"  [P9] avatar upload ({avatar_path.rsplit('/', 1)[-1]})")
                        try:
                            if await upload_avatar(page, avatar_path):
                                result["fixed"].append("avatar")
                            else:
                                llog("  [P9] avatar upload returned False")
                        except Exception as e:
                            llog(f"  [P9] error: {e}")
                    else:
                        llog("  [P9] avatar already uploaded (non-placeholder)")

            # Phase 10 Finalize
            db = SessionLocal()
            try:
                a = db.get(Account, acct_id)
                a.warmup_group = "B"
                if a.status != "warmup":
                    a.status = "warmup"
                    result["fixed"].append("status→warmup")
                if not a.onboard_completed_at:
                    a.onboard_completed_at = datetime.now(UTC)
                if not a.warmup_start_date:
                    a.warmup_start_date = datetime.now(UTC)
                a.warmup_end_date = a.warmup_start_date + timedelta(days=WARMUP_DAYS.get("B", 3))
                if (a.warmup_day or 0) == 0:
                    a.warmup_day = 0
                db.commit()
            finally:
                db.close()

            result["status"] = "ok"
            return result
    finally:
        try:
            adsp.stop_browser(profile_id)
        except Exception:
            pass


async def main():
    LOG_PATH.write_text("")
    llog("=== onboard start: accounts 18-50 ===")
    summary = {"ok": 0, "skipped": 0, "locked": 0, "error": 0}

    for acct_id in range(18, 51):  # #18~50 온보딩
        llog(f"\n--- account #{acct_id} ---")
        try:
            r = await verify_account(acct_id)
        except Exception as e:
            llog(f"  FATAL: {e!r}")
            summary["error"] += 1
            llog(f"STOP requested due to FATAL error at #{acct_id}")
            break

        llog(f"  result: status={r['status']} fixed={r.get('fixed', [])} error={r.get('error', '')}")

        s = r["status"]
        if s == "ok":
            summary["ok"] += 1
        elif s == "skipped":
            summary["skipped"] += 1
        elif s == "locked":
            summary["locked"] += 1
        else:
            summary["error"] += 1
            llog(f"STOP due to error at #{acct_id}")
            break

        await asyncio.sleep(15)  # 계정 간 15초

    llog("=== done ===")
    llog(f"summary: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
