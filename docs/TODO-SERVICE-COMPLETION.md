# HYDRA v2 서비스 완성 투두 리스트

> 작성일: 2026-04-17
> 목표: 코드 완성 → 실제 동작 검증 → 운영 가능 상태

---

## Phase A: 로컬 통합 검증 (서버 + 프론트 + Worker)

### A-1. 서버 + 프론트엔드 동시 실행 확인
- [ ] `./scripts/start-dev.sh` 실행
- [ ] http://localhost:5173 접속 → 대시보드 로딩 확인
- [ ] 사이드바 9개 페이지 전부 클릭 → 에러 없이 렌더링 확인
- [ ] 각 페이지에서 API 호출 → 네트워크 탭에서 200 응답 확인
- [ ] 에러 나는 페이지 → 원인 파악 → 수정

### A-2. API 엔드포인트 전수 검사
- [ ] 브랜드 생성 (`POST /brands/api/create`) → 응답 확인
- [ ] 브랜드 목록 (`GET /brands/api/list`) → 생성한 브랜드 표시 확인
- [ ] 브랜드 수정 → 반영 확인
- [ ] 키워드 생성/목록
- [ ] 영상 수동 추가 (`POST /videos/api/add-manual`) → 목록 표시 확인
- [ ] 프리셋 목록 (`GET /api/presets/`) → A~J 10개 확인
- [ ] 프리셋 커스텀 생성 → 목록에 추가 확인
- [ ] 프리셋 수정/삭제
- [ ] 캠페인 생성 → 태스크 분해 확인 (DB에 Task 레코드 생성됐는지)
- [ ] 다이렉트 캠페인 생성
- [ ] Worker 등록 (`POST /api/workers/register`) → 토큰 발급 확인
- [ ] Worker 목록 (`GET /api/workers/`)
- [ ] 대시보드 통계 (`GET /api/stats`) → 숫자 정확한지
- [ ] 캘린더 (`GET /api/calendar`) → 데이터 반환 확인
- [ ] 설정 저장/로드 (`GET/POST /settings/api/all`, `/settings/api/save`)
- [ ] 계정 목록/상세/메트릭/이력
- [ ] 에러 로그 목록
- [ ] 시스템 상태

### A-3. 프론트엔드 CRUD 전수 검사
- [ ] 브랜드 추가 모달 → 입력 → 저장 → 목록 반영
- [ ] 브랜드 수정 모달 → 수정 → 저장 → 반영
- [ ] 캠페인 생성 모달 → 브랜드/프리셋/영상 선택 → 생성
- [ ] 다이렉트 캠페인 모달 → URL 입력 → 작업 선택 → 생성
- [ ] 프리셋 생성/수정/삭제 (설정 > 프리셋)
- [ ] 워커 추가 다이얼로그 → 이름 + 시크릿 → 토큰 표시
- [ ] 계정 행 클릭 → 상세 시트 열림 → 정보/메트릭/이력 표시
- [ ] 설정 > 일반 → API 키 저장
- [ ] 설정 > 행동 패턴 → 값 변경 → 저장

### A-4. WebSocket 실시간 확인
- [ ] 프론트에서 WebSocket 연결 (`/ws`) → 콘솔에서 연결 상태 확인
- [ ] 태스크 완료 시 대시보드에 실시간 반영되는지

---

## Phase B: 코드 미완성 부분 구현

### B-1. video_collector 실제 YouTube API 연결
- [ ] `hydra/services/video_collector.py`의 `collect_videos_for_brand` 완성
- [ ] 기존 `hydra/collection/youtube_api.py`의 `YouTubeAPI` 클래스 임포트
- [ ] 실제 YouTube Data API 호출 → 검색 결과 → Video 테이블에 저장
- [ ] `/videos/api/collect` 엔드포인트에서 실제 수집 실행 확인
- [ ] YouTube API 키 필요 (이미 있으면 .env에 설정)

### B-2. 대시보드 인증 (Basic Auth)
- [ ] FastAPI에 간단한 관리자 인증 추가 (환경변수: ADMIN_USER, ADMIN_PASSWORD)
- [ ] 모든 대시보드 라우트에 인증 미들웨어 적용
- [ ] Worker API는 토큰 인증이므로 별도
- [ ] 프론트엔드에 로그인 페이지 추가 (or Basic Auth prompt)

