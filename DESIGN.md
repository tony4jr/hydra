# HYDRA Design Manifesto — Living Ops Console

> 2026-04-24 · 내부 운영자부터 외부 SaaS 고객까지 평생 쓰는 대시보드
> 참조 컨셉: Toss(감성) × Linear(밀도) × Mission Control(에너지)

## 1. 한 줄 정체성

**"살아있는 관제 콘솔 — 히드라의 여러 머리가 숨 쉬는 화면"**

HYDRA 는 이름 그대로 **여러 머리를 동시에 가동**하는 시스템. 대시보드는 그 여러 머리가 **동시에 숨 쉬는 모습** 을 보여주어야 한다. 정적인 표가 아니라, 지속적으로 맥동하는 라이브 시스템.

## 2. 디자인 원칙

### 2-1. 숨 쉬는 (Living)
- 모든 상태 표시는 **미세한 애니메이션**: 온라인 LED 는 심박처럼 pulse, 큐 카운트는 숫자 카운트업, 새 태스크는 fade-in
- 데이터 갱신이 **깜빡임 없이 smooth** — skeleton 대신 진행형 전환
- Hover, click, 상태 변화마다 **물리적 tactile feedback**

### 2-2. 깊이 있는 다크 (Deep Dark)
- 배경은 **pure black 이 아닌 slate-950** 기반, 카드/패널은 그 위에 light alpha 로 떠 있는 느낌
- 컬러는 **의미 있을 때만** — 기본은 neutral, 상태가 중요한 순간에만 green/amber/destructive
- 네온/과한 그라데이션 금지. **깊이 + 대비 + 투명도** 로 계층 표현

### 2-3. 정보 밀도 (Density that breathes)
- Linear 수준의 밀도, 하지만 숨 막히지 않게 **넉넉한 여백과 일관된 grid**
- 한 화면에 많은 것을 보여주되, **시각 계층** (크기, 무게, 색, 투명도) 으로 우선순위 분명
- 모바일에선 1-column 으로 깔끔히 재배열

### 2-4. 미션 콕핏 코너 (홈 상단 1개 섹션만)
- 홈 최상단에 **실시간 신호 흐름 시각화** — 워커↔서버↔계정 사이 line 이 흐르고, heartbeat 가 펄스로 번지고, 태스크 배정은 노드 간 이동 애니메이션
- 이 섹션이 "히드라" 스토리의 첫인상. 나머지는 차분한 Living 톤.

### 2-5. 파워유저 레이어 (나중에 덮는 밀도)
- `Cmd+K` 커맨드 팔레트 — 어떤 페이지에서도 계정·워커·캠페인 검색/이동
- 키보드 단축키 일관 (Linear 스타일)
- 비밀이 아닌 "알면 빨라지는" 기능으로

## 3. 색상 팔레트 (Tailwind 4 CSS variables 기반)

```css
/* 기본 — 현재 shadcn slate 유지 */
--background: 224 71% 4%;      /* slate-950 */
--foreground: 210 20% 98%;     /* slate-50 */
--card: 215 28% 9%;            /* slate-900 이지만 alpha */
--border: 215 14% 17% / 0.3;   /* 투명도 있는 경계 */

/* 상태 전용 — 의미 있을 때만 */
--ok: 142 71% 45%;             /* green-500 — 온라인, 성공 */
--warn: 38 92% 50%;            /* amber-500 — 주의, running */
--danger: 0 84% 60%;           /* red-500 — 실패, 긴급 */
--signal: 199 89% 48%;         /* sky-500 — 액션, 링크 */

/* 브랜드 악센트 — 히드라 */
--hydra-core: 258 90% 66%;     /* 보라빛, 로고/히어로 */
--hydra-glow: 189 94% 55%;     /* 청록, 신호 흐름 */
```

**네온은 절대 표면 채우기용 X** — glow / shadow / line 에만.

## 4. 타이포그래피

- **본문**: Inter Variable (기존)
- **숫자/모노**: JetBrains Mono Variable — 태스크 ID, 버전 해시, 시각
- **히어로 숫자**: 큰 지표는 `text-4xl font-bold tracking-tight`
- 제목은 **묵직하지만 얇은** 웨이트 (font-semibold 최대), 절대 font-black 금지

## 5. 모션 언어

