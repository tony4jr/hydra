"""Assign Claude-generated personas to all accounts without persona.

Claims one PersonaSlot per account, calls Claude, saves to account.persona.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.ai.agents.persona_agent import assign_persona


def main():
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(Account.persona.is_(None)).order_by(Account.id).all()
        print(f"Accounts without persona: {len(accounts)}")
        ok = fail = 0
        for a in accounts:
            try:
                assign_persona(db, a)
                ok += 1
                print(f"  [{ok}/{len(accounts)}] {a.gmail} done")
                time.sleep(0.5)  # gentle rate limit
            except Exception as e:
                fail += 1
                print(f"  FAIL {a.gmail}: {e}")
        print(f"\nDone: ok={ok} fail={fail}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
