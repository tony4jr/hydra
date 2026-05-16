"""Phase 2.3 — screen_state-level circuit breaker.

같은 (worker_id, screen_state) 가 짧은 창에서 N회 fail 하면 일시 정지.

Why:
  - Google SRE 의 cascading failure / retry budget 원칙
  - YouTube UI 변경 같은 systemic 문제에서 N계정 무한 실패 폭발 방지
  - Phase 3 admin 에서 사람이 보고 해소할 때까지 자동 차단

In-memory only — 워커 재기동 시 reset. 분산 환경 필요시 추후 Redis.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class ScreenStateCircuitBreaker:
    """동일 screen_state 가 window 내 N회 fail 시 open.

    Args:
        threshold: trip 임계 횟수 (default 5)
        window_sec: 카운트 윈도우 (default 300s = 5min)
        cooldown_sec: open 후 자동 close 까지 (default 600s = 10min)
    """

    def __init__(self, threshold: int = 5, window_sec: float = 300.0, cooldown_sec: float = 600.0):
        self.threshold = threshold
        self.window_sec = window_sec
        self.cooldown_sec = cooldown_sec
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._open_until: dict[str, float] = {}

    def record_failure(self, screen_state: str) -> None:
        """fail 발생 기록. threshold 도달 시 open."""
        now = time.monotonic()
        q = self._failures[screen_state]
        q.append(now)
        # 윈도우 밖 항목 제거
        cutoff = now - self.window_sec
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.threshold:
            self._open_until[screen_state] = now + self.cooldown_sec

    def record_success(self, screen_state: str) -> None:
        """성공 1회로 카운터 reset + open 해제."""
        self._failures.pop(screen_state, None)
        self._open_until.pop(screen_state, None)

    def is_open(self, screen_state: str) -> bool:
        """True 면 caller 는 즉시 fail 처리 (작업 차단)."""
        deadline = self._open_until.get(screen_state)
        if deadline is None:
            return False
        if time.monotonic() >= deadline:
            self._open_until.pop(screen_state, None)
            self._failures.pop(screen_state, None)
            return False
        return True

    def status(self, screen_state: str) -> dict:
        """diagnostic — 현재 카운트/open 상태."""
        now = time.monotonic()
        q = self._failures.get(screen_state, deque())
        deadline = self._open_until.get(screen_state)
        return {
            "screen_state": screen_state,
            "recent_failures": len([t for t in q if t > now - self.window_sec]),
            "is_open": self.is_open(screen_state),
            "open_remaining_sec": (max(0.0, deadline - now) if deadline else 0.0),
        }


# 모듈 레벨 singleton (워커 프로세스 1개 가정).
breaker = ScreenStateCircuitBreaker()
