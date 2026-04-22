#!/usr/bin/env python3
"""#29 로그인 시도 후 /challenge/dp 에서 브라우저 멈춰두고 수동 확인."""
import asyncio, sys
sys.path.insert(0, ".")

from hydra.db.session import SessionLocal
from hydra.db.models import Account
from onboarding.session import open_session
from onboarding.login_fsm import run_login_fsm


async def main(aid: int):
    db = SessionLocal()
    acct = db.get(Account, aid)
    db.close()
    if not acct:
        print(f"no account {aid}"); return

    sess = await open_session(acct, rotate=True)
    try:
        print(f"\n→ login FSM start (profile={sess.profile_id})")
        status, url = await run_login_fsm(sess.page, acct)
        print(f"\n=== FSM {status} @ {url}")
        print("브라우저 유지 중. 확인 후 Ctrl+C 로 종료.")
        while True:
            await asyncio.sleep(10)
            try:
                cur = sess.page.url
                print(f"  [현재 URL] {cur[:100]}")
            except Exception:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print("\n닫는 중...")
        await sess.close()


if __name__ == "__main__":
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 29
    asyncio.run(main(aid))
