# Manual E2E: 프로필 생성 + IP 로테이션

본 체크리스트는 자동화된 단위/통합 테스트로 검증 불가능한 실체(AdsPower, 실폰 ADB, 실 YouTube)를 수동으로 확인하기 위한 가이드입니다.

## 사전 요구

- [ ] AdsPower Global 실행 중, Local API `http://localhost:50325/status` 응답 확인
- [ ] `.env` 의 `ADSPOWER_API_KEY` 유효 (`curl` 으로 `/api/v1/user/list` 401 아닌지 확인)
- [ ] ADB 로 폰 연결: `adb devices` 에 기기 1대 표시 (폰 Wi-Fi OFF 상태)
- [ ] Server 실행: `./scripts/start-dev.sh`
- [ ] Alembic 마이그레이션 적용 상태: `alembic current` 이 `head` 표시
- [ ] Worker 실행: `HYDRA_WORKER_TOKEN=<token> python -m worker`
- [ ] Worker DB 레코드의 `ip_config` 필드에 `{"adb_device_id": "<ADB 시리얼>"}` 설정

## 1. 단일 계정 프로필 생성 흐름

- [ ] 기존 20개 중 테스트 계정 1개 선택 — `adspower_profile_id` 비어있어야 함
- [ ] 해당 계정에 페르소나 배정 확인 (`persona.device_hint` 존재)
- [ ] 서버 API 호출:
  ```bash
  curl -X POST http://localhost:8000/accounts/api/batch/auto-queue-profiles
  ```
  → `{"ok": true, "queued": 1, ...}` 응답 확인
- [ ] Task 테이블 확인:
  ```bash
  sqlite3 data/hydra.db "SELECT id, task_type, status FROM tasks WHERE task_type='create_profile';"
  ```
- [ ] Worker 로그: 태스크 pickup → AdsPower 호출 → `profile_id` 회신 확인
- [ ] AdsPower Global UI: 새 프로필 — 이름 `hydra_<id>_<gmail주인>`, 그룹 HYDRA, 비고 = 페르소나 요약
- [ ] DB: `accounts.adspower_profile_id` 설정됨, `status='profile_set'`
- [ ] `account_profile_history` 1행 — `fingerprint_snapshot` 이 JSON 저장됨

## 2. 지문 검증 (브라우저에서)

- [ ] AdsPower UI 에서 방금 만든 프로필 "Open" 버튼으로 열기
- [ ] `chrome://version` → UA 가 번들의 OS (Windows 10/11 또는 Mac) 와 일치
- [ ] `https://browserleaks.com/canvas` → 정상 렌더 (noise 적용 확인)
- [ ] `https://browserleaks.com/webgl` → Unmasked Vendor/Renderer 가 번들 GPU 풀과 일치
  - windows_heavy → Intel/NVIDIA/AMD 중 하나
  - mac_heavy → Apple M1/M2/M3
- [ ] `https://browserleaks.com/ip` → IP 가 테더링된 폰의 IP 와 일치 (`adb -s <id> shell curl ifconfig.me` 비교)
- [ ] `https://browserleaks.com/timezone` → Asia/Seoul (+09:00)
- [ ] DevTools Console: `navigator.languages` → `["ko-KR","ko","en-US","en"]`
- [ ] DevTools Console: `navigator.hardwareConcurrency` → 번들 값과 일치
- [ ] WebRTC 누수 없음 확인: `https://browserleaks.com/webrtc` → local IP 노출 X

## 3. 세션 전 IP 로테이션 훅

- [ ] Worker 레코드의 `ip_config` 에 `{"adb_device_id": "<실 ADB 시리얼>"}` 세팅됐는지
- [ ] 계정 A 로 첫 세션 시작 (수동 trigger: 캠페인/워밍업 태스크 수동 큐잉)
- [ ] `ip_log` 에 A 의 현재 IP 기록 확인
  ```bash
  sqlite3 data/hydra.db "SELECT account_id, ip_address, started_at FROM ip_log ORDER BY id DESC LIMIT 5;"
  ```
- [ ] 같은 Worker 에서 다른 계정 B 로 세션 시작
- [ ] Worker 로그: "IP rotation attempt 1/3" 메시지 확인 (B 세션 시작 전)
- [ ] `ip_log` 에서 B 의 IP 가 A 와 달라야 함
- [ ] 동일 계정 A 로 또 세션 → IP 변경 없어야 함 (직전 A IP 재사용)

## 4. 로테이션 실패 시나리오

- [ ] 폰 Wi-Fi 강제로 켜서 IP 로테이션이 실제론 변하지 않는 상태 만듦
  - (또는 ADB mock 으로 항상 같은 IP 리턴)
- [ ] 다른 계정 세션 시작 시도
- [ ] Worker 로그: "IP 로테이션 3회 실패" 메시지
- [ ] 텔레그램 설정돼 있으면 알림 도착 확인
- [ ] Task 상태 확인:
  ```bash
  sqlite3 data/hydra.db "SELECT id, status, retry_count, error_message, scheduled_at FROM tasks ORDER BY id DESC LIMIT 3;"
  ```
  → `status=pending`, `retry_count=1`, `error_message='ip_rotation_failed'`, `scheduled_at` 5~10분 뒤

## 5. 중복 생성 시나리오

- [ ] Task 테이블에 같은 계정에 대해 `create_profile` 2건 수동 삽입 (SQL)
- [ ] 두 번째 태스크 완료 후 AdsPower 에 만들어진 중복 프로필 폐기 태스크 자동 생성 확인
- [ ] AdsPower UI: 중복 프로필이 사라짐
- [ ] `accounts.adspower_profile_id` 는 첫 프로필로 유지

## 6. AdsPower 쿼터 엔드포인트

- [ ] `curl http://localhost:8000/accounts/api/adspower-quota`
- [ ] 응답: `adspower_count`, `linked_accounts`, `quota`, `used_ratio` 네 필드 확인
- [ ] 숫자가 실제 AdsPower UI 에서 보이는 프로필 수와 일치

## 체크리스트 통과 후

- [ ] 모든 단위/통합 테스트 통과: `pytest -q`
- [ ] 기존 20개 계정에 대해 batch-auto-queue-profiles 호출, 전원 프로필 생성 완료
- [ ] AdsPower 슬롯 사용량 `/accounts/api/adspower-quota` 에서 확인
- [ ] 하루 정도 20개 워밍업 돌려보고 IP 충돌/탐지 이슈 없는지 모니터링
