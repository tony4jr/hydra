# PR-8g — 댓글 추적 + 영상당 한도

**위험**: ★★★ (큰 백엔드 + Playwright 워커 + DB)
**예상**: 6h
**의존**: PR-8e (CommentTreeSlot, slot_id FK), PR-8f (점수, 한도 자동 조절)

---

## 목표

운영의 핵심: **우리가 깐 댓글이 살아남았나?** + **영상당 / 채널당 / 워커당 안전 한도**.

영상 단위 진입 = 한 영상에 여러 댓글 (효율 2~3배).

---

## CommentExecution 모델 (alembic)

실제 작성된 댓글 1건의 추적 단위.

```python
class CommentExecution(Base):
    __tablename__ = "comment_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"),
                      nullable=False)
    slot_id = Column(Integer, ForeignKey("comment_tree_slots.id", ondelete="SET NULL"))
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"))
    worker_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)  # 작성한 워커

    # 작성 결과
    text = Column(Text, nullable=False)  # 실제 작성된 댓글
    posted_at = Column(DateTime, nullable=False)
    youtube_comment_id = Column(String)  # YT 댓글 ID

    # 추적
    status = Column(String(20), default="alive", nullable=False)
    # alive / deleted / unknown / banned
    likes_count = Column(Integer, default=0, nullable=False)
    last_checked_at = Column(DateTime)
    next_check_at = Column(DateTime)  # 다음 추적 예정 시점
    tracking_status = Column(String(20), default="active", nullable=False)
    # active / paused / ended
    tracking_phase = Column(String(20), default="hour")
    # hour (0~24h) / day (1~7d) / week (7~30d) / ended

    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        Index("ix_executions_video", "video_id"),
        Index("ix_executions_worker", "worker_id"),
        Index("ix_executions_next_check", "next_check_at"),
        Index("ix_executions_status", "status", "tracking_status"),
    )
```

---

## 적응형 추적 주기

| Phase | 기간 | 주기 | 횟수 |
|---|---|---|---|
| hour | 0~24h | 6시간마다 | 4회 |
| day | 1~7일 | 1일 1회 | 6회 |
| week | 7~30일 | 7일 1회 (화력 받은 댓글만) | 3회 |
| ended | 30일+ | 추적 종료 | - |

"화력 받은 댓글" = likes_count ≥ N (운영자 임계값, default 10).

추적 워커 (별도 워커):
- 매 분 `next_check_at <= now AND tracking_status = 'active'` 쿼리
- Playwright 로 YT 영상 페이지 열고 youtube_comment_id 검색
- 결과 (alive/deleted, likes_count) 업데이트
- next_check_at 다음 phase 기준으로 갱신

---

## 영상당 한도 (baseline + 자동 조절)

| 영상 크기 | 댓글 한도 | 간격 |
|---|---|---|
| 큰 (조회 100만+) | 4~5개 | 30~60분 |
| 중간 | 3개 | 1~2시간 (baseline) |
| 작은 (1만 이하) | 1개 | - |

PR-8f 의 `Video.view_count` 또는 `VideoScore.view_score` 로 분류.

### 절대 안전 한도 (운영 안전)

- 첫 댓글 후 5분 안에 두 번째 X
- 같은 영상 24h 4개+ X (하드 한도)
- 같은 워커 같은 영상 재방문 X (예외: 슬롯 재등장 ↻ — 같은 워커가 자기 댓글에 답글, 시간 간격 ≥ 30분)
- 채널당 일 5 영상 X
- 영상 댓글 5% 초과 X (영상의 전체 댓글 대비)

---

## 한도 체크 (캠페인 시작 시)

