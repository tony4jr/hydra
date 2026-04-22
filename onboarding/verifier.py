"""메인 오케스트레이터 — 각 계정에 대해 goal 순차 실행 + 리포트 생성."""
import asyncio
import random
import json
from datetime import datetime, UTC

from hydra.db.models import Account
from hydra.db.session import SessionLocal
from hydra.core.logger import get_logger

from onboarding.goals import ALL_GOALS
from onboarding.report import GoalStatus, Report
from onboarding.session import open_session

log = get_logger("onboarding.verifier")


async def _bypass_ipp_if_present(page, acct) -> bool:
    """현재 URL 이 /challenge/ipp/ 면 bypass 실행 + acct.ipp_flagged 세팅.

    Returns True 면 bypass 수행됨.
    """
    if "/signin/challenge/ipp/" not in page.url:
        return False
    if getattr(acct, "ipp_flagged", False):
        return False  # 이미 우회했는데도 또 뜸 — 재우회 안 함 (loop 방지)
    from onboarding.login_fsm import _bypass_ipp, _type_password
    try:
        await _bypass_ipp(page, acct)     # chip → accountchooser → my account → /pwd
        await _type_password(page, acct)  # pwd 재입력
        async with asyncio.timeout(15):
            while "/signin/challenge/" in page.url and "/pwd" in page.url:
                await asyncio.sleep(0.5)
        acct.ipp_flagged = True
        db = SessionLocal()
        try:
            row = db.get(Account, acct.id)
            row.ipp_flagged = True
            tag = f"login_ipp_bypassed @ {datetime.now(UTC).isoformat(timespec='seconds')}"
            row.notes = (row.notes + "\n" + tag) if row.notes else tag
            db.commit()
        finally:
            db.close()
        log.info(f"post-goal ipp bypass OK for #{acct.id} — ipp_flagged=True")
        return True
    except Exception as e:
        log.warning(f"post-goal ipp bypass err for #{acct.id}: {e}")
        return False

PHASE_GAP_MIN = 3.0
PHASE_GAP_MAX = 7.0

# ipp (복구 전화 요구) 우회한 계정에서는 Google 계정 정보 수정 경로가 막힘.
# YouTube 쪽 (video_lang_ko, natural_browsing, channel_profile, avatar) 은 정상.
IPP_BLOCKED_GOALS = {"ui_lang_ko", "display_name", "totp_secret"}


def _connection_error(e: BaseException) -> bool:
    msg = str(e)
    return any(
        s in msg for s in (
            "Connection closed",
            "Target page, context or browser has been closed",
            "browser has been closed",
            "Protocol error",
        )
    )


async def verify_account(account_id: int, *, rotate_ip: bool = True) -> Report:
    """한 계정 온보딩 검증 + 미비 보정. Report 반환."""
    report = Report(account_id=account_id)

    db = SessionLocal()
    try:
        acct = db.get(Account, account_id)
    finally:
        db.close()

    if not acct:
        report.error("session", "account not found")
        return report

    if acct.status in ("identity_challenge", "suspended", "retired"):
        report.skip("session", f"status={acct.status}")
        return report

    if not acct.adspower_profile_id:
        report.error("session", "no adspower_profile_id")
        return report

    try:
        session = await open_session(acct, rotate=rotate_ip)
    except Exception as e:
        report.error("session", f"open: {e}")
        return report

    try:
        page = session.page

        login_ok = True  # login goal 이후 실패하면 다른 goals 의미 없음
        for goal in ALL_GOALS:
            if not login_ok and goal.name != "login":
                report.skip(goal.name, "login prerequisite failed")
                continue

            # 이전 goal 실행 중 ipp interstitial 에 걸렸으면 우회하고 flag 세팅
            await _bypass_ipp_if_present(page, acct)

            # ipp 우회 계정 — Google 계정 설정 수정 경로 차단됨 (워밍업/댓글은 가능)
            if getattr(acct, "ipp_flagged", False) and goal.name in IPP_BLOCKED_GOALS:
                report.skip(goal.name, "ipp_blocked (google account locked)")
                log.info(f"[{goal.name}] skipped — ipp_flagged")
                continue

            # Phase gap — 계정당 goal 간 5~12초 대기 (자연스러움 + YT throttle 회피)
            await asyncio.sleep(random.uniform(PHASE_GAP_MIN, PHASE_GAP_MAX))

            log.info(f"[{goal.name}] detect start — url={page.url[:120]}")

            # detect
            try:
                state = await goal.detect(page, acct)
            except Exception as e:
                log.warning(f"[{goal.name}] detect EXCEPTION at url={page.url[:120]} — {e}")
                if _connection_error(e):
                    report.error(goal.name, f"detect disconnected: {e}")
                    break
                report.error(goal.name, f"detect: {e}")
                continue

            log.info(f"[{goal.name}] detect={state} — url={page.url[:120]}")

            if state == "done":
                report.skip(goal.name, "already done")
                continue
            if state == "blocked":
                report.skip(goal.name, "precondition")
                continue

            log.info(f"[{goal.name}] apply start — url={page.url[:120]}")

            # apply
            try:
                result = await goal.apply(page, acct)
            except Exception as e:
                log.warning(f"[{goal.name}] apply EXCEPTION at url={page.url[:120]} — {e}")
                if _connection_error(e):
                    report.error(goal.name, f"apply disconnected: {e}")
                    break
                report.error(goal.name, f"apply: {e}")
                continue

            log.info(f"[{goal.name}] apply={result} — url={page.url[:120]}")

            # apply 가 끝난 직후 ipp interstitial 걸렸을 수 있음 → 우회 + flag
            await _bypass_ipp_if_present(page, acct)

            report.add(goal.name, GoalStatus(result))

            if goal.name == "login" and result != "done":
                login_ok = False
            if goal.name == "identity_challenge" and result == "blocked":
                # 이후 goals 의미 없음 (locked)
                break
    finally:
        await session.close()

    log.info(f"verify #{account_id} overall_ok={report.overall_ok()} "
             f"entries={json.dumps(report.as_dict()['entries'], ensure_ascii=False)}")
    return report
