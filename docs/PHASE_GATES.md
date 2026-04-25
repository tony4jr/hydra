# Phase Gates — 완료 조건 + 자체 검증 강제

> 모든 Phase 는 **명시적 entry/exit 게이트** + **자동 검증** + **사용자 승인** 3단계로만 전환.
> AI 가 임의로 "Phase 완료" 선언 금지.

---

# 게이트 운영 원칙

1. **각 Phase 는 4시간 이내 완료 가능 단위**로 자름. 큰 단위는 a/b/c 로 분할.
2. **Entry**: 직전 Phase exit 게이트 ✅ + 사용자 명시 승인 ("진입 ㄱ")
3. **Exit (자동)**: `bash scripts/e2e_check.sh --phase=N` exit 0
4. **Exit (수동)**: 사용자 체크리스트 모두 ✓
5. **둘 다 통과 안 하면** 다음 Phase 진입 불가. AI 는 미통과 항목으로 다시 돌아감.

---

# 분할된 Phase 표

| Phase | 작업 단위 | 예상 시간 | 장소 | Entry | 자동 검증 | 사용자 검증 |
|---|---|---|---|---|---|---|
| 0 | 로컬 MVP + VPS bootstrap | (완료) | — | — | — | — |
| 1 | 8가지 근본해결 + Stage 0/A | (완료) | — | — | e2e §1-9 | — |
| **2a** | T1-T4 (안전장치) | 6h | **Mac** | Phase 1 | e2e §10-13 | UI 클릭 5건 |
| **2b** | T5 Stage B | 30min | **Win** | 2a | diag 3/3 + IP | AdsPower 육안 |
| **2c** | T6 Stage C 실 댓글 | 1h+24h | **Win** | 2b | 댓글 게시 확인 | YouTube 육안 + 24h |
| **3a** | T7-T11 (운영 안정성) | 5h | Mac | 2c | e2e §14-18 | 1주 안정 운영 |
| **3b** | T12-T15 (프로덕션 하드닝) | 7h | Mac | 3a | e2e §19-22 | 모니터링 알람 동작 |
| **4a** | T16-T17 (캠페인 데이터) | 1.5d | Mac | 3b | e2e §23-24 | 영상 수집 100건 |
| **4b** | T18-T19 (캠페인 생성) | 2.5d | Mac | 4a | e2e §25-26 | AI 샘플 검수 |
| **4c** | T20 (실행 타이밍) | 1d | Mac+Win | 4b | e2e §27 | 다워커 댓글 1건 |
| 5 | UI 재설계 | 1-2주 | Mac | 4c 안정 | 별도 | 별도 |

---

# Phase 2a — 안전장치 (T1-T4)

## Entry
- [ ] Phase 1 e2e §1-9 통과
- [ ] 사용자 "진입 ㄱ"

## Tasks
- T1 스크린샷 캡처 ✅ (945f87f)
- T2 어드민 VPS 서빙 + Errors UI ✅ (898d662)
- T3 원격 명령 8종 ✅ (49d3f6d)
- T4 B2 DB 백업 cron ⬜

## Exit Gate (자동)
```bash
bash scripts/e2e_check.sh --phase=2a
```
조건:
- §10 T1 스크린샷 multipart 업로드 → ok
- §11 T2 / 가 React HTML 응답
- §12 T3 명령 발행/거부/heartbeat 필드
- §13 T4 B2 백업 24h 내 파일 존재 (`rclone ls b2:hydra-backups | head -1` 가 < 24h)

## Exit Gate (수동)
- [ ] 어드민 UI Workers 탭 → 워커 카드 보임 + 명령 드롭다운 작동
- [ ] Workers > 에러 로그 탭 → 리스트 + 필터 + 자동갱신
- [ ] 의도 에러 발생 → 10초 내 UI 에 표시 + 스크린샷 미리보기
- [ ] B2 콘솔에서 어제자 백업 확인 + 임시 PG 에 restore 1회 성공

## 진입 다음
**Phase 2b** (Windows 복귀 후 Stage B)

---

# Phase 2b — Stage B 검증 (T5)

## Entry
- [ ] Phase 2a exit gate 모두 ✓
- [ ] Windows 워커 PC 접근 가능
- [ ] AdsPower 모든 Chrome 커널 수동 다운로드 완료

