"""Phase 1 — 실패 분류 체계.

기존 worker_errors.kind 는 자유 문자열이라 운영 분석 어려움.
이 enum 으로 실패를 7 카테고리로 정규화 → 종류별 retry/escalation 정책 가능.

Why:
  - selector_missing: UI 변경. → selector_registry 업데이트
  - page_variant: 동일 의도 다른 화면. → 새 screen_state 추가
  - auth_challenge: 2FA/captcha/보안. → manual review queue
  - rate_limit: HTTP 429 / soft block. → cooldown + IP 회전
  - browser_crash: AdsPower/Chrome 죽음. → profile 재시작
  - unknown_outcome: 액션은 했으나 결과 모름. → 조사
  - policy_block: shadow ban / 정책 차단. → 비즈니스 리스크 시그널

How to apply:
  capture_unknown_screen(page, screen_state="...", taxonomy=FailureTaxonomy.PAGE_VARIANT, ...)
"""
from __future__ import annotations

from enum import StrEnum


class FailureTaxonomy(StrEnum):
    SELECTOR_MISSING = "selector_missing"
    PAGE_VARIANT = "page_variant"
    AUTH_CHALLENGE = "auth_challenge"
    RATE_LIMIT = "rate_limit"
    BROWSER_CRASH = "browser_crash"
    UNKNOWN_OUTCOME = "unknown_outcome"
    POLICY_BLOCK = "policy_block"
