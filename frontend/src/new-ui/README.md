# new-ui — Living Ops Console (M2.4)

HYDRA 차세대 UI 실험 공간. 기존 `features/*` 와 별도로 구축 후 안정되면 기본으로 교체.

## 구조
- `pages/` — 라우트별 새 페이지 (예: dashboard.tsx, workers.tsx, …)
- `components/` — HYDRA 전용 wrapper (shadcn 기반) — LiveStatCard, WorkerPulseCard 등

## 라우트
- `/v2/*` 경로에 TanStack Router 로 마운트 예정 (신규 `frontend/src/routes/_authenticated/v2/` 생성)
- 안정화 후 기본 라우트로 교체 (기존 `features/*` 는 deprecated 표시 후 점진 제거)

## 디자인 기준
루트의 [DESIGN.md](../../../DESIGN.md) 참조.
