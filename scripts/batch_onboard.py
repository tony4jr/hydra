"""계정 1-50 배치 온보딩.

이미 온보딩된 계정(warmup/active 이상) 과 identity_challenge 마킹된 계정은 skip.
각 계정별로:
  1. ADB IP 로테이션 (+ 새 IP 검증)
  2. AdsPower 프로필 open → CDP 연결
  3. auto_login (필요 시) → run_onboard_session
  4. 결과에 identity_challenge:locked 있으면 계정 상태 전환 + 7일 쿨다운
  5. ok && no critical_failures 면 status=warmup + warmup_day=1 으로 finalize
  6. OTP 시크릿 등록됐으면 totp_secret 암호화 저장
  7. AdsPower 프로필 close

로그: /tmp/hydra_batch_onboard.log
"""
import asyncio
import json
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
from worker.onboard_session import run_onboard_session

LOG_PATH = Path("/tmp/hydra_batch_onboard.log")
ACCOUNTS = [15, 16]  # 이번 실행: #15 + #16 만
IP_ROTATE_TIMEOUT = 20  # seconds
PER_ACCOUNT_TIMEOUT = 900  # 15 min


def log(msg: str):
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def rotate_ip() -> str:
    """ADB 로 모바일 데이터 토글. 새 외부 IP 반환."""
    try:
        subprocess.run(["adb", "shell", "svc", "data", "disable"], check=True, timeout=10)
        time.sleep(3)
        subprocess.run(["adb", "shell", "svc", "data", "enable"], check=True, timeout=10)
        time.sleep(8)
        ip = subprocess.check_output(
            ["curl", "-s", "--max-time", "10", "https://api.ipify.org"],
            timeout=12,
        ).decode().strip()
        return ip
    except Exception as e:
        log(f"  ip_rotate_error: {e}")
        return ""


def should_skip(acct: Account) -> str | None:
    """None 반환 시 처리 대상. 문자열 반환 시 skip 이유.

    정책: 잠긴/정지된 계정만 skip. 이미 워밍업/액티브여도 재검증 (idempotent 스킵
    으로 완료된 단계는 내부에서 빨리 지나감, 미비된 단계만 실제 수행).
    """
    if acct.status in ("identity_challenge", "suspended", "retired", "ip_blocked"):
        return f"status={acct.status}"
    return None


