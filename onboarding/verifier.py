"""메인 오케스트레이터 — 각 계정에 대해 goal 순차 실행 + 리포트 생성."""
import asyncio
import random
import json

from hydra.db.models import Account
from hydra.db.session import SessionLocal
from hydra.core.logger import get_logger

from onboarding.goals import ALL_GOALS
from onboarding.report import GoalStatus, Report
from onboarding.session import open_session

log = get_logger("onboarding.verifier")

PHASE_GAP_MIN = 5.0
PHASE_GAP_MAX = 12.0


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

            # Phase gap — 계정당 goal 간 5~12초 대기 (자연스러움 + YT throttle 회피)
            await asyncio.sleep(random.uniform(PHASE_GAP_MIN, PHASE_GAP_MAX))

            # detect
            try:
                state = await goal.detect(page, acct)
            except Exception as e:
                if _connection_error(e):
                    report.error(goal.name, f"detect disconnected: {e}")
                    break
                report.error(goal.name, f"detect: {e}")
                continue

            if state == "done":
                report.skip(goal.name, "already done")
                continue
            if state == "blocked":
                report.skip(goal.name, "precondition")
                continue

            # apply
            try:
                result = await goal.apply(page, acct)
            except Exception as e:
                if _connection_error(e):
                    report.error(goal.name, f"apply disconnected: {e}")
                    break
                report.error(goal.name, f"apply: {e}")
                continue

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