```python
def can_post_comment(db, video_id, worker_id, campaign_id) -> tuple[bool, str | None]:
    """캠페인 시작 전 한도 검증."""
    video = db.get(Video, video_id)
    # 1. 영상 크기별 한도
    size = classify_video(video)  # large / medium / small
    limit = LIMIT_BY_SIZE[size]
    posted_24h = count_recent_executions(db, video_id, hours=24)
    if posted_24h >= limit:
        return False, f"video_24h_limit:{posted_24h}/{limit}"

    # 2. 5분 간격
    last = last_execution(db, video_id)
    if last and (now - last.posted_at) < timedelta(minutes=5):
        return False, "too_soon_after_last"

    # 3. 워커 재방문
    same_worker = db.query(CommentExecution).filter(
        CommentExecution.video_id == video_id,
        CommentExecution.worker_id == worker_id,
    ).first()
    if same_worker:
        # 슬롯 재등장 (답글) 이면 OK, 30분 간격 필요
        if (now - same_worker.posted_at) < timedelta(minutes=30):
            return False, "same_worker_too_soon"

    # 4. 채널 일 5영상
    today_channel_count = count_distinct_videos_today(db, worker_id, video.channel_id)
    if today_channel_count >= 5:
        return False, "channel_daily_limit"

    # 5. 영상 댓글 5%
    if video.comment_count and posted_24h >= video.comment_count * 0.05:
        return False, "video_5pct_limit"

    return True, None
```

---

## 한도 설정 페이지

`/settings/limits`:
- 영상 크기별 한도 (slider)
- 5분 간격 (조절 X, 안전 한도)
- 채널당 일 한도
- 영상 댓글 % 한도

system_config 에 저장.

---

## 워커 풀 정책

**워커 풀 = 전역 + 범용** (모든 브랜드 / 캠페인 공유).

기존 codebase 의 `accounts` (=워커) 가 이미 전역. PR-8g 는 정책 변경 없음 — 단순 활용.

---

## 백엔드

`GET /api/admin/executions?video_id=&campaign_id=&status=&page=`
`GET /api/admin/executions/{id}` — 단일 추적 상세
`POST /api/admin/executions/{id}/refresh` — 즉시 재추적 (수동)
`GET /api/admin/limits` — 현재 한도 설정
`PATCH /api/admin/limits` — 한도 수정

추적 워커 endpoint (워커 토큰 인증):
`GET /api/worker/tracking/next` — 다음 추적 대상 list
`POST /api/worker/tracking/{exec_id}/result` — 추적 결과 보고

---

## 변경 파일

| 파일 | 변경 |
|---|---|
| `alembic/versions/XX_comment_executions.py` | **신규** — comment_executions 테이블 + 한도 system_config |
| `hydra/db/models.py` | CommentExecution 클래스 |
| `hydra/services/limits.py` | **신규** — can_post_comment + 한도 검증 |
| `hydra/services/tracking.py` | **신규** — phase 진행 + next_check_at 계산 |
| `hydra/web/routes/admin_executions.py` | **신규** |
| `hydra/web/routes/admin_limits.py` | **신규** |
| `hydra/web/routes/worker_tracking.py` | **신규** (워커 토큰) |
| `frontend/src/features/settings/limits.tsx` | **신규** 한도 설정 페이지 |
| `frontend/src/features/videos/timeline.tsx` | CommentExecution 추적 표시 추가 |
| `frontend/src/types/execution.ts` | **신규** |
| 워커 스크립트 (외부) | 추적 Playwright 로직 — PR-8g 의 백엔드만 본 PR, 워커 스크립트는 후속 |

---

## 격리 dry-run

- accounts 9 row count = 0
- comment_executions 테이블 생성
- system_config 한도 seed INSERT
- downgrade roundtrip

---

## 자율 결정 영역

- A. tracking_phase 자동 전환 (cron 또는 매 추적마다 결정)
- B. "화력 받은" 임계값 default (10 likes — 조정 가능)
- C. 영상 크기 분류 경계 (현재: 큰=100만+, 작은=1만 이하, 중간=그 사이)
- D. 5분/30분 등 hard 안전 한도 — system_config 에서 조절 가능 vs 코드 hardcoded
- E. 워커 추적 batch size (한 번에 몇 건씩)

---

## Out of scope

- 실제 워커 스크립트 (Playwright) — 별도 PR (워커 코드는 별도 repo 또는 deployment)
- 추적 결과 알림 (PR-8b 알림 시스템 확장)
- 자동 응대 댓글 (살아남은 댓글에 추가 댓글 깔기 — 별도)