async def process_account(acct_id: int) -> dict:
    """한 계정 처리. 결과 dict 반환."""
    result = {"id": acct_id, "status": "pending", "reason": "", "actions": [], "error": ""}

    db = SessionLocal()
    try:
        acct = db.get(Account, acct_id)
        if not acct:
            result["status"] = "not_found"
            return result

        skip_reason = should_skip(acct)
        if skip_reason:
            result["status"] = "skipped"
            result["reason"] = skip_reason
            return result

        profile_id = acct.adspower_profile_id
        if not profile_id:
            result["status"] = "no_profile"
            result["reason"] = "no AdsPower profile"
            return result

        email = acct.gmail
        password = crypto.decrypt(acct.password) if acct.password else None
        recovery = acct.recovery_email
        persona = json.loads(acct.persona) if acct.persona else {}
    finally:
        db.close()

    # IP rotate
    new_ip = rotate_ip()
    log(f"  IP → {new_ip or 'FAILED'}")
    if not new_ip:
        result["status"] = "ip_fail"
        result["error"] = "IP rotation failed"
        return result

    # Open AdsPower
    adsp = AdsPowerClient()
    browser_info = None
    try:
        browser_info = adsp.start_browser(profile_id)
        ws = browser_info.get("ws_endpoint")
        debug_port = browser_info.get("debug_port")
        if not ws:
            result["status"] = "adspower_fail"
            result["error"] = "no ws_endpoint"
            return result
        cdp = f"http://127.0.0.1:{debug_port}"
        log(f"  AdsPower opened profile={profile_id} port={debug_port}")

        # Wait briefly for tabs to settle
        await asyncio.sleep(3)

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp)
            ctx = browser.contexts[0] if browser.contexts else None
            if ctx is None:
                result["status"] = "no_context"
                return result

            # 작업 탭 하나만 남기고 나머지 close — 특히 start.adspower.net 은 정리.
            work_page = None
            for pg in ctx.pages:
                url = pg.url
                if "youtube.com" in url or "google.com" in url:
                    work_page = pg
                    break
            if work_page is None:
                work_page = await ctx.new_page()
                try:
                    await work_page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=30_000)
                except Exception as e:
                    log(f"  initial goto error: {e}")
            for pg in list(ctx.pages):
                if pg is not work_page:
                    try:
                        await pg.close()
                    except Exception:
                        pass
            page = work_page

            # 로그인은 run_onboard_session 내부의 auto_login 에 위임 (이중 로그인 방지).
            # run_onboard_session 은 goto youtube → check_logged_in → (False 면) auto_login
            # → post-login 프롬프트 skip 까지 처리.

            # Run onboard session
            try:
                r = await asyncio.wait_for(
                    run_onboard_session(
                        page, persona=persona, email=email, password=password,
                        recovery_email=recovery,
                        duration_min_sec=75, duration_max_sec=135,
                    ),
                    timeout=PER_ACCOUNT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                result["status"] = "timeout"
                result["error"] = f"onboard timeout > {PER_ACCOUNT_TIMEOUT}s"
                return result
            except Exception as e:
                result["status"] = "onboard_exception"
                result["error"] = str(e)
                return result

            result["actions"] = r.actions
            result["critical_failures"] = r.critical_failures
            result["ok"] = r.ok
            result["error"] = r.error or ""

            # Persist results
            db = SessionLocal()
            try:
                acct = db.get(Account, acct_id)
                if r.otp_secret and not acct.totp_secret:
                    acct.totp_secret = crypto.encrypt(r.otp_secret)

                # identity_challenge:locked → 7일 쿨다운
                if any("identity_challenge:locked" in f for f in r.critical_failures):
                    acct.status = "identity_challenge"
                    acct.identity_challenge_until = datetime.now(UTC) + timedelta(days=7)
                    acct.identity_challenge_count = (acct.identity_challenge_count or 0) + 1
                    result["status"] = "identity_challenge_locked"
                elif r.ok and not r.critical_failures:
                    # 최초 온보딩인 경우에만 warmup 전이 + start_date 셋팅.
                    # 이미 warmup 상태였으면 기존 날짜 유지하고 end_date 만 B=3일 기준으로 동기화.
                    acct.warmup_group = "B"
                    if acct.status != "warmup" or not acct.warmup_start_date:
                        acct.status = "warmup"
                        acct.onboard_completed_at = acct.onboard_completed_at or datetime.now(UTC)
                        acct.warmup_start_date = acct.warmup_start_date or datetime.now(UTC)
                    acct.warmup_end_date = acct.warmup_start_date + timedelta(
                        days=WARMUP_DAYS.get("B", 3)
                    )
                    # 온보딩 직후 = Day 0. 이미 Day > 0 으로 진행중이면 건드리지 않음.
                    if (acct.warmup_day or 0) == 0:
                        acct.warmup_day = 0
                    result["status"] = "onboarded"
                else:
                    result["status"] = "failed"
                    if not result["error"]:
                        result["error"] = f"ok={r.ok} critical={r.critical_failures}"
                db.commit()
            finally:
                db.close()

    finally:
        # 마지막 계정이면 브라우저 유지 (수동 검증용). ACCOUNTS 전역 참조.
        if acct_id != ACCOUNTS[-1]:
            try:
                adsp.stop_browser(profile_id)
            except Exception as e:
                log(f"  stop_browser error: {e}")
        else:
            log(f"  keeping browser open (last account)")

    return result


async def main():
    LOG_PATH.write_text("")  # reset log
    log(f"=== batch onboard start — targets: {ACCOUNTS[0]}..{ACCOUNTS[-1]} ===")

    summary = {"onboarded": 0, "skipped": 0, "failed": 0, "identity_challenge": 0, "login_fail": 0, "other_error": 0}

    for acct_id in ACCOUNTS:
        log(f"")
        log(f"--- account #{acct_id} ---")
        try:
            r = await process_account(acct_id)
        except Exception as e:
            log(f"  FATAL in process_account: {e!r}")
            summary["other_error"] += 1
            continue

        log(f"  result: status={r.get('status')} reason={r.get('reason', '')} actions={r.get('actions', [])[:8]}")
        if r.get("error"):
            log(f"  error: {r['error']}")

        s = r.get("status", "unknown")
        if s == "onboarded":
            summary["onboarded"] += 1
        elif s == "skipped":
            summary["skipped"] += 1
        elif s == "identity_challenge_locked":
            summary["identity_challenge"] += 1
        elif s == "login_fail":
            summary["login_fail"] += 1
        elif s == "failed":
            summary["failed"] += 1
        else:
            summary["other_error"] += 1

        # between accounts — 15s 휴지 (쓰로틀 회피)
        await asyncio.sleep(15)

    log(f"")
    log(f"=== done ===")
    log(f"summary: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
