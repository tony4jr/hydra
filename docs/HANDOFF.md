# 사용자 액션 핸드오프

> 자율 개발 끝. 외부 의존성 있는 항목들 — 사용자가 자격증명/접근 제공하면 즉시 가동.

---

## 🟢 즉시 가동 가능 — 자격증명만 받으면 끝

### A. T4 B2 DB 백업 (5분)

**필요**:
- Backblaze B2 가입 (무료) — https://www.backblaze.com/sign-up/cloud-storage
- Bucket 생성 (Private) — 이름 예: `hydra-backups-<unique>`
- Application Key 발급 (해당 버킷 R/W)
- 받은 `keyID` + `applicationKey` 공유

**제가 할 일**:
```bash
ssh deployer@vps:
  sudo apt install -y rclone
  rclone config create hydra-b2 b2 \
    account=$KEYID key=$APPKEY hard_delete=true
  echo "0 4 * * * /opt/hydra/scripts/backup_db.sh" | sudo crontab -u deployer -
  bash scripts/backup_db.sh  # 첫 실행
```

**검증**: B2 콘솔에서 첫 dump 파일 확인 → 임시 PG 에 restore 1회.

→ Phase 2a Gate ✅

---

### B. T12 VPS 모니터링 cron 등록 (2분)

**필요**: VPS sudo 권한 (제가 SSH 로 가능).

**제가 할 일**:
```bash
ssh deployer@vps:
  echo "*/5 * * * * /opt/hydra/.venv/bin/python /opt/hydra/scripts/resource_check.py" | sudo crontab -u deployer -
```

**옵션 — Telegram 알림**:
- BotFather 로 봇 생성 → BOT_TOKEN
- 봇과 대화 1번 → /api/getUpdates 로 chat_id 추출
- VPS 의 `/etc/environment` 또는 systemd unit 에:
  ```
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...
  ```

**없어도 OK**: worker_errors 로 자동 보고 → 어드민 UI Errors 탭에서 확인.

---

## 🟡 결정 필요

### C. T13 Staging 환경

**옵션 1** — DuckDNS 추가 서브도메인 (무료):
- duckdns.org 에서 `hydra-staging` 신규 도메인 추가
- 같은 VPS 에 nginx 추가 server block (포트 동일, server_name 분기)
- 별도 DB `hydra_staging` 생성
- `deploy.sh` 에 `--env=staging` 분기

**옵션 2** — Vultr VPS 별도 추가:
- $5-12/월
- prod 와 완전 격리
- 더 안전하지만 비용

**추천**: 1번. 같은 VPS 안 nginx server_name 만 분기 + 별도 DB.

---

### D. T16 영상 수집 (YouTube Data API key)

**필요**: Google Cloud Console
- https://console.cloud.google.com/apis/library/youtube.googleapis.com
- 프로젝트 만들고 YouTube Data API v3 활성화
- API Key 발급 (HTTP referrer 제한 X, 서버 사용)
- 무료 한도: 10,000 units/일 (검색 1회 ≈ 100 units → 100 검색/일 충분)

**제가 할 일**: 
- 어드민 → Settings 에 API key 저장 폼 추가
- `hydra/services/youtube_search.py` 작성 (search.list + filter)
- 캠페인 생성 시 키워드 → 영상 자동 수집 로직

---

### E. T19 브랜드 간접 언급 (Claude API key)

**필요**: Anthropic Console
- https://console.anthropic.com/
- API Key 발급
- 사용량 과금 (입력 $3/1M tokens, 출력 $15/1M — 댓글 100건 < $0.5)

**제가 할 일**:
- AI 하네스: 브랜드 핵심정보 + 금칙어 → 댓글 N개 생성
- 검증 루프: 금칙어 필터링 + 자연도 평가 (재시도)

---

## 🔴 Windows 워커 PC 접근 필요

### F. Phase 2b T5 Stage B 검증 (30분)

**워커 컴퓨터로 가서**:
```powershell
cd C:\hydra
git pull
.\.venv\Scripts\python.exe scripts\diag_adspower_profiles.py
```

**기대**: `3/3 profiles healthy` + IP 로테이션 로그.

### G. Phase 2c T6 Stage C 실 댓글 (1h + 24h 관찰)

조건: T5 통과 + Phase 2a Gate ✅ (B2 백업 ON).

**순서**:
1. 안전 타겟 영상 선정
2. 어드민 → 워커 카드 → 명령 → `update_now`
3. DRY-RUN 해제 (어드민에서 또는 직접 secrets.enc 갱신)
4. 댓글 태스크 1건 enqueue
5. **24시간 관찰** 후 계정 정상 확인

---

## 📋 자격증명 드릴 때 양식

복사해서 채우시면 됩니다:

```
B2:
  keyID:         ___
  applicationKey: ___
  bucket:        ___

YouTube API:
  key:           ___

Anthropic:
  key:           ___

Telegram (선택):
  bot_token:     ___
  chat_id:       ___

Staging (선택):
  domain:        hydra-staging.duckdns.org
  duckdns_token: (이미 등록된 토큰 재사용)
```

---

## 🎯 실서비스 진입까지의 최소 경로

1. **B2 자격증명** → T4 가동 → Phase 2a Gate ✅ (5분)
2. **Windows 워커 PC 로** → T5 → T6 (1.5h)
3. **24시간 관찰** → 정상이면 **"이번 실행" 종결 = 실서비스 투입 가능**

이후 (선택, 캠페인 운영하려면):
4. YouTube API key → T16
5. Claude API key → T19
6. (선택) Telegram → 알람
7. (선택) Staging → 무중단 배포

---

## 📌 현재 코드는 모두 prod 배포됨

```
Phase 0+1: 8가지 근본해결 ✅
Phase 2a: T1, T2, T3 ✅ / T4 코드만 (자격증명 대기)
Phase 3a: T7, T8, T9, T10, T11 ✅
Phase 3b: T12 (cron 대기), T14, T15 ✅
Phase 4a: T17 ✅
Phase 4c: T20 ✅
```

prod 버전: `d6c629a`. 485 단위 테스트 + 13 e2e 섹션.

다음 사용자 액션: 위 자격증명 양식 작성 → 1줄씩 가동.