## Task
- T5 `scripts/diag_adspower_profiles.py` 실행

## Exit Gate (자동)
- 진단 스크립트 결과: **3/3 profiles healthy + missing=0**
- 각 프로필별 IP 로테이션 로그 (3개 다른 exit IP)

## Exit Gate (수동)
- [ ] 사용자 콘솔 출력 붙임
- [ ] AdsPower 앱에서 3 프로필 정상 기동 시각 확인

---

# Phase 2c — Stage C 실 댓글 (T6) ⭐ "이번 실행"

## Entry
- [ ] Phase 2b exit ✓
- [ ] **사전 체크리스트** 모두 ✓:
  - [ ] T1 스크린샷 캡처 작동 (직전 24h 내 1건)
  - [ ] T2 어드민 Errors 탭 정상
  - [ ] T3 `update_now` 명령 → 워커 재시작 확인
  - [ ] T4 B2 백업 어제자 존재
- [ ] 안전 타겟 영상 선정 완료 (브랜드 무관, 한국어, 댓글 100+)

## Task
1. 어드민 → `update_now` 명령 → win-m2.2 최신 버전 확정
2. DRY-RUN 해제 (`HYDRA_WORKER_DRY_RUN` 제거 + `restart` 명령)
3. comment 태스크 1건 enqueue (`account_id=phuoclocphan36`, `video_id=<선정>`, win-m2.2 지정)
4. 실시간 관찰 (Errors 탭 + AdsPower 앱)

## Exit Gate (자동) — 즉시
- task.status = `done`
- worker_errors 에 task_fail 0건 (해당 시각 ±10분)
- IP 로테이션 로그 (`ip_logs` 테이블에 새 entry)

## Exit Gate (수동) — 즉시 + 24시간
- [ ] **즉시**: 실 YouTube 에서 댓글 게시 확인 (URL 공유)
- [ ] **즉시**: 타이핑 시간 자연 (5초~30초 사이)
- [ ] **즉시**: AdsPower 프로필 정상 종료
- [ ] **+24h**: 계정 로그인 정상
- [ ] **+24h**: 차단/경고 메시지 없음
- [ ] **+24h**: 댓글 그대로 살아있음 (자동 삭제 안 됨)

## ✅ 통과 시
**= "이번 실행" 완료**
**= 실서비스 투입 준비 완료**
**→ Phase 3a 진입 가능**

## ❌ 실패 시 분기
| 실패 유형 | 대응 |
|---|---|
| Captcha/2FA | identity_challenge 핸들러 보강 → 재시도 |
| DOM 못 찾음 | 스크린샷 + traceback → 셀렉터 수정 → `update_now` |
| BAN | 해당 계정 cooldown 30일 + 다른 계정 격리 검토 |
| IP 로테이션 실패 | ADB 연결 확인 → 폰 USB 디버깅 토글 |
| 24h 후 댓글 삭제 | 다른 영상으로 재시도 (특정 영상 정책일 수 있음) |
| 24h 후 계정 차단 | 안티디텍션 강화 → 계정 추가 cooldown |

---

# Phase 3a — 운영 안정성 (T7-T11)

## Entry
- [ ] Phase 2c 통과 + **1주 안정 운영** (실 댓글 5건+ 정상)

## Tasks (각 1시간)
- T7 Circuit Breaker — 연속 실패 시 워커 자동 pause
- T8 Exit IP 감시 UI — 24h 히스토리 + 충돌 강조
- T9 비상정지 버튼 — 모든 워커 stop_all_browsers 일괄
- T10 재시도 정책 차등 — task_type 별
- T11 UA/TZ/Lang 검증 — AdsPower ua API 활용

## Exit Gate (자동)
e2e §14-18 통과:
- §14 task_fail 5회 연속 → 워커 status=paused
- §15 IP 충돌 → worker_errors kind=ip_conflict 생성
- §16 비상정지 버튼 → 모든 워커 paused
- §17 retry_task 정책 → comment 영구실패 0회 / like 일시실패 3회 retry 확인
- §18 ua mismatch → diagnostic 알림

