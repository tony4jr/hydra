"""온보딩 재설계 — state-machine login + goal-based idempotent verifier."""

from onboarding.report import GoalStatus, Report
from onboarding.verifier import verify_account

__all__ = ["GoalStatus", "Report", "verify_account"]