### B-3. WebSocket 인증
- [ ] WebSocket 연결 시 쿼리 파라미터로 토큰 전달
- [ ] 유효하지 않은 토큰 → 연결 거부

### B-4. 기존 라우트 deprecated 코드 정리
- [ ] `hydra/web/routes/accounts.py` — `db.query(Model).get()` → `db.get(Model, id)` 전체 교체
- [ ] `hydra/web/routes/campaigns.py` — 동일
- [ ] `hydra/web/routes/brands.py` — 동일
- [ ] `hydra/web/routes/videos.py` — 동일
- [ ] 기타 라우트 파일 전부 확인

### B-5. N+1 쿼리 최적화
- [ ] `campaigns.py`의 `list_campaigns` — joinedload로 Video, Brand 한번에 로드
- [ ] `accounts.py`의 `list_accounts` — 배치 쿼리로 success_rate 계산
- [ ] `campaigns.py`의 `work_queue` — 동일

### B-6. 에러 응답 형식 통일
- [ ] 모든 라우트에서 에러 시 HTTPException 사용 (200 + error 메시지 방식 제거)
- [ ] 프론트엔드 fetchApi에서 에러 응답 처리 통일

---

## Phase C: 브라우저 자동화 실테스트

### C-1. AdsPower 연결 확인
- [ ] AdsPower 실행 상태 확인
- [ ] `hydra/browser/adspower.py`로 프로필 목록 조회 (`list_profiles`)
- [ ] 테스트 프로필 1개 열기 (`start_browser`) → WebSocket URL 받기
- [ ] Playwright CDP 연결 → 페이지 조작 가능한지 확인
- [ ] 프로필 닫기 (`stop_browser`)

### C-2. YouTube 기본 동작 테스트
- [ ] AdsPower 프로필 열기 → YouTube 접속
- [ ] 로그인 상태 확인 (`check_logged_in`)
- [ ] 로그인 안 되어 있으면 → `auto_login` 실행 → 성공 확인
- [ ] 2FA 코드 자동 입력 확인 (TOTP)
- [ ] YouTube 홈 스크롤 → 영상 클릭 → 시청 → 뒤로가기
- [ ] 숏츠 페이지 → 스와이프 → 시청

### C-3. 댓글 기능 테스트 (테스트 영상에서)
- [ ] 테스트용 영상 1개 선정 (본인 채널 or 오래된 영상)
- [ ] `scroll_to_comments` → 댓글 영역 도달 확인
- [ ] `post_comment` → 댓글 작성 → youtube_comment_id 반환 확인
- [ ] `post_reply` → 대댓글 작성 확인
- [ ] `click_like_button` → 좋아요 클릭 확인
- [ ] `check_ghost` → 작성한 댓글 존재 확인 (visible)
- [ ] 마우스 궤적 → 자연스러운 이동 확인

### C-4. 워밍업 세션 E2E 테스트
- [ ] 계정 1개로 워밍업 Day 1 실행
- [ ] 세션 시작 → YouTube 접속 → 숏츠 시청 → 영상 시청 → 좋아요
- [ ] 채널 설정 (이름, 아바타) 실행 확인
- [ ] 세션 종료 → 결과 보고
- [ ] Day 2 실행 → Gmail 확인 + Google 검색 + 댓글 작성
- [ ] Day 3 실행 → 댓글 고스트 체크 확인
- [ ] 에러 없이 완료되는지 확인
- [ ] 에러 발생 시 → 원인 파악 → 코드 수정

### C-5. IP 로테이션 테스트
- [ ] ADB 연결 확인 (`adb devices`)
- [ ] `rotate_ip` 실행 → 새 IP 할당 확인
- [ ] IP 변경 전후 비교 (curl ifconfig.me)

---

## Phase D: Worker 앱 E2E 테스트

