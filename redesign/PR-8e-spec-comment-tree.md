# PR-8e — 댓글 트리 편집 UI (가장 큰 PR)

**위험**: ★★★ (UI 복잡 + 슬롯 CRUD 백엔드)
**예상**: 8h
**의존**: PR-8d (Preset / CommentTreeSlot 모델)

---

## 목표

프리셋 = 댓글 트리. 트리 = 슬롯 (워커 단위) 의 부모-자식 관계. PR-8e 는 **편집 UI** 와 **미리보기** 모드.

---

## 핵심 개념: 슬롯

- **슬롯 = 워커 1명** (한 프리셋 안에서 같은 워커가 여러 번 등장 가능)
- 슬롯 라벨은 **자동 부여** (A, B, C, D, ...) — 새 슬롯 추가 시 다음 알파벳
- **재등장 ↻ 표시**: 같은 워커 (= 같은 slot_label) 가 다른 위치에 또 나타나면 시각 명확
  - 예: A=메인 댓글, B=A 에 답글, **A**↻ = B 에 또 답글 (같은 워커)

---

## 편집 UI (Preset 디테일 페이지)

```
┌─ /presets/$id ────────────────────────────────────┐
│  후기형 [편집] [복제] [삭제]                          │
│                                                  │
│  [✏ 편집 모드] [👁 미리보기]                      │
│                                                  │
│  [+ 슬롯 추가]                                    │
│                                                  │
│  ┌─ A (메인 댓글) ─────────────────────┐          │
│  │ 양식: [_________________________]  │          │
│  │ 길이: ◉짧게 ○보통 ○길게            │          │
│  │ 이모지: ○없음 ◉가끔 ○자주          │          │
│  │ AI 변형: ━━━●━━ 50%                │          │
│  │ 좋아요: 5~20  방식: [적응형 ▾]      │          │
│  │ [답글 추가] [삭제]                  │          │
│  └────────────────────────────────────┘          │
│                                                  │
│  ┌─ B (A 에 답글) ────────────────────┐          │
│  │ ... 동일 컨트롤                     │          │
│  └────────────────────────────────────┘          │
│                                                  │
│  ┌─ A↻ (B 에 답글, 재등장) ────────────┐          │
│  │ ... 동일 컨트롤                     │          │
│  └────────────────────────────────────┘          │
└──────────────────────────────────────────────────┘
```

### 슬롯별 컨트롤

| 컨트롤 | 타입 | 값 |
|---|---|---|
| 양식 | textarea | 자유 텍스트 (placeholder, ai_variation 으로 변형) |
| 길이 | radio | short / medium / long |
| 이모지 | radio | none / sometimes / often |
| AI 변형 | slider | 0~100% (0=양식 그대로, 100=완전 재작성) |
| 좋아요 범위 | min/max input | 0~999 |
| 좋아요 방식 | select | adaptive / burst / spread / slow |

### 답글 대상 드롭다운

새 슬롯 추가 시:
- "메인 댓글로" → reply_to_slot_label = NULL
- "A 에 답글로" → reply_to_slot_label = 'A'
- "B 에 답글로" → 'B'
- ...

기존 슬롯 라벨 list 에서 선택. 자기 자신 답글 X (UI 차단).

### 재등장 ↻ 표시

같은 slot_label 이 트리 안에 2번 이상 나타나면:
- 첫 번째: `A`
- 두 번째: `A↻`
- 세 번째: `A↻↻`

같은 워커가 여러 위치에서 댓글 — 자연 토론처럼 보임.

운영자는 **새 슬롯 추가 시 라벨 선택 가능**:
- 새 워커 (다음 알파벳) 또는
- 기존 워커 재사용 (드롭다운에서 선택)

### 편집 모드 ↔ 미리보기 모드 토글

미리보기 모드:
```
┌─ 미리보기 (실제 유튜브 댓글 영역처럼) ────────────┐
│                                                │
│  유저A · 1시간 전                              │
│  정말 도움됐어요. 6개월째 사용중인데 효과 있네요.│
│  ❤ 12   답글 ▾                                │
│   └ 유저B · 30분 전                            │
│      감사합니다 :)                              │
│      ❤ 5   답글 ▾                              │
│       └ 유저A · 10분 전 (재등장)               │
│          저도 더 알아볼게요                      │
│          ❤ 0                                  │
│                                                │
└────────────────────────────────────────────────┘
```

