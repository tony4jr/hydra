"""홈 대시보드 파이프라인 흐름 endpoint.

PR-2b-1.

GET /api/admin/pipeline/flow — 5단계 깔때기 카운트 + 병목 감지.
30s 캐시 (dashboard_metrics 내부).

설계:
- _ADMIN_DEPS 적용 (legacy dashboard.py 와 달리 인증 강제)
- module-level sync 라우트 (codebase 패턴)
- response_model 명시 (타입 안전 + OpenAPI 자동)
- niche_id 파라미터 X (PR-3 에서 추가)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.services.dashboard_metrics import (
    PipelineFlowResponse,
    get_pipeline_flow,
)

router = APIRouter()


@router.get(
    "/api/admin/pipeline/flow",
    response_model=PipelineFlowResponse,
)
def read_pipeline_flow(
    window_hours: int = Query(24, ge=1, le=168),  # 1h ~ 7d
    db: Session = Depends(get_db),
) -> PipelineFlowResponse:
    """파이프라인 흐름 집계 — 5단계 카운트 + 병목.

    Query params:
        window_hours: 집계 윈도우 (1, 6, 12, 24 권장. 최대 168=7d).

    Returns:
        PipelineFlowResponse — 5 stages, pass_rate, bottleneck_message.
    """
    return get_pipeline_flow(db, window_hours=window_hours)