### D-1. Worker 등록 + 연결
- [ ] 서버 실행 상태에서 `python scripts/generate_worker_token.py --name "PC-1"` → 토큰 발급
- [ ] `HYDRA_WORKER_TOKEN=<token> HYDRA_SERVER_URL=http://localhost:8000 python -m worker` 실행
- [ ] Worker가 서버에 heartbeat 전송 확인 (대시보드 워커 페이지에 나타남)
- [ ] Worker 상태 "online" 확인

### D-2. 태스크 수신 + 실행
- [ ] 대시보드에서 캠페인 생성 → Task 테이블에 태스크 생성 확인
- [ ] Worker가 태스크 fetch → 실행 → 결과 보고 확인
- [ ] 대시보드에서 태스크 완료 상태 확인
- [ ] 프로필 잠금 → 다른 Worker가 같은 프로필 못 열기 확인

### D-3. 워밍업 태스크 실행
- [ ] 대시보드에서 "워밍업" 태스크 수동 생성 (or API로)
- [ ] Worker가 워밍업 세션 실행
- [ ] AdsPower 프로필 열림 → YouTube 접속 → 워밍업 동작 확인
- [ ] 세션 완료 → 결과 보고 → 프로필 닫힘 확인

### D-4. 에러 핸들링 테스트
- [ ] AdsPower 꺼진 상태에서 Worker 실행 → 에러 핸들링 확인
- [ ] 존재하지 않는 프로필 ID로 태스크 → 실패 보고 확인
- [ ] Worker 강제 종료 → 서버에서 offline 감지 확인 (heartbeat timeout)
- [ ] 태스크 실패 → 재시도 로직 확인

---

## Phase E: Docker 배포 테스트

### E-1. 로컬 Docker 풀스택
- [ ] `docker-compose build` → 에러 없이 빌드
- [ ] `docker-compose up -d` → 3개 서비스 (db, server, frontend) 정상 시작
- [ ] http://localhost → Nginx → React 대시보드 접속
- [ ] http://localhost:8000/api/stats → API 직접 접속
- [ ] Nginx → FastAPI 프록시 동작 확인 (모든 API 경로)
- [ ] WebSocket 프록시 동작 확인
- [ ] `docker-compose down` → 정상 종료

### E-2. 데이터 마이그레이션
- [ ] Docker PostgreSQL 실행 상태에서
- [ ] `DB_URL=postgresql+psycopg2://hydra:hydra_secret@localhost:5432/hydra alembic upgrade head`
- [ ] `python scripts/migrate_sqlite_to_pg.py --sqlite ... --pg ...`
- [ ] 마이그레이션 완료 → 기존 20개 계정 확인
- [ ] 프리셋 시드: `python scripts/seed_presets.py`
- [ ] 대시보드에서 데이터 정상 표시 확인

### E-3. Docker Compose 안정성
- [ ] 24시간 방치 → 서비스 살아있는지 확인
- [ ] 서버 재시작 (`docker-compose restart server`) → 데이터 유지 확인
- [ ] DB 재시작 → 서버 자동 재연결 확인

---

## Phase F: VPS 배포

### F-1. VPS 서버 준비
- [ ] VPS 결제 (Vultr/AWS Lightsail, 2코어/2GB, 서울 리전)
- [ ] SSH 접속 설정
- [ ] Docker + Docker Compose 설치
- [ ] 방화벽 설정 (80, 443, 8000 포트)
- [ ] 도메인 연결 (선택)

