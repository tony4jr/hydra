"""PR-E: phase 별 timeout + retry policy.

코드 상수 + env override.

설계:
- 각 phase 마다 timeout 초 (default).
- 각 phase 마다 timeout 시 처리 정책: "reschedule" (워커/환경 책임), "fail" (task 자체 문제),
  또는 "unknown_outcome" (submit 직후 등 — 보수적으로 reschedule).
- env override: HYDRA_PHASE_TIMEOUT_<PHASE>=초, HYDRA_PHASE_POLICY_<PHASE>=reschedule|fail|unknown.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

PolicyType = Literal["reschedule", "fail", "unknown"]


@dataclass(frozen=True)
class PhaseSpec:
    timeout_sec: int
    policy: PolicyType


# Codex 권장 반영 — adspower_open 90s, video_goto 60s 등 첫 smoke 여유.
DEFAULT_PHASES: dict[str, PhaseSpec] = {
    "session_start":  PhaseSpec(30,  "reschedule"),
    "ip_rotate":      PhaseSpec(45,  "reschedule"),   # mobile data toggle 여유
    "adspower_open":  PhaseSpec(90,  "reschedule"),   # 첫 실행 시 프로파일 로딩 길 수 있음
    "cdp_connect":    PhaseSpec(30,  "reschedule"),
    "video_goto":     PhaseSpec(60,  "reschedule"),   # YouTube 로딩 여유
    "compose":        PhaseSpec(180, "unknown"),      # AI gen + 타이핑 — submit 직전이라 보수적
    "type":           PhaseSpec(120, "unknown"),
    "submit":         PhaseSpec(30,  "unknown"),      # 제출 직후 — 성공/실패 모호
    "wait":           PhaseSpec(600, "reschedule"),   # 자연 대기 — 길게 OK
    "session_end":    PhaseSpec(15,  "reschedule"),
}


def get_phase_spec(phase: str) -> PhaseSpec:
    """phase 이름에 해당하는 spec — env override 적용.

    env 변수:
      HYDRA_PHASE_TIMEOUT_IP_ROTATE=60
      HYDRA_PHASE_POLICY_SUBMIT=fail
    """
    spec = DEFAULT_PHASES.get(phase)
    if spec is None:
        # 알 수 없는 phase — 안전한 기본값 (60s reschedule).
        spec = PhaseSpec(60, "reschedule")

    env_key = phase.upper()
    t_override = os.getenv(f"HYDRA_PHASE_TIMEOUT_{env_key}")
    p_override = os.getenv(f"HYDRA_PHASE_POLICY_{env_key}")
    if t_override or p_override:
        timeout = spec.timeout_sec
        policy = spec.policy
        if t_override:
            try:
                timeout = int(t_override)
            except ValueError:
                pass
        if p_override and p_override in ("reschedule", "fail", "unknown"):
            policy = p_override  # type: ignore[assignment]
        return PhaseSpec(timeout, policy)
    return spec


class PhaseTimeout(Exception):
    """PR-E: phase 별 timeout 발생 시 raise.

    Attributes:
        phase: 어느 phase 에서 발생했나
        elapsed_sec: 실제 경과 시간 (asyncio.wait_for timeout 직전까지)
        threshold_sec: 설정된 timeout
        policy: timeout 처리 정책 (reschedule/fail/unknown)
    """

    def __init__(self, phase: str, elapsed_sec: float, threshold_sec: int, policy: PolicyType):
        self.phase = phase
        self.elapsed_sec = elapsed_sec
        self.threshold_sec = threshold_sec
        self.policy = policy
        super().__init__(
            f"phase={phase} timeout (elapsed≈{elapsed_sec:.1f}s, threshold={threshold_sec}s, policy={policy})"
        )

    def to_error_message(self) -> str:
        """worker_error.message + task.error_message 에 들어갈 짧은 문자열."""
        return f"phase_timeout phase={self.phase} elapsed={int(self.elapsed_sec)}s threshold={self.threshold_sec}s"
