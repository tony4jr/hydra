"""Niche fallback helper — PR-3b.

서비스 코드가 Brand id (legacy: target_id) 로부터 default Niche 를 조회하기 위한 헬퍼.
Niche 없으면 None — 호출자는 Brand/TargetCollectionConfig fallback 처리.

PR-3a 백필 후엔 모든 brand 에 default Niche 1:1 존재. fallback 은 안전망.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from hydra.db.models import Niche


def get_niche_for_target(db: Session, target_id: int) -> Optional[Niche]:
    """Brand id 로부터 default Niche 조회 (state != 'archived', id 오름차순 첫 번째)."""
    return (
        db.query(Niche)
        .filter(Niche.brand_id == target_id, Niche.state != "archived")
        .order_by(Niche.id.asc())
        .first()
    )
