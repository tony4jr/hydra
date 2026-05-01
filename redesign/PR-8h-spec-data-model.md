# PR-8h — 영상 즐겨찾기 + 보호 + 데이터 모델 종합

**위험**: ★ (DB 마이그레이션, 작은 schema 만)
**예상**: 2h
**의존**: PR-8f (점수 부스트 활용)

---

## 목표

운영자 즐겨찾기 (채널 / 영상) 와 보호 표시 모델 신설. PR-8f 의 boost 점수와 결합. PR-8 데이터 모델 종합 정리.

---

## 모델 (alembic)

### FavoriteChannel

```python
class FavoriteChannel(Base):
    __tablename__ = "favorite_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"),
                      nullable=False)
    channel_id = Column(String, nullable=False)  # YT channel id
    channel_title = Column(String)  # 표시용
    note = Column(Text)  # 운영자 메모 (왜 즐겨찾기?)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        UniqueConstraint("brand_id", "channel_id", name="uq_fav_channel"),
        Index("ix_fav_channel_brand", "brand_id"),
    )
```

### FavoriteVideo

```python
class FavoriteVideo(Base):
    __tablename__ = "favorite_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"),
                      nullable=False)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"),
                      nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        UniqueConstraint("brand_id", "video_id", name="uq_fav_video"),
        Index("ix_fav_video_brand", "brand_id"),
    )
```

### ProtectedVideo

```python
class ProtectedVideo(Base):
    __tablename__ = "protected_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"),
                      nullable=False)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"),
                      nullable=False)
    reason = Column(Text)  # 보호 사유 (예: "고객 직접 게시한 영상")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        UniqueConstraint("brand_id", "video_id", name="uq_protected_video"),
        Index("ix_protected_brand", "brand_id"),
    )
```

ProtectedVideo 가 set 되면 PR-8f 안전필터에서 자동 제외.

---

## 영상 디테일 액션 버튼

`/videos/$videoId` 페이지 (PR-5a 의 timeline) 에 액션 버튼 추가:

```
┌─ 영상 헤더 ──────────────────────────┐
│ "탈모 30대 자가진단"                  │
│ @건강채널 · 1.2M회                   │
│                                      │
│ [⭐ 즐겨찾기 추가] [🚫 보호] [📁 채널 즐겨찾기] │
└──────────────────────────────────────┘
```

토글 동작:
- 즐겨찾기 추가 ↔ 즐겨찾기 해제
- 보호 ↔ 보호 해제
- 채널 즐겨찾기 ↔ 채널 즐겨찾기 해제

---

## 백엔드

`POST /api/admin/favorites/channels?brand_id=&channel_id=` — 추가 (idempotent)
`DELETE /api/admin/favorites/channels/{id}`
`GET /api/admin/favorites/channels?brand_id=`

`POST /api/admin/favorites/videos?brand_id=&video_id=` — 추가
`DELETE /api/admin/favorites/videos/{id}`
`GET /api/admin/favorites/videos?brand_id=`

`POST /api/admin/protected-videos?brand_id=&video_id=&reason=` — 추가
`DELETE /api/admin/protected-videos/{id}`
`GET /api/admin/protected-videos?brand_id=`

---

## 변경 파일

| 파일 | 변경 |
|---|---|
| `alembic/versions/XX_favorites_protection.py` | **신규** — 3 테이블 |
| `hydra/db/models.py` | FavoriteChannel, FavoriteVideo, ProtectedVideo |
| `hydra/web/routes/favorites.py` | **신규** |
| `hydra/web/app.py` | router |
| `hydra/services/video_score.py` (PR-8f) | boost / safety 통합 |
| `frontend/src/features/videos/timeline.tsx` | 액션 버튼 |
| `frontend/src/hooks/use-favorites.ts` | **신규** |

---

## PR-8 데이터 모델 종합 (cross-PR 요약)

| PR | 신규 테이블 | 컬럼 추가 | 주요 의도 |
|---|---|---|---|
| 8a | - | - | UI 만 |
| 8b | - | - | UI + 기존 데이터 derived |
| 8c | - | brands +7 | 브랜드 톤·금지어 |
| 8d | presets / comment_tree_slots | niches +1 (preset_id) | 전역 프리셋 |
| 8e | - | - | UI + 8d 모델 활용 |
| 8f | video_scores | videos +1 (is_longrun) | 영상 점수 |
| 8g | comment_executions | - | 추적 + 한도 |
| 8h | favorite_channels / favorite_videos / protected_videos | - | 운영자 표시 |

총 **6 신규 테이블** + brands +7 컬럼 + niches +1 + videos +1.

⚠️ accounts 9 테이블 = ALTER 0 (절대 원칙, 모든 PR-8 sub-PR).

---

## "Niche → Target" 표시 변경 (cross-PR)

DB 컬럼 / 모델 / API rename 모두 **X**. UI 표시만:
- PR-8a: i18n-terms.ts `niche: '시장' → '타겟'`
- PR-8a: 사이드바 항목명, 페이지 헤더 모두 "타겟"
- PR-8c: /products/$brandId/niches/$nicheId 의 헤더 "타겟"
- PR-8c: /products → /targets 라우트 alias 추가? (자율 결정, 기본은 /products 유지)

PR-8h 는 이 cross-PR 결정의 종합 정리. 실제 작업은 각 sub-PR 안.

---

## 격리 dry-run

- accounts 9 row count = 0
- 3 테이블 생성 확인
- downgrade roundtrip

---

## Out of scope

- 즐겨찾기 alert (PR-8b 알림 확장)
- 보호 영상 자동 인식 (현재는 수동)
- 채널 즐겨찾기 시 채널의 모든 영상 자동 점수 부스트 (PR-8f 점수 계산 로직에서 처리)
- import/export favorites (별도)

---

## 자율 결정 영역

- A. note 필드 max length (현재 Text — 무제한)
- B. brand_id 가 NULL 인 전역 즐겨찾기 (현재: NOT NULL — 브랜드 단위만)
- C. ProtectedVideo 의 expiration (현재 영구)
- D. /products → /targets alias (운영자 사이드바 항목 따로 추가, 라우트 그대로)
