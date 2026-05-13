<#
HYDRA installer v2 — 단일 진입점.

paired install: desktop_worker (Task Scheduler) + admin_agent (NSSM service)
한 번에 깨끗하게 install. 기존 setup.ps1 (desktop only) + install-admin-agent-service.ps1
조합 폐기.

핵심 원칙 (Codex 권고):
1. 다운로드/실행 모두 절대경로 (캐시 회피)
2. preflight DNS check — 실패 시 즉시 abort
3. 기존 process / Task / Service 정리 후 깨끗하게
4. desktop secrets.enc 와 admin_agent NSSM env **완전 분리** — 서로 안 덮음
5. 중간 실패 시 명시 출력 + abort
6. SCRIPT_VERSION 출력 (server 가 serve 시 commit hash 치환)

사용 (paired enroll endpoint 가 install_command 로 생성):
  iwr /api/workers/install-hydra.ps1 -OutFile install.ps1
  .\install.ps1 -ServerUrl ... -DesktopToken ... -AgentToken ...
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$ServerUrl,
    [Parameter(Mandatory=$true)] [string]$DesktopToken,
    [Parameter(Mandatory=$true)] [string]$AgentToken,
    [string]$InstallPath = "C:\hydra",
    [string]$RepoUrl = "https://github.com/tony4jr/hydra.git",
    [string]$ServiceName = 'HydraAdminAgent',
    [string]$TaskName = 'HydraWorker'
)

$ErrorActionPreference = 'Stop'

# server 가 serve 시 치환하는 placeholder. 직접 실행 시 dev.
$SCRIPT_VERSION = '__HYDRA_COMMIT__'

# Codex installer v2 review: $ErrorActionPreference='Stop' 은 PowerShell native
# command (git, choco, nssm) 의 non-zero exit 을 자동 throw 안 함. 모든 외부
# 명령은 이 helper 로 호출 → exit code != 0 면 abort.
function Run-Native {
    param(
        [Parameter(Mandatory=$true)][scriptblock]$ScriptBlock,
        [Parameter(Mandatory=$true)][string]$What,
        [int[]]$AllowedExitCodes = @(0)
    )
    & $ScriptBlock
    $code = $LASTEXITCODE
    if ($AllowedExitCodes -notcontains $code) {
        throw "$What 실패 (exit $code). 이전 출력 참고."
    }
}

Write-Host "=== HYDRA installer v2 ===" -ForegroundColor Cyan
Write-Host "  Version:     $SCRIPT_VERSION"
Write-Host "  ServerUrl:   $ServerUrl"
Write-Host "  InstallPath: $InstallPath"

# ─── Admin 권한 확인 ─────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "PowerShell 을 관리자 권한으로 실행해야 합니다."
}

# ─── Preflight: DNS check ────────────────────────────────────────────────
Write-Host "[preflight] DNS resolve check..." -ForegroundColor Yellow
function Assert-Dns([string]$h) {
    try {
        [System.Net.Dns]::GetHostEntry($h) | Out-Null
        Write-Host "  OK: $h"
    } catch {
        throw "DNS resolve 실패: $h — 네트워크/DNS 설정 확인 후 재시도. (8.8.8.8 시도 권장)"
    }
}
$serverHost = ($ServerUrl -replace '^https?://','' -split '/')[0]
Assert-Dns $serverHost
Assert-Dns 'github.com'
Assert-Dns 'pypi.org'

# ─── 기존 worker process / Task / Service 정리 ────────────────────────────
Write-Host "[preflight] 기존 process / Task / Service 정리..." -ForegroundColor Yellow
try {
    Disable-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
} catch {}
$svcExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svcExists) {
    try { Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue } catch {}
}
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match 'python.*-m\s+worker' } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
Start-Sleep -Seconds 2

# ─── Chocolatey + Python 3.11 + Git + ADB + NSSM ─────────────────────────
Write-Host "[install] Chocolatey + Python 3.11 + Git + ADB + NSSM..." -ForegroundColor Yellow
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = `
        [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString(
        'https://community.chocolatey.org/install.ps1'))
    $env:Path += ";C:\ProgramData\chocolatey\bin"
}
Run-Native -What "choco install python311/git/adb/nssm" -ScriptBlock {
    choco install -y python311 git adb nssm --no-progress
}
# tailscale 은 선택 — 실패해도 진행. exit 1 (이미 설치) / 1641 도 허용.
& choco install -y tailscale --no-progress 2>$null | Out-Null
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
            [System.Environment]::GetEnvironmentVariable("Path", "User")

# ─── NTP 동기화 ───────────────────────────────────────────────────────────
Write-Host "[install] NTP sync..." -ForegroundColor Yellow
w32tm /config /manualpeerlist:"time.windows.com,time.google.com" `
      /syncfromflags:manual /reliable:yes /update | Out-Null