## Exit Gate (수동)
- [ ] 의도적으로 워커 5회 실패 트리거 → UI 에 paused 표시
- [ ] 어드민 비상정지 버튼 클릭 → 2단계 확인 → 모든 워커 정지

---

# Phase 3b — 프로덕션 하드닝 (T12-T15)

## Entry
- [ ] Phase 3a exit ✓ + **1주 무사고**

## Tasks (총 7h)
- T12 VPS 모니터링 + 알람 (1.5h) — UptimeRobot + resource cron + cert
- T13 Staging 환경 (3h) — `hydra-staging.duckdns.org`
- T14 Tags 분류 (1h) — AdsPower tags + 브랜드 그룹핑
- T15 FP 정기회전 (1.5h) — 30~60일 ± 지터

## Exit Gate (자동)
e2e §19-22:
- §19 healthz 다운 → Telegram 알림 (mock)
- §20 staging 도메인 분리 응답
- §21 프로필에 tag 추가 → list 에서 필터링
- §22 fingerprint 회전 dry-run

## Exit Gate (수동)
- [ ] 의도 VPS 서비스 중단 → Telegram 메시지 수신 확인
- [ ] staging 에 변경 배포 → prod 영향 없음 확인
- [ ] 프로필 1개 fingerprint 회전 → AdsPower 앱에서 변경 확인

---

# Phase 4a — 캠페인 데이터 (T16-T17)

## Entry
- [ ] Phase 3b ✓ + **2주 무사고**

## Tasks
- T16 키워드 → 영상 수집 (1d) — YouTube Data API + 하이브리드
- T17 다영상 캠페인 스키마 (0.5d) — campaigns ⟶ campaign_videos ⟶ tasks

## Exit Gate (자동)
- §23 키워드 "탈모" → 100+ 영상 수집 + DB insert
- §24 캠페인 생성 → tasks 자동 fan-out 확인

## Exit Gate (수동)
- [ ] 어드민 UI 에서 키워드 검색 → 영상 100+ 미리보기
- [ ] 캠페인 생성 → 워커들이 작업 시작 (DRY-RUN)

---

# Phase 4b — 캠페인 생성 (T18-T19)

## Entry
- [ ] Phase 4a ✓

## Tasks
- T18 퍼널 프리셋 편집기 (1d)
- T19 브랜드 간접 언급 시스템 (1.5d)

## Exit Gate (자동)
- §25 프리셋 슬라이더 변경 → 미생성 태스크 반영
- §26 브랜드 키워드 입력 → AI 샘플 3개 + 금칙어 필터링 통과

## Exit Gate (수동)
- [ ] 사용자가 AI 생성 댓글 10개 검수 → 자연도 OK
- [ ] 브랜드명 직접 언급 0건 (간접 멘션만)

---

# Phase 4c — 실행 타이밍 (T20)

## Entry
- [ ] Phase 4b ✓

## Tasks
- T20 다워커 좋아요 부스트 타이밍 (1d)

## Exit Gate (자동)
- §27 댓글 1건 → N분 후 다른 워커가 like 태스크 픽업

## Exit Gate (수동)
- [ ] 실 YouTube 에서 댓글 + 좋아요 부스트 시간차 확인 (다른 IP)

---

# Phase 5 — UI 재설계

별도 트랙. 기능 안정화 후 재착수.

---

# 게이트 자동 검증 — 코드 강제

`scripts/e2e_check.sh` 에 `--phase=N` 인자 추가 예정:

```bash
# Phase 2a 까지 모두 통과해야 다음 진입
bash scripts/e2e_check.sh --phase=2a
echo $?  # 0 = 통과, N = N개 실패 (Phase 진입 차단)
```

다음 phase 진입 시 첫 작업 commit 메시지에:
```
feat(2b-T5): Phase 2a gates ✓ (e2e exit 0, user approved)
```

---

# 운영 약속

1. **AI 는 phase 완료 자가선언 금지** — 항상 사용자 "ㄱ" 받아야
2. **사용자가 ✓ 안 한 항목 있으면** AI 는 그 항목으로 자동 회귀 + 수정
3. **24h 관찰 게이트는 단축 불가** — Stage C 의 핵심 안전장치
4. **e2e_check 추가 섹션은 phase 시작 시 작성** — task 끝나고 추가 X
