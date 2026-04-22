# HYDRA Worker 설치 가이드 (Windows)

## 요구사항
- Windows 10/11, PowerShell 5.1+
- **관리자 권한**
- 디스크 여유 5GB+
- 인터넷 접속

## 1. 어드민 UI 에서 enrollment token 발급

```
POST /api/admin/workers/enroll
Authorization: Bearer <admin JWT>
{ "worker_name": "pc-01", "ttl_hours": 24 }
```

응답 `install_command` 1줄 복사.

## 2. 워커 PC 에서 PowerShell(관리자) 실행

```powershell
iwr -Uri https://hydra-prod.duckdns.org/api/workers/setup.ps1 -OutFile setup.ps1
.\setup.ps1 -Token 'ENROLLMENT_JWT' -ServerUrl 'https://hydra-prod.duckdns.org'
```

설치 단계 (약 10~20분):
1. Chocolatey
2. Python 3.11 / Git / ADB / Tailscale
3. NTP 동기화
4. `git clone` → `C:\hydra`
5. venv + `pip install -e .` + `playwright install chromium`
6. `/api/workers/enroll` 호출 → worker_token 수신
7. DPAPI(LocalMachine) 로 `C:\hydra\secrets.enc` 저장
8. Task Scheduler `HydraWorker` 등록 (AtStartup, SYSTEM)

## 3. 검증

- 어드민 UI 의 워커 목록에 새 워커가 표시됨
- `last_heartbeat` 가 최근 시각으로 갱신됨
- 수동 시작: `Start-ScheduledTask -TaskName HydraWorker`

## 4. 재설치 / 토큰 회전

같은 `worker_name` 으로 다시 enrollment token 을 발급받아 실행하면 자동으로
worker_token 이 회전된다 (이전 token 은 즉시 무효).

## 5. 삭제

```powershell
Unregister-ScheduledTask -TaskName HydraWorker -Confirm:$false
Remove-Item -Recurse -Force C:\hydra
```