### F-2. 배포
- [ ] 코드 업로드 (git clone or scp)
- [ ] `.env` 파일 설정 (API 키, DB 비밀번호, Worker 시크릿 등)
- [ ] `docker-compose up -d` 실행
- [ ] 브라우저에서 대시보드 접속 확인
- [ ] HTTPS 설정 (Let's Encrypt + Certbot)

### F-3. 데이터 마이그레이션 (VPS에서)
- [ ] SQLite 파일을 VPS에 업로드
- [ ] 마이그레이션 스크립트 실행
- [ ] 데이터 확인

### F-4. Worker 연결
- [ ] VPS에서 Worker 토큰 생성
- [ ] 로컬 PC에서 Worker 앱 설치 + 토큰 입력
- [ ] Worker가 VPS 서버에 연결 확인
- [ ] 대시보드에서 Worker 온라인 표시 확인

---

## Phase G: 운영 준비

### G-1. 프리셋 세부 조정
- [ ] 프리셋 A~J 각각의 스텝 구조 검토
- [ ] 역할(role), 톤(tone), 딜레이 범위(delay_min/max) 실운영에 맞게 조정
- [ ] 좋아요 수(like_count) 적절한지 확인
- [ ] 커스텀 프리셋 1~2개 추가 테스트

### G-2. 계정 한도 조정
- [ ] daily_comment_limit (기본 15) — 적절한지?
- [ ] daily_like_limit (기본 50) — 적절한지?
- [ ] weekly_comment_limit (기본 70) — 적절한지?
- [ ] weekly_like_limit (기본 300) — 적절한지?
- [ ] 보수적으로 시작 → 데이터 보면서 점진 조정

### G-3. 행동 패턴 설정
- [ ] 설정 > 행동 패턴에서 값 확인/조정
- [ ] 주간 프로모 목표
- [ ] 세션 간격
- [ ] 쿨다운 일수
- [ ] 고스트 쿨다운

### G-4. 브랜드 설정
- [ ] 첫 브랜드 등록 (이름, 상품, 카테고리)
- [ ] 홍보 키워드 설정
- [ ] 타겟 키워드 설정
- [ ] AI 가이드 (톤, 금지어)
- [ ] 주간 캠페인 목표 설정
- [ ] 자동 캠페인 활성화

### G-5. 계정 등록
- [ ] 기존 20개 계정 CSV 임포트 (or 데이터 마이그레이션으로 이전)
- [ ] 각 계정의 AdsPower 프로필 ID 매칭 확인
- [ ] TOTP 시크릿 설정 확인
- [ ] 페르소나 배정 확인

### G-6. 텔레그램 알림 설정
- [ ] 텔레그램 봇 생성 (or 기존 봇 사용)
- [ ] Bot Token + Chat ID를 설정에 입력
- [ ] 테스트 알림 전송 확인

### G-7. 백업 확인
- [ ] PostgreSQL 자동 백업 설정 (cron or Docker)
- [ ] 백업 파일 생성 확인
- [ ] 복원 테스트

---

## Phase H: 첫 실운영

### H-1. 워밍업 실행 (2~3일)
- [ ] 20개 계정 워밍업 태스크 생성
- [ ] Day 1 실행 → 결과 확인 → 에러 수정
- [ ] Day 2 실행 → Gmail/검색 + 댓글 → 확인
- [ ] Day 3 실행 → 고스트 체크 → 활성 전환
- [ ] 문제 계정 파악 → 처리

### H-2. 첫 캠페인 실행
- [ ] 타겟 영상 수집 (자동 or 수동)
- [ ] 캠페인 1개 생성 (가장 단순한 프리셋 A)
- [ ] Worker가 댓글 작성 → 댓글 존재 확인 (YouTube에서 직접)
- [ ] 좋아요 부스트 실행 → 좋아요 수 확인
- [ ] 고스트 체크 → 댓글 살아있는지 확인

### H-3. 모니터링
- [ ] 대시보드에서 실시간 진행률 확인
- [ ] 텔레그램 알림 수신 확인
- [ ] 에러 로그 확인 → 문제 없는지
- [ ] 계정 건강도 확인

### H-4. 점진적 확장
- [ ] 캠페인 수 늘리기 (1개 → 5개 → 10개)
- [ ] 다이렉트 캠페인 테스트
- [ ] 브랜드 추가
- [ ] 분석 페이지에서 성과 확인
- [ ] 상단 노출 여부 추적 시작

---

## 체크리스트 요약

| Phase | 내용 | 예상 소요 |
|-------|------|----------|
| A | 로컬 통합 검증 | 반나절 |
| B | 코드 미완성 구현 | 1~2일 |
| C | 브라우저 실테스트 | 반나절~1일 |
| D | Worker E2E 테스트 | 반나절 |
| E | Docker 배포 테스트 | 반나절 |
| F | VPS 배포 | 반나절 |
| G | 운영 준비 (설정) | 반나절 |
| H | 첫 실운영 | 2~3일 |
