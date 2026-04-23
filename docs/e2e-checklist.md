# HYDRA End-to-End 검증 체크리스트 (Task 36)

프로덕션 배포 전후에 돌리는 전수 스모크. 자동화 가능한 부분은 `scripts/e2e_check.sh`
로 커버되며, 나머지는 수동 브라우저/워커 확인이 필요하다.

## 자동 스모크 (≤30초)

```bash
export HYDRA_URL=https://hydra-prod.duckdns.org
export ADMIN_EMAIL=admin@hydra.local
export ADMIN_PASSWORD='...'        # 저장해둔 어드민 비번
bash scripts/e2e_check.sh
```

기대: `PASS: 14 / FAIL: 0`.

| # | 검증 | 수단 |
|---|---|---|
| 1 | setup.ps1 공개 서빙 | curl 200 |
| 2 | 로그인 422 (미들웨어 OK) | curl |
| 3 | 어드민 로그인 → JWT | /api/admin/auth/login |
| 4 | 미인증 401 (server-config/deploy/presets) | curl |
| 5 | server-config 조회 | /api/admin/server-config |
| 6 | admin /enroll → enrollment_token | /api/admin/workers/enroll |
| 7 | worker /enroll → worker_token | /api/workers/enroll |
| 8 | heartbeat/v2 current_version 일치 | /api/workers/heartbeat/v2 |
| 9 | 태스크 fetch | /api/tasks/v2/fetch |
| 10 | 아바타 업로드 | /api/admin/avatars/upload |
| 11 | 아바타 워커 다운로드 (PNG) | /api/avatars/... |
| 12 | 감사 로그 기록 | /api/admin/audit/list |

## 수동 브라우저 검증 (모바일 + 데스크톱)

### 로그인/네비게이션
- [ ] `/login` 로딩, 폼 포커스/탭 이동
- [ ] 잘못된 자격증명 → "invalid credentials" 토스트/메시지
- [ ] 성공 → `/` 대시보드 전환 + 토큰 localStorage 저장
- [ ] 토큰 제거 후 `/` 접근 → `/login` 리다이렉트 (가드)

### 대시보드
- [ ] ServerStatusBar 표시 (current_version/paused)
- [ ] "긴급 정지" 클릭 → paused=true 반영 (10초 내 폴링)
- [ ] "재개" 클릭 → paused=false
- [ ] "배포" 클릭 → confirm 프롬프트 → pid 토스트

### 워커
- [ ] `/workers` 목록 조회 (admin + legacy 병합)
- [ ] "워커 추가" → 이름 입력 → PowerShell install_command 생성 + 복사 버튼 동작
- [ ] 카드의 "편집" → 체크리스트 다이얼로그
- [ ] wildcard 토글 시 개별 체크박스 disabled
- [ ] 저장 후 서버 DB 반영 (`allowed_task_types`)

### 아바타
- [ ] `/avatars` 진입 → 트리 뷰 로드
- [ ] 카테고리 입력 + 드래그 앤 드롭 업로드
- [ ] .zip 업로드 시 내부 이미지 추출
- [ ] 휴지통 아이콘 → confirm → 삭제
- [ ] 트리에서 폴더 접기/펼치기

### 감사 로그
- [ ] `/audit` 진입 → 최신 순 로딩
- [ ] Action select 필터 적용
- [ ] User ID 필터
- [ ] 이전/다음 페이지네이션

## 모바일 별도 확인
- [ ] iPhone Safari 에서 로그인
- [ ] 긴급정지 버튼 터치 영역 44pt 이상
- [ ] 대시보드 ServerStatusBar 세로 스택 OK

## 서버 측 운영 상태
- [ ] `ssh deployer@... 'sudo systemctl is-active hydra-server'` → active
- [ ] `sudo systemctl is-active cron` → active (zombie cleanup)
- [ ] `/etc/cron.d/hydra-zombie` 존재 + `/var/log/hydra/zombie.log` 누적
- [ ] `sudo -u postgres pg_dump -d hydra_prod > ...dump` 가능
- [ ] nginx `client_max_body_size 50M` 설정 (zip 업로드)
- [ ] HTTPS 인증서 만료일 >30일 (`certbot certificates`)

## Worker 실전 연결 후 추가 (Phase 1e 이후)
- [ ] Windows PC 에서 setup.ps1 실행 → 자동 등록 → 워커 목록 반영
- [ ] `/api/admin/workers/{id}` PATCH → 다음 fetch 에 반영 확인
- [ ] 실제 create_account task 1건 → account-created 업로드 → accounts row 생성
- [ ] 워커 크래시 시뮬레이션 → 30분 후 좀비 복구 (cron) 확인

# deploy flow verify

# deploy v2 test
