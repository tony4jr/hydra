"""실행 결과 집약 — 각 goal 단위 status + reason 기록."""
from dataclasses import dataclass, field
from enum import StrEnum


class GoalStatus(StrEnum):
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
    ERROR = "error"  # detect/apply 내 예외
    BLOCKED = "blocked"  # 전이 조건 미충족 (예: identity_challenge locked)


# required=True 인 goal 들 — 실패 시 전체 실패로 간주
REQUIRED_GOALS = frozenset([
    "login",
    "ui_lang_ko",
    "display_name",
    "identity_challenge",
    "channel_profile",  # name + handle 통합
])


@dataclass
class Report:
    account_id: int
    entries: list[dict] = field(default_factory=list)

    def add(self, goal: str, status: GoalStatus, *, reason: str | None = None) -> None:
        self.entries.append({"goal": goal, "status": status.value, "reason": reason})

    def skip(self, goal: str, reason: str = ""):
        self.add(goal, GoalStatus.SKIPPED, reason=reason or None)

    def error(self, goal: str, reason: str):
        self.add(goal, GoalStatus.ERROR, reason=reason)

    def as_dict(self) -> dict:
        return {"account_id": self.account_id, "entries": self.entries}

    def overall_ok(self) -> bool:
        """필수 goal 이 모두 done/skipped 이면 True."""
        good = {GoalStatus.DONE.value, GoalStatus.SKIPPED.value}
        done = {e["goal"] for e in self.entries if e["status"] in good}
        return REQUIRED_GOALS.issubset(done)
