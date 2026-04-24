<#
HYDRA Windows 워커 설치 스크립트.

  iwr -Uri https://hydra-prod.duckdns.org/api/workers/setup.ps1 -OutFile setup.ps1
  .\setup.ps1 -Token 'ENROLLMENT_TOKEN' -ServerUrl 'https://hydra-prod.duckdns.org'

요구:
- PowerShell 관리자 권한
- 인터넷 연결
- 디스크 여유 5GB+ (playwright chromium + venv)
#>
param(
    [Parameter(Mandatory=$true)] [string]$Token,
    [Parameter(Mandatory=$true)] [string]$ServerUrl,
    [string]$InstallPath = "C:\hydra",
    [string]$RepoUrl = "https://github.com/tony4jr/hydra.git",
    [string]$AdsPowerApiKey = "",  # AdsPower Local API key (Settings → API)
    [switch]$DryRun  # 실 행동 없이 신호 루프만 (M2.1 검증)
)

$ErrorActionPreference = "Stop"
Write-Host "=== HYDRA Worker Setup ===" -ForegroundColor Cyan
Write-Host "  ServerUrl: $ServerUrl"
Write-Host "  InstallPath: $InstallPath"

# ─── 0. 관리자 권한 확인 ───
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "PowerShell 을 관리자 권한으로 실행해야 합니다."
    exit 1
}

# ─── 1. Chocolatey ───
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "[1/8] Chocolatey 설치..." -ForegroundColor Yellow
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = `
        [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString(
        'https://community.chocolatey.org/install.ps1'))
    $env:Path += ";C:\ProgramData\chocolatey\bin"
} else {
    Write-Host "[1/8] Chocolatey 이미 설치됨"
}

# ─── 2. 의존성 ───
Write-Host "[2/8] Python 3.11 / Git / ADB 설치..." -ForegroundColor Yellow
choco install -y python311 git adb --no-progress
# Tailscale 은 선택 — 실패해도 진행
choco install -y tailscale --no-progress 2>$null

# 새로 설치된 명령어들을 현재 세션에서 인식
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
            [System.Environment]::GetEnvironmentVariable("Path", "User")

# ─── 3. NTP 동기화 (타임스큐 방지) ───
Write-Host "[3/8] NTP 동기화..." -ForegroundColor Yellow
w32tm /config /manualpeerlist:"time.windows.com,time.google.com" `
      /syncfromflags:manual /reliable:yes /update | Out-Null
Restart-Service w32time -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
w32tm /resync /nowait | Out-Null

# ─── 4. Repo clone ───
Write-Host "[4/8] Repo clone → $InstallPath..." -ForegroundColor Yellow
if (-not (Test-Path $InstallPath)) {
    git clone $RepoUrl $InstallPath
} else {
    Write-Host "  이미 존재 — pull 시도"
    Push-Location $InstallPath
    git fetch origin main
    git reset --hard origin/main
    Pop-Location
}
Set-Location $InstallPath

# ─── 5. venv + Python 의존성 + Playwright chromium ───
Write-Host "[5/8] venv + pip install + playwright chromium..." -ForegroundColor Yellow
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& ".\.venv\Scripts\pip.exe" install -e . --quiet
& ".\.venv\Scripts\python.exe" -m playwright install chromium

# ─── 6. Enrollment ───
Write-Host "[6/8] /api/workers/enroll 호출..." -ForegroundColor Yellow
$hostname = $env:COMPUTERNAME
$body = @{ enrollment_token = $Token; hostname = $hostname } | ConvertTo-Json
$resp = Invoke-RestMethod -Method Post -Uri "$ServerUrl/api/workers/enroll" `
        -ContentType "application/json" -Body $body
$workerToken = $resp.worker_token
$secrets = $resp.secrets
Write-Host "  worker_id=$($resp.worker_id)"

# ─── 7. DPAPI 로 secrets.enc 저장 ───
Write-Host "[7/8] secrets DPAPI(LocalMachine) 암호화 저장..." -ForegroundColor Yellow
$envContent = @"
SERVER_URL=$ServerUrl
WORKER_TOKEN=$workerToken
WORKER_HOSTNAME=$hostname
DB_CRYPTO_KEY=$($secrets.DB_CRYPTO_KEY)
$(if ($AdsPowerApiKey) { "ADSPOWER_API_KEY=$AdsPowerApiKey" } else { "" })
$(if ($DryRun) { "HYDRA_WORKER_DRY_RUN=1" } else { "" })
"@
Add-Type -AssemblyName System.Security
$plain = [System.Text.Encoding]::UTF8.GetBytes($envContent)
$enc = [System.Security.Cryptography.ProtectedData]::Protect(
    $plain, $null,
    [System.Security.Cryptography.DataProtectionScope]::LocalMachine)
[System.IO.File]::WriteAllBytes(
    (Join-Path $InstallPath "secrets.enc"), $enc)
# 평문은 즉시 제거
Remove-Variable envContent, plain -ErrorAction SilentlyContinue

# ─── 7a. 수동 사전 작업 안내 (AdsPower 브라우저 커널) ───
Write-Host "" -ForegroundColor Yellow
Write-Host "========== 워커 세팅 완료 전 수동 작업 ==========" -ForegroundColor Cyan
Write-Host " AdsPower 앱을 열고:" -ForegroundColor Yellow
Write-Host "   프로필 > 편집 > 브라우저 코어 > 모든 Chrome 버전 다운로드" -ForegroundColor Yellow
Write-Host " (이 워커가 사용할 프로필의 커널을 전부 받아둬야" -ForegroundColor Yellow
Write-Host "  첫 태스크 실행 시 download 대기로 실패하지 않음)" -ForegroundColor Yellow
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# ─── 8. Task Scheduler 등록 ───
Write-Host "[8/8] Task Scheduler 등록..." -ForegroundColor Yellow
# 로그 디렉토리
$logDir = Join-Path $InstallPath "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

# Task Scheduler 는 stdout 리다이렉트 직접 지원 안 함 → cmd 로 감싸서 처리
# 로그 파일은 매 기동 시 타임스탬프로 새로 생성 (자동 로테이션 효과 + 기존 파일 보존)
# 30일 이상 된 로그는 별도 cleanup (아래 Unregister 전에 cleanup 트리거)
$wrapperCmd = "cmd.exe"
$wrapperArgs = "/c `"`"$($InstallPath)\.venv\Scripts\python.exe`" -m worker >> `"$($logDir)\worker-%date:~0,4%%date:~5,2%%date:~8,2%.log`" 2>&1`""

$action = New-ScheduledTaskAction `
    -Execute $wrapperCmd `
    -Argument $wrapperArgs `
    -WorkingDirectory $InstallPath
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "HydraWorker" `
    -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  - secrets: $InstallPath\secrets.enc (DPAPI/LocalMachine)"
Write-Host "  - Task:    HydraWorker (재부팅 시 자동 시작)"
if ($DryRun) {
    Write-Host "  - Mode:    DRY-RUN (실 행동 없음, 신호 루프만)" -ForegroundColor Yellow
} else {
    Write-Host "  - Mode:    LIVE (실제 YouTube 액션 수행)" -ForegroundColor Magenta
}
Write-Host ""
Write-Host "지금 바로 시작하려면:"
Write-Host "  Start-ScheduledTask -TaskName HydraWorker" -ForegroundColor Cyan
Write-Host ""
Write-Host "로그 보려면:"
Write-Host "  Get-ScheduledTaskInfo -TaskName HydraWorker"
