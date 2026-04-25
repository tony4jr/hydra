# 검증 가이드 — 단계별 자체검증

## 자동화된 검증 3계층

### 계층 1: 단위 테스트 (commit 전)
```bash
source .venv/bin/activate
python -m pytest tests/ -q --ignore=tests/test_language_setup.py
```
**현재 상태**: 453 passed (2026-04-25 기준)

각 T 작업 commit 시 반드시 통과해야 함.

### 계층 2: E2E 스모크 테스트 (deploy 후)
실 VPS 에 대해 13개 섹션 자동 검증:

```bash
HYDRA_URL="https://hydra-prod.duckdns.org" \
ADMIN_EMAIL="admin@hydra.local" \
ADMIN_PASSWORD="..." \
bash scripts/e2e_check.sh
```

**검증 항목**:
| # | 섹션 | 검증 |
|---|---|---|
| 1 | 공개 엔드포인트 | setup.ps1 / login 422 |
| 2 | 어드민 인증 | JWT 토큰 발급 |
| 3 | 미인증 401 | server-config / deploy / presets |
| 4 | 서버 상태 | current_version / paused |
| 5 | 워커 enrollment | admin → worker → heartbeat |
| 6 | 태스크 큐 | fetch 정상 응답 |
| 7 | 아바타 | upload + serve + delete |
| 8 | 감사 로그 | total > 0 |
| 9 | 태스크 stats/recent + workers | current_task 필드 |
| **10** | **T1 스크린샷** | multipart 업로드 → ok |
| **11** | **T2 VPS 서빙** | / → React HTML (placeholder 탈출) |
| **12** | **T3 원격 명령** | 발행/거부/heartbeat 필드 |
| **13** | **T4 B2 백업** | 자격증명 존재 시 ok |

**통과 기준**: PASS=>0, FAIL=0. exit 코드 = FAIL 수.

### 계층 3: 사용자 육안 검증 (Phase 종료 시)
- 어드민 UI 에서 직접 클릭/관찰
- Phase 별 체크리스트는 `docs/ROADMAP.md` 의 T1~T6 검증 게이트 참조

---

## Phase 별 게이트

### Phase 2 종료 게이트 (이번 실행)
1. **계층 1 통과**: pytest 453 green
2. **계층 2 통과**: e2e_check.sh exit 0 (FAIL=0)
3. **계층 3 사용자 확인**:
   - [ ] 브라우저로 `/admin` 접속 → 로그인 → Workers → Errors 탭 표시
   - [ ] 워커 카드의 "원격 명령" 드롭다운 → 7개 명령 클릭 가능
   - [ ] 발행한 명령이 히트비트 후 워커가 실행 (실 워커 필요)
   - [ ] 스크린샷 캡처 후 모달에서 이미지 표시
   - [ ] B2 백업 (구성 시) 24h 내 파일 존재
4. **Stage C 실 댓글 1건** + **24시간 관찰** 통과

→ 모두 통과해야 Phase 3 진입.

---

## 빠른 검증 사이클

작업 → 커밋 → 배포 → 검증 4단계 자동화:

```bash
# 1) 단위 테스트
python -m pytest tests/ -q

# 2) 커밋 + 푸시
git add -A && git commit -m "..." && git push origin main

# 3) 백엔드 배포
ssh -i ~/.ssh/hydra_prod deployer@158.247.232.101 \
    'cd /opt/hydra && bash scripts/deploy.sh'

# 4) (UI 변경 시) 프론트 빌드+배포
bash scripts/build_and_deploy_frontend.sh

# 5) E2E 검증
bash scripts/e2e_check.sh
```

**오류 발생 시 5번이 어디서 깨졌는지 정확히 가리킴.**

---

## 견고화 전 점검 리스트

`docs/ROADMAP.md` 하단의 **"견고화 감사"** 테이블 참조. 5 영역 (인프라/워커/AdsPower/YouTube/보안) × 예상 실패 시나리오 × 현재 방어 × 미비점 매핑.

각 행마다:
- ✅ 자동 복구 작동 → green
- ⚠️ 수동 개입 필요 → yellow
- ❌ 미비 → red (해당 Phase task 로 추적)