Restart-Service w32time -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
w32tm /resync /nowait | Out-Null

# ─── Repo clone / pull ───────────────────────────────────────────────────
Write-Host "[install] Repo $InstallPath..." -ForegroundColor Yellow
if (-not (Test-Path $InstallPath)) {
    Run-Native -What "git clone" -ScriptBlock {
        git clone $RepoUrl $InstallPath
    }
} else {
    Push-Location $InstallPath
    try {
        Run-Native -What "git fetch origin main" -ScriptBlock {
            git fetch origin main
        }
        Run-Native -What "git reset --hard origin/main" -ScriptBlock {
            git reset --hard origin/main
        }
    } finally {
        Pop-Location
    }
}
Set-Location $InstallPath
$repoHead = ((git -C $InstallPath rev-parse --short HEAD) | Out-String).Trim()
if (-not $repoHead) { throw "git rev-parse 실패 — repo 상태 확인" }
Write-Host "  repo HEAD: $repoHead"

# ─── venv + pip + playwright chromium ─────────────────────────────────────
Write-Host "[install] venv + pip install + playwright chromium..." -ForegroundColor Yellow
$pythonExe = Join-Path $InstallPath '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    Run-Native -What "py -3.11 -m venv" -ScriptBlock {
        py -3.11 -m venv (Join-Path $InstallPath '.venv')
    }
}
if (-not (Test-Path $pythonExe)) {
    throw "venv python.exe 미생성: $pythonExe"
}
Run-Native -What "pip upgrade" -ScriptBlock {
    & $pythonExe -m pip install --quiet --upgrade pip
}
Run-Native -What "pip install -e $InstallPath" -ScriptBlock {
    & $pythonExe -m pip install --quiet -e $InstallPath
}
# playwright install — 일부 환경에서 이미 있어 non-zero 가능. 비-치명적이라 warn 만.
& $pythonExe -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Warning "playwright install chromium exit $LASTEXITCODE — 이미 설치된 상태일 가능성. 계속 진행."
}

# ─── Desktop_worker enroll ────────────────────────────────────────────────
Write-Host "[enroll] desktop_worker..." -ForegroundColor Yellow
$body = @{
    enrollment_token = $DesktopToken
    hostname = $env:COMPUTERNAME
} | ConvertTo-Json -Compress
try {
    $desktopResp = Invoke-RestMethod -Method Post -Uri "$ServerUrl/api/workers/enroll" `
        -ContentType "application/json" -Body $body -TimeoutSec 30
} catch {
    throw "desktop enroll 실패: $($_.Exception.Message)"
}
if (-not $desktopResp.worker_token) {
    throw "desktop enroll 응답에 worker_token 없음"
}
Write-Host "  desktop worker_id=$($desktopResp.worker_id)"

# ─── secrets.enc (desktop 전용, admin_agent 는 안 건드림) ────────────────
Write-Host "[install] desktop secrets.enc (DPAPI)..." -ForegroundColor Yellow
$envContent = @"
SERVER_URL=$ServerUrl
WORKER_TOKEN=$($desktopResp.worker_token)
WORKER_HOSTNAME=$env:COMPUTERNAME
DB_CRYPTO_KEY=$($desktopResp.secrets.DB_CRYPTO_KEY)
"@
Add-Type -AssemblyName System.Security
$plain = [System.Text.Encoding]::UTF8.GetBytes($envContent)
$enc = [System.Security.Cryptography.ProtectedData]::Protect(
    $plain, $null,
    [System.Security.Cryptography.DataProtectionScope]::LocalMachine)
[System.IO.File]::WriteAllBytes((Join-Path $InstallPath "secrets.enc"), $enc)
Remove-Variable envContent, plain -ErrorAction SilentlyContinue

# ─── Desktop Task Scheduler ──────────────────────────────────────────────
Write-Host "[install] Desktop Task Scheduler ($TaskName)..." -ForegroundColor Yellow
$logDir = Join-Path $InstallPath "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$wrapperCmd = "cmd.exe"
$wrapperArgs = "/c `"`"$pythonExe`" -m worker >> `"$($logDir)\worker-%date:~0,4%%date:~5,2%%date:~8,2%.log`" 2>&1`""
$action = New-ScheduledTaskAction -Execute $wrapperCmd -Argument $wrapperArgs -WorkingDirectory $InstallPath
$triggerStartup = New-ScheduledTaskTrigger -AtStartup
$triggerWatchdog = New-ScheduledTaskTrigger `
    -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 9999)
$trigger = @($triggerStartup, $triggerWatchdog)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Enable-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null

