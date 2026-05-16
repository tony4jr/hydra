"""Phase 4.1 — worker_errors 묶음 → 한 줄 운영 요약.

Why:
  - 운영자가 100건 worker_errors raw 보기 싫음
  - Haiku 4.5 가성비로 한 문장 요약 (cost <$0.001/호출)
  - admin UI 또는 텔레그램 알림에서 호출

Pattern:
  rows = db.query(WorkerError).filter(...).limit(50).all()
  summary = summarize_errors(rows)  # → "최근 1시간 12건 — login 5건 실패 (POST_PASSWORD_UNKNOWN 3건), AdsPower 7건 crash"
"""
from __future__ import annotations

import json
from typing import Iterable

from hydra.ai.base import get_model
from hydra.ai.harness import call_claude


_SYSTEM = """당신은 자동화 운영팀의 데이터 분석 보조다. worker_error 묶음을 한 문장(최대 2문장)으로 요약한다.

규칙:
- 핵심 패턴 1-3개만 추출. 단순 카운트 + 가장 두드러진 원인 1개.
- 한국어. 운영자가 즉시 의사결정 가능한 형태.
- 추측 금지. 데이터에 없는 원인 추정 금지.
- 모르겠으면 "패턴 불분명, raw 검토 필요"라고 말함.
- JSON 출력 금지. 텍스트만."""


def summarize_errors(
    errors: Iterable[dict],
    *,
    window_hint: str = "",
) -> str:
    """worker_error dict 묶음을 한 줄 요약.

    Args:
        errors: iterable of dicts with keys: kind, message, screen_state,
                failure_taxonomy, captured_url, received_at, worker_id
        window_hint: 시간 범위 힌트 (e.g. "최근 1시간")

    Returns:
        요약 텍스트 (1-2 문장). 호출 실패 시 "(요약 실패: <reason>)" 반환.
    """
    rows = list(errors)
    if not rows:
        return "에러 없음"

    # 카운트는 전체 row 기준 — Codex P2 fix (이전엔 50개로 잘라서 분포가 왜곡).
    # 토큰 절약은 sample_messages 캡으로만 처리.
    by_kind: dict[str, int] = {}
    by_state: dict[str, int] = {}
    by_taxonomy: dict[str, int] = {}
    sample_messages: list[str] = []
    for r in rows:
        k = r.get("kind") or "other"
        by_kind[k] = by_kind.get(k, 0) + 1
        st = r.get("screen_state")
        if st:
            by_state[st] = by_state.get(st, 0) + 1
        tax = r.get("failure_taxonomy")
        if tax:
            by_taxonomy[tax] = by_taxonomy.get(tax, 0) + 1
        m = r.get("message") or ""
        if len(sample_messages) < 5 and m:
            sample_messages.append(m[:200])

    summary_data = {
        "total": len(rows),
        "window": window_hint,
        "by_kind": by_kind,
        "by_screen_state": by_state,
        "by_failure_taxonomy": by_taxonomy,
        "sample_messages": sample_messages,
    }
    user_msg = (
        "다음 worker_error 통계를 한 문장으로 요약:\n\n"
        + json.dumps(summary_data, ensure_ascii=False, indent=2)
    )

    try:
        text = call_claude(
            model=get_model("error_summary"),  # Haiku 4.5
            agent_name="error_summary",
            system=_SYSTEM,
            user_message=user_msg,
            max_tokens=200,
            max_retries=1,
        )
        return text.strip()
    except Exception as e:
        return f"(요약 실패: {type(e).__name__}: {str(e)[:120]})"
