"""HYDRA entry point.

Usage:
    python -m hydra web              — Start web dashboard (port 8000)
    python -m hydra scheduler        — Start scheduler (campaign steps + like boosts)
    python -m hydra run              — Run sessions for all active accounts
    python -m hydra collect          — Run video collection once (--core for high priority only)
    python -m hydra init-db          — Initialize database tables
    python -m hydra setup <gmail>    — Setup single account (login + profile)
    python -m hydra import <csv>     — Import accounts from CSV file
    python -m hydra warmup           — Run warmup sessions for warmup accounts
    python -m hydra report           — Send daily report now
"""

import sys
import asyncio


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init-db":
        from hydra.db.session import init_db
        init_db()
        print("Database initialized (15 tables).")

    elif cmd == "web":
        from hydra.web.app import run
        run()

    elif cmd == "scheduler":
        from hydra.core.scheduler import run_scheduler, set_device
        device = sys.argv[2] if len(sys.argv) > 2 else None
        if device:
            set_device(device)
            print(f"Device set: {device}")
        asyncio.run(run_scheduler())

    elif cmd == "run":
        from hydra.core.session_runner import run_all_sessions
        device = sys.argv[2] if len(sys.argv) > 2 else None
        asyncio.run(run_all_sessions(device_id=device))

    elif cmd == "collect":
        from hydra.db.session import SessionLocal
        from hydra.collection.youtube_api import collect_all
        db = SessionLocal()
        try:
            core_only = "--core" in sys.argv
            n = collect_all(db, core_only=core_only)
            print(f"Collected {n} new videos.")
        finally:
            db.close()

    elif cmd == "setup":
        if len(sys.argv) < 3:
            print("Usage: python -m hydra setup <gmail>")
            sys.exit(1)
        gmail = sys.argv[2]
        from hydra.db.session import SessionLocal
        from hydra.db.models import Account
        from hydra.accounts.setup import full_setup
        db = SessionLocal()
        account = db.query(Account).filter(Account.gmail == gmail).first()
        if not account:
            print(f"Account not found: {gmail}")
            sys.exit(1)
        asyncio.run(full_setup(db, account))
        db.close()

    elif cmd == "import":
        if len(sys.argv) < 3:
            print("Usage: python -m hydra import <csv_path>")
            sys.exit(1)
        csv_path = sys.argv[2]
        from hydra.db.session import SessionLocal
        from hydra.accounts.manager import import_from_csv
        db = SessionLocal()
        count = import_from_csv(db, csv_path)
        print(f"Imported {count} accounts.")
        db.close()

    elif cmd == "warmup":
        # 모든 WARMUP 상태 계정에 warmup 태스크 큐잉 (Worker 가 pull 해서 실행).
        from hydra.db.session import SessionLocal
        from hydra.db.models import Account
        from hydra.api.tasks import enqueue_warmup_task
        db = SessionLocal()
        try:
            warmups = db.query(Account).filter(Account.status == "warmup").all()
            queued = 0
            for acct in warmups:
                if enqueue_warmup_task(db, acct):
                    queued += 1
            print(f"Enqueued {queued} warmup tasks (scanned {len(warmups)} accounts)")
        finally:
            db.close()

    elif cmd == "report":
        from hydra.infra.daily_report import send_daily_report
        send_daily_report()
        print("Daily report sent.")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