# ─── Admin agent enroll ───────────────────────────────────────────────────
Write-Host "[enroll] admin_agent..." -ForegroundColor Yellow
$body = @{
    enrollment_token = $AgentToken
    hostname = $env:COMPUTERNAME
} | ConvertTo-Json -Compress
try {
    $agentResp = Invoke-RestMethod -Method Post -Uri "$ServerUrl/api/workers/enroll" `
        -ContentType "application/json" -Body $body -TimeoutSec 30
} catch {
    throw "admin_agent enroll 실패: $($_.Exception.Message)"
}
if (-not $agentResp.worker_token) {
    throw "admin_agent enroll 응답에 worker_token 없음"
}
Write-Host "  admin_agent worker_id=$($agentResp.worker_id)"

# ─── Admin agent NSSM service (secrets.enc 안 건드림 — env 전용) ─────────
Write-Host "[install] NSSM $ServiceName service..." -ForegroundColor Yellow
$nssmExe = ''
$nssmCmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
if ($nssmCmd) {
    $nssmExe = $nssmCmd.Source
} elseif (Test-Path 'C:\ProgramData\chocolatey\bin\nssm.exe') {
    $nssmExe = 'C:\ProgramData\chocolatey\bin\nssm.exe'
} else {
    throw "NSSM 미발견 (choco install 실패?)"
}

# 기존 service 정리
$svcExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svcExists) {
    & $nssmExe stop $ServiceName 2>$null | Out-Null
    & $nssmExe remove $ServiceName confirm 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

$agentLog = Join-Path $logDir 'admin-agent.log'
Run-Native -What "nssm install $ServiceName" -ScriptBlock {
    & $nssmExe install $ServiceName $pythonExe '-m' 'worker.admin_agent'
}
Run-Native -What "nssm set AppDirectory" -ScriptBlock {
    & $nssmExe set $ServiceName AppDirectory $InstallPath
}
Run-Native -What "nssm set Description" -ScriptBlock {
    & $nssmExe set $ServiceName Description "Hydra Admin Agent (PC management / web terminal)"
}
Run-Native -What "nssm set Start" -ScriptBlock {
    & $nssmExe set $ServiceName Start SERVICE_AUTO_START
}
Run-Native -What "nssm set AppStdout" -ScriptBlock {
    & $nssmExe set $ServiceName AppStdout $agentLog
}
Run-Native -What "nssm set AppStderr" -ScriptBlock {
    & $nssmExe set $ServiceName AppStderr $agentLog
}
Run-Native -What "nssm set AppRotateFiles" -ScriptBlock {
    & $nssmExe set $ServiceName AppRotateFiles 1
}
Run-Native -What "nssm set AppRotateBytes" -ScriptBlock {
    & $nssmExe set $ServiceName AppRotateBytes 10485760
}
Run-Native -What "nssm set AppExit" -ScriptBlock {
    & $nssmExe set $ServiceName AppExit Default Restart
}
Run-Native -What "nssm set AppRestartDelay" -ScriptBlock {
    & $nssmExe set $ServiceName AppRestartDelay 5000
}

# Codex review fix: SERVER_URL → HYDRA_SERVER_URL (worker.config 가 읽는 이름).
# desktop 의 secrets.enc 의 SERVER_URL 우연 의존 X — admin_agent 단독 env.
$envBlock = @(
    "HYDRA_SERVER_URL=$ServerUrl",
    "HYDRA_PROCESS_ROLE=admin_agent",
    "HYDRA_AGENT_WORKER_TOKEN=$($agentResp.worker_token)",
    "DB_CRYPTO_KEY=$($agentResp.secrets.DB_CRYPTO_KEY)",
    "HYDRA_DISABLE_TASK_REGISTER=1",
    "HYDRA_UPDATE_OWNER=agent",
    "PYTHONIOENCODING=utf-8"
)
$envArgs = @('set', $ServiceName, 'AppEnvironmentExtra') + $envBlock
Run-Native -What "nssm AppEnvironmentExtra" -ScriptBlock {
    & $nssmExe @envArgs
}

# 시작
Run-Native -What "nssm start $ServiceName" -ScriptBlock {
    & $nssmExe start $ServiceName
}
Start-Sleep -Seconds 3
$svcAfter = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svcAfter -or $svcAfter.Status -ne 'Running') {
    Write-Warning "$ServiceName 시작 실패. nssm dump $ServiceName 또는 $agentLog 확인."
}

# ─── Desktop Task 시작 ───────────────────────────────────────────────────
Write-Host "[start] Desktop Task..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

# ─── Done ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== HYDRA install complete ===" -ForegroundColor Green
Write-Host "  desktop_worker (Task Scheduler $TaskName):  worker_id=$($desktopResp.worker_id)"
Write-Host "  admin_agent    (NSSM $ServiceName):         worker_id=$($agentResp.worker_id)"
Write-Host "  repo HEAD:                                  $repoHead"
Write-Host "  installer version:                          $SCRIPT_VERSION"
Write-Host ""
Write-Host "확인:"
Write-Host "  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "  Get-Service -Name $ServiceName"
Write-Host "  Get-Content $logDir\admin-agent.log -Tail 30"