- 워커 자동 배정 (실제 운영 시 풀에서 슬롯 라벨 → 워커 매핑)
- AI 변형 적용된 텍스트 (mock 또는 호출)
- 좋아요 범위 중간값 표시
- 시간 분산: 운영자가 시점 분산 옵션 결정한 결과 표시

---

## 백엔드: 슬롯 CRUD

```
POST   /api/admin/presets/{id}/slots          (생성)
PATCH  /api/admin/presets/{id}/slots/{slot_id}  (수정)
DELETE /api/admin/presets/{id}/slots/{slot_id}  (삭제)
POST   /api/admin/presets/{id}/slots/reorder   (position 일괄 업데이트)
```

POST body:
```python
class SlotCreate(BaseModel):
    slot_label: str | None = None  # None = 자동 (다음 알파벳)
    reply_to_slot_label: str | None = None  # None = 메인 댓글
    text_template: str = ''
    length: Literal['short', 'medium', 'long'] = 'medium'
    emoji: Literal['none', 'sometimes', 'often'] = 'sometimes'
    ai_variation: int = 50  # 0~100
    like_min: int = 0
    like_max: int = 0
    like_distribution: Literal['adaptive', 'burst', 'spread', 'slow'] = 'adaptive'
```

자동 라벨링:
- POST 시 slot_label=None 이면 백엔드가 다음 알파벳 부여
- 사용 중인 라벨 (A, B, C) → D 부여
- 운영자가 명시적으로 'A' 선택하면 (재등장 의도) 그대로 사용

미리보기:
`POST /api/admin/presets/{id}/preview?brand_id=N`
```python
class PreviewResponse(BaseModel):
    slots: list[{
        slot_label: str,
        worker_alias: str,  # 워커 풀에서 매핑 (mock)
        rendered_text: str,  # AI 변형 + 톤 적용된 결과
        likes_estimated: int,
        scheduled_offset_min: int,  # 메인 댓글로부터의 offset
    }]
```

---

## 변경 파일

| 파일 | 변경 |
|---|---|
| `hydra/web/routes/presets.py` | 슬롯 CRUD + preview |
| `frontend/src/features/presets/preset-detail.tsx` | **신규** 편집 UI |
| `frontend/src/features/presets/slot-card.tsx` | **신규** 단일 슬롯 컨트롤 |
| `frontend/src/features/presets/preview.tsx` | **신규** 미리보기 |
| `frontend/src/types/preset.ts` | Slot 타입 추가 |
| `frontend/src/hooks/use-presets.ts` | 슬롯 CRUD hook |
| `frontend/src/routes/_authenticated/presets/$presetId.tsx` | 편집 페이지 마운트 |

---

## 검증

- tsc / vitest / build / pytest 통과
- 신규 endpoint 모두 401
- 자동 라벨링 정확 (A→B→C→...→Z→AA)
- 재등장 ↻ 표시 동작
- 미리보기에서 워커 매핑 mock 동작
- DB 변경 0 (PR-8d 의 모델 사용만)

---

## 자율 결정 영역

- A. 라벨 알파벳 26 초과 시 (AA, AB, ...) 또는 숫자 (A1, A2, ...) — 운영 환경에서 1 프리셋의 슬롯 수 일반적으로 < 10
- B. AI 변형 0~100 의 의미 (deterministic 0~확률적 변형 정도)
- C. 미리보기 워커 자동 배정 — 워커 풀의 alias 사용 (mock) 또는 실제 풀 호출
- D. 답글 대상 자기 자신 (A 가 A 에 답글) — 차단 (UI level)
- E. 시점 분산 옵션 4가지 (adaptive/burst/spread/slow) 의 실제 의미 — PR-8g 한도와 결합

---

## Out of scope

- 실제 댓글 생성 시 AI 호출 (PR-7-followup 또는 별도 백엔드 워커)
- 슬롯 정렬 drag-and-drop (현재는 reorder API + 위/아래 버튼)
- 다국어 양식 (한국어만)
- 워커 알리아스 자동 생성 (현재는 백엔드가 결정)