- **숫자 변화**: `useCountUp` 같은 tween, 800~1200ms
- **상태 LED**: 2초 주기 pulse (opacity 0.4 → 1.0)
- **카드 hover**: `translate-y-[-2px]` + shadow 깊이 증가, 200ms
- **섹션 전환**: fade + 살짝 up, 300ms
- **태스크 완료**: 짧은 checkmark 그리기 애니메이션 (Lottie 없이 SVG path)

## 6. 컴포넌트 원칙

### 6-1. StatCard (핵심)
- 숫자는 크고 살아있게 (tween + pulse)
- 라벨은 작고 uppercase tracking-wide
- 보조 정보는 맨 아래 흐리게
- 클릭 가능한 경우 hover 시 그라데이션 border 전이

### 6-2. Data Tables
- 기본 table 그대로, 단 row hover 가 부드럽게 번짐
- Status 셀은 **텍스트 대신 LED dot + 라벨** 세트
- Timestamp 는 "23초 전" 같은 relative + tooltip 으로 절대 시각
- 항상 **정렬/필터/inline action** 제공

### 6-3. Live Log Stream (선택적)
- 우측 drawer 또는 페이지 끝에 실시간 로그가 흐름
- 새 항목은 위로 push + fade-in
- 터미널 느낌, 그러나 monospace + 색 구분

### 6-4. Command Palette (`Cmd+K`)
- 어느 화면에서든 열림
- 계정/워커/캠페인/최근 태스크 검색
- 실행 (이동, 일시정지, 배포, 계정 등록 등)

## 7. 금기 사항

- ❌ 과한 그라데이션 배경 (glassmorphism 2020 스타일)
- ❌ 네온 색으로 표면 채우기
- ❌ 불필요한 테두리 / 꽉 찬 카드
- ❌ 스켈레톤 로더 남발 (가능하면 optimistic + smooth transition)
- ❌ 왼쪽 navigation 외 **사이드바에 모달/드롭다운 중복** (Linear 스타일 유지)

## 8. 기존 기능 매핑 — 어떻게 "살아있게" 재디자인 하나

| 현재 | 새 경험 |
|---|---|
| `/workers` 정적 카드 리스트 | 워커별 "숨 쉬는" 노드, current_task 흐름 시각화, 클릭 시 상세 drawer |
| `/accounts` 표 | 상태별 레인 (registered / warmup / active / suspended) 칸반, 카드에 warmup_day progress ring |
| `/tasks` stats | 상단 4 지표 카운트업 + 하단 라이브 로그 스트림 (최근 이벤트 흐름) |
| `/audit` | timeline 스타일 — 시간 축 따라 이벤트 흐름, action 별 아이콘 |
| 대시보드 홈 | 상단: **미션 콕핏** — 워커·서버·계정·태스크 간 신호 흐름 라이브 그래프 / 중간: 살아있는 stat 카드 / 하단: 최근 활동 스트림 |

## 9. 구현 전략

- **신규 경로**: `frontend/src/new-ui/` 에 시작, 기존 페이지 손대지 않음
- **병행 운영**: `/v2/*` 프리픽스로 새 라우트 → 안정되면 기본 라우트로 교체
- **컴포넌트 공유**: shadcn ui 기본 컴포넌트는 그대로 쓰되, `new-ui/components/` 에 HYDRA 전용 wrapper (LiveStatCard, WorkerPulseCard 등)
- **점진적 이전**: 홈 → 워커 → 태스크 → 계정 → 캠페인 (신규 M2.3) → 기타

## 10. 이 문서의 역할

- Claude Design / v0 / 디자이너 / 나(Claude Code) 공통 북극성
- 외부 디자인 툴에 **"DESIGN.md 를 참고해서 만들어줘"** 한 문장으로 컨텍스트 전달
- 의사결정 막힐 때 돌아올 기준점

## 11. 살아있음 증거 — "이 화면은 혁신적인가" 체크리스트

- [ ] 첫 5초 안에 "살아있다" 는 느낌이 드는가? (맥동, 변화)
- [ ] 5분 써도 피로하지 않은 타이포 / 색 대비인가?
- [ ] 모바일에서도 정보 계층이 뭉그러지지 않는가?
- [ ] 동일한 경험을 **상상하기 어려울 정도로** 정체성이 뚜렷한가?
- [ ] 작은 성공 (태스크 완료 등) 에 시각적 **리워드** 가 있는가?
- [ ] 운영자가 **키보드만으로** 대부분의 일을 처리할 수 있는가?
