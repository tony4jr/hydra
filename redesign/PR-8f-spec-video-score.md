# PR-8f — 영상 점수 알고리즘 + 안전필터 + 롱런 분류

**위험**: ★★ (DB 마이그레이션 + 점수 계산 워커)
**예상**: 4h
**의존**: 없음 (독립)

---

## 목표

영상 우선순위 = **100점 점수 + 부스트 + 안전필터**. 운영자 가중치 조절 가능. 롱런 영상 자동 분류.

---

## 점수 (100점)

| 컴포넌트 | 만점 | 계산 |
|---|---|---|
| 최신성 (recency_score) | 40 | 24h 이내 = 40, 1일=30, 3일=20, 1주=10, >1주=0 |
| 조회수 (view_score) | 30 | 1만~100만 → linear 0~30, ≥100만=30 |
| 키워드 일치도 (keyword_score) | 30 | embedding_score (PR-3a 의 niche threshold 와 동일 source) × 30 |
| **합계** | **100** | recency + view + keyword |

운영자 가중치 조절 (관리자 페이지):
```
최신성: 40 → [40] (slider 0~100)
조회수: 30 → [30]
키워드: 30 → [30]
합 = 100 (자동 정규화 또는 합 표시)
```

---

## 부스트 (절대값 +)

| 부스트 | 점수 |
|---|---|
| 즐겨찾기 채널 (FavoriteChannel, PR-8h) | +20 |
| 즐겨찾기 영상 (FavoriteVideo, PR-8h) | +50 |

PR-8h 모델 출시 후 활용. PR-8f 는 schema 만 (boost_favorite_channel, boost_favorite_video 컬럼).

---

## 안전 필터 (절대 제외, total_score = 0 + reason)

| 사유 | 신호 |
|---|---|
| 채널 운영자 댓글 삭제 이력 | CommentSnapshot.is_deleted 누적 (해당 channel_id) |
| 우리 워커 차단 이력 | Account.banned_video_ids 또는 신규 BannedVideoChannel |
| 신고 누적 영상 | 외부 신호 미정 (PR-8f 는 schema 만, 실제 trigger PR-8f-followup) |
| 운영자 보호 표시 | ProtectedVideo (PR-8h) |
| 키워드 매칭도 5점 이하 | embedding_score < 0.05 |

---

## 롱런 영상 자동 분류

조건:
- 일평균 조회수 ≥ 1만 (Video 등록 후 7일 평균)
- 또는 운영자 즐겨찾기 추가

자동 분류 시 `Video.is_longrun = TRUE`. 운영자가 토글 가능.

롱런 영상의 **댓글 비율 한도**:
- 영상 전체 댓글 수의 3% 까지 (max 30 슬롯/캠페인)
- 매주 1개 추가 (자동, PR-8g 워커)
- 작업 기간 6개월

---

## 데이터 모델 (alembic)

### VideoScore 신규 테이블

```python
class VideoScore(Base):
    __tablename__ = "video_scores"

    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"),
                      primary_key=True)
    recency_score = Column(Integer, default=0, nullable=False)
    view_score = Column(Integer, default=0, nullable=False)
    keyword_score = Column(Integer, default=0, nullable=False)
    boost_favorite_channel = Column(Integer, default=0, nullable=False)
    boost_favorite_video = Column(Integer, default=0, nullable=False)
    total_score = Column(Integer, default=0, nullable=False)
    safety_filter_reason = Column(String(60))  # NULL = 통과
    is_longrun = Column(Boolean, default=False, nullable=False)
    calculated_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        Index("ix_video_scores_total", "total_score"),
        Index("ix_video_scores_longrun", "is_longrun"),
    )
```

### Video 테이블 — `is_longrun` 컬럼 추가 (옵션)

```python
op.add_column('videos', sa.Column('is_longrun', sa.Boolean(), default=False))
```

VideoScore.is_longrun 과 중복? — 점수 행이 없는 영상도 있을 수 있음. Video.is_longrun 가 운영자 토글 source-of-truth, VideoScore.is_longrun 는 캐시된 자동 분류.

자율 결정: Video 에만 두고 VideoScore.is_longrun 제거. 단순화.

→ **결정**: VideoScore.is_longrun 제거, `Video.is_longrun` 만 사용.

### 가중치 설정 (system_config)

```sql
INSERT INTO system_config (key, value) VALUES
  ('video_score_weights', '{"recency": 40, "view": 30, "keyword": 30, "boost_channel": 20, "boost_video": 50, "longrun_threshold": 10000}');
```

운영자가 조절 시 `PATCH /api/admin/system/video-score-weights`.

---

## 백엔드

`POST /api/admin/videos/{video_id}/recalc-score` — 단일 재계산
`POST /api/admin/videos/recalc-all` — 전체 (background)
`GET /api/admin/videos/{video_id}/score` — VideoScore 조회

운영 워커 (별도):
- nightly 배치로 모든 active video 점수 재계산
- 신규 발견 영상 즉시 계산

---

## 안전필터 즉시 적용

영상 수집 단계 (smart_video_collector) 에서:
- VideoScore 계산
- safety_filter_reason 가 set 되면 Video.state='blacklisted' + blacklist_reason

---

## 변경 파일

| 파일 | 변경 |
|---|---|
| `alembic/versions/XX_video_score.py` | **신규** — video_scores 테이블 + Video.is_longrun + system_config seed |
| `hydra/db/models.py` | VideoScore 클래스, Video.is_longrun |
| `hydra/services/video_score.py` | **신규** — 점수 계산 로직 |
| `hydra/web/routes/videos.py` | recalc / score endpoints |
| `hydra/web/routes/admin_settings.py` (또는 system) | video-score-weights GET/PATCH |
| `frontend/src/features/settings/video-score.tsx` | **신규** 가중치 조절 페이지 |
| `frontend/src/types/video.ts` | VideoScore 타입 추가 |
| `frontend/src/features/videos/index.tsx` | 검색 결과에 점수 표시 |
| `frontend/src/features/videos/timeline.tsx` | 점수 + safety 사유 표시 |

---

## 격리 dry-run

- accounts 9 row count = 0
- video_scores 테이블 생성 확인
- system_config seed INSERT 확인
- downgrade roundtrip

---

## 자율 결정 영역

- A. 점수 정규화 — 가중치 합이 100 이 아니면 자동 normalize 또는 운영자에게 합 표시 후 책임
- B. nightly 배치 시점 (현재 운영 시간대 회피)
- C. recalc-all 의 백그라운드 실행 (FastAPI BackgroundTasks 또는 별도 워커)
- D. is_longrun 의 자동 vs 수동 우선순위 (자동 분류 후 운영자가 끄면 자동 재분류 주기)

---

## Out of scope

- 실제 운영 워커 통합 (PR-8f 는 모델 + 계산 로직만, 통합은 후속)
- 점수 변화 추적 (versioned VideoScore log) — 별도
- 점수 기반 알림 (PR-8b 알림 시스템 확장)
