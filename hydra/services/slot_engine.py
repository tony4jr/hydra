"""Slot tree → Task 변환 엔진 (Phase B).

PR-8d/8e 의 CommentPreset/CommentTreeSlot 을 실제 실행 가능한 Task 트리로 분해.

규칙:
1. 슬롯의 position 순서대로 Task 생성
2. reply_to_slot_label → parent_task_id 매핑
3. same_account_as_slot_label 지정 시 그 라벨 슬롯과 같은 account 강제 할당
4. 그 외 슬롯은 사용 가능 계정 풀에서 분배 (한 영상당 한 슬롯 1계정 원칙, 재등장 제외)
5. like_min~max 범위로 like_boost 태스크 생성, target_task_id 로 연결
6. scheduled_at: 부모 Task 시간 + 랜덤 지터 (재등장은 더 긴 지터)
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, UTC

from sqlalchemy.orm import Session

from hydra.db.models import (
    Account, Campaign, CommentPreset, CommentTreeSlot, Task,
)


# ─── 시간 분포 (분 단위) ────────────────────────────────────────
DELAY_MAIN_MIN, DELAY_MAIN_MAX = 0, 30        # A 슬롯 (메인 댓글) 시작 지연
DELAY_REPLY_MIN, DELAY_REPLY_MAX = 30, 180    # B/C 답글 (다른 계정)
DELAY_REAPPEAR_MIN, DELAY_REAPPEAR_MAX = 90, 360  # D 재등장 (같은 계정 — 더 길게)
LIKE_BOOST_DELAY_MIN, LIKE_BOOST_DELAY_MAX = 5, 60  # 좋아요 부스트 지연


class SlotEngineError(ValueError):
    """슬롯 → 태스크 변환 중 회복 불가능한 오류."""


def _pick_available_accounts(
    db: Session, *, brand_id: int, exclude_ids: set[int], n: int
) -> list[Account]:
    """캠페인용 사용 가능 계정 N개 선택.

    조건:
    - status='active'
    - identity_challenge_until 미설정이거나 과거
    - exclude_ids 에 없음 (이미 같은 영상에 배정됨)
    - ipp_flagged=False (보호된 계정)
    """
    now = datetime.now(UTC)
    q = (
        db.query(Account)
        .filter(Account.status == "active")
        .filter((Account.identity_challenge_until.is_(None)) |
                (Account.identity_challenge_until < now))
        .filter(Account.ipp_flagged.is_(False))
    )
    if exclude_ids:
        q = q.filter(~Account.id.in_(exclude_ids))
    candidates = q.all()
    if len(candidates) < n:
        raise SlotEngineError(
            f"insufficient active accounts: need {n}, available {len(candidates)}"
        )
    random.shuffle(candidates)
    return candidates[:n]


def _delay_for_slot(
    slot: CommentTreeSlot, is_main: bool, is_reappear: bool
) -> tuple[int, int]:
    if is_main:
        return DELAY_MAIN_MIN, DELAY_MAIN_MAX
    if is_reappear:
        return DELAY_REAPPEAR_MIN, DELAY_REAPPEAR_MAX
    return DELAY_REPLY_MIN, DELAY_REPLY_MAX


def create_campaign_with_slot_tasks(
    db: Session,
    *,
    campaign: Campaign,
    comment_preset: CommentPreset,
    video_id: str,
    base_time: datetime | None = None,
) -> list[Task]:
    """슬롯 트리 기반으로 캠페인 태스크 분해.

    Args:
        db: 세션 (commit 은 호출자 책임).
        campaign: 이미 flush 된 Campaign 인스턴스 (campaign.id 필요).
        comment_preset: 슬롯 로드된 프리셋.
        video_id: 대상 영상 ID.
        base_time: 기준 시각 (None 이면 now).

    Returns:
        생성된 Task 리스트 (comment/reply + like_boost 모두 포함, 순서: 슬롯 position).

    Raises:
        SlotEngineError: 가용 계정 부족, 슬롯 트리 정합성 오류 등.
    """
    if base_time is None:
        base_time = datetime.now(UTC)

    slots = sorted(comment_preset.slots, key=lambda s: s.position)
    if not slots:
        raise SlotEngineError("preset has no slots")

    # 라벨 → 슬롯 매핑 (정합성 체크용)
    slots_by_label: dict[str, CommentTreeSlot] = {s.slot_label: s for s in slots}

    # 정합성 체크: reply_to / same_account_as 가 가리키는 라벨이 모두 존재해야 함
    for s in slots:
        if s.reply_to_slot_label and s.reply_to_slot_label not in slots_by_label:
            raise SlotEngineError(
                f"slot {s.slot_label}: reply_to '{s.reply_to_slot_label}' not found"
            )
        if s.same_account_as_slot_label and s.same_account_as_slot_label not in slots_by_label:
            raise SlotEngineError(
                f"slot {s.slot_label}: same_account_as '{s.same_account_as_slot_label}' not found"
            )
        if s.same_account_as_slot_label == s.slot_label:
            raise SlotEngineError(f"slot {s.slot_label}: cannot reference self")

    # 계정 할당
    # 1) 재등장 슬롯이 아닌 슬롯들에만 새 계정 분배
    fresh_slots = [s for s in slots if not s.same_account_as_slot_label]
    n_fresh = len(fresh_slots)

    used_account_ids: set[int] = set()
    accounts = _pick_available_accounts(
        db, brand_id=campaign.brand_id or 0, exclude_ids=used_account_ids, n=n_fresh
    )
    label_to_account: dict[str, Account] = {}
    for s, acct in zip(fresh_slots, accounts):
        label_to_account[s.slot_label] = acct
        used_account_ids.add(acct.id)

    # 2) 재등장 슬롯은 참조 라벨의 계정 그대로
    for s in slots:
        if s.same_account_as_slot_label:
            label_to_account[s.slot_label] = label_to_account[s.same_account_as_slot_label]

    # Task 생성 (슬롯 순서대로)
    tasks_by_label: dict[str, Task] = {}
    created: list[Task] = []

    for s in slots:
        is_main = s.reply_to_slot_label is None
        is_reappear = s.same_account_as_slot_label is not None

        # scheduled_at 계산
        if is_main:
            base = base_time
            lo, hi = _delay_for_slot(s, is_main=True, is_reappear=False)
        else:
            parent_task = tasks_by_label[s.reply_to_slot_label]
            base = parent_task.scheduled_at
            lo, hi = _delay_for_slot(s, is_main=False, is_reappear=is_reappear)
        delay_min = random.uniform(lo, hi)
        scheduled_at = base + timedelta(minutes=delay_min)

        acct = label_to_account[s.slot_label]
        parent = tasks_by_label.get(s.reply_to_slot_label) if s.reply_to_slot_label else None

        task_type = "comment" if is_main else "reply"
        task = Task(
            campaign_id=campaign.id,
            account_id=acct.id,
            task_type=task_type,
            priority="normal",
            status="pending",
            payload=json.dumps({
                "video_id": video_id,
                "preset_id": comment_preset.id,
                "slot_label": s.slot_label,
                "reply_to_slot_label": s.reply_to_slot_label,
                "is_reappear": is_reappear,
                "ai_pending": True,  # Phase C 에서 텍스트 채울 때 신호
            }, ensure_ascii=False),
            scheduled_at=scheduled_at,
            slot_id=s.id,
            slot_label=s.slot_label,
            parent_task_id=parent.id if parent else None,
        )
        db.add(task)
        db.flush()  # task.id 필요 (자식이 parent_task_id 참조)
        tasks_by_label[s.slot_label] = task
        created.append(task)

        # like_boost 태스크
        like_n = random.randint(s.like_min, s.like_max) if s.like_max > 0 else 0
        if like_n > 0:
            # like_boost 는 댓글 작성된 후에 → comment.scheduled_at + LIKE_BOOST_DELAY
            # 다른 계정들이 시간차로 누름. 분배는 워커 측 fetch 시점 + ProfileLock 으로 자연 분산.
            for i in range(like_n):
                lb_delay = random.uniform(LIKE_BOOST_DELAY_MIN, LIKE_BOOST_DELAY_MAX)
                lb_jitter = random.uniform(0.5, 3.0) * i  # 시간차 누적
                lb_task = Task(
                    campaign_id=campaign.id,
                    task_type="like_boost",
                    priority="low",
                    status="pending",
                    payload=json.dumps({
                        "video_id": video_id,
                        "target_task_id": task.id,
                        "target_slot_label": s.slot_label,
                        "preset_id": comment_preset.id,
                    }, ensure_ascii=False),
                    scheduled_at=scheduled_at + timedelta(minutes=lb_delay + lb_jitter),
                    parent_task_id=task.id,
                )
                db.add(lb_task)
                created.append(lb_task)

    return created
