<#
.SYNOPSIS
  Hydra Admin Agent Windows Service installer (NSSM-based) — Slice 2.3.

.DESCRIPTION
  Installs / manages the Hydra Admin Agent as a Windows Service via NSSM.
  Admin Agent = PC management/PowerShell channel. Desktop worker (browser
  automation) is a separate process — NOT touched here.

  Slice 2.3 scope: installer only. The Desktop Worker launcher (2.4),
  Task Scheduler cutover (2.5), and update ownership are out of scope.

.PARAMETER Action
  install (default), start, stop, restart, status, uninstall.

.PARAMETER ServerUrl
  Hydra server URL (e.g. https://hydra-prod.duckdns.org). Required for install
  unless captured from an existing service config.

.PARAMETER InstallPath
  Hydra repo root on this PC. Default C:\hydra.

.PARAMETER ServiceName
  Windows Service name. Default HydraAdminAgent.

.PARAMETER AgentWorkerToken
  Existing admin_agent worker token. Either this or -EnrollmentToken is
  required for install. Token value is never written to stdout/log.

.PARAMETER EnrollmentToken
  One-time enrollment token. If supplied (and -AgentWorkerToken empty),
  installer calls POST /api/workers/enroll to obtain a worker_token. First
  heartbeat from the agent will mark the row role=admin_agent.

.PARAMETER NssmPath
  Explicit NSSM executable path. Resolution order if absent:
    1) Get-Command nssm.exe
    2) C:\ProgramData\chocolatey\bin\nssm.exe
    3) choco install -y nssm --no-progress (if choco present)
  Hard error if all fail.

.PARAMETER Start
  Switch — start the service immediately after install.

.PARAMETER Force
  Switch — allow re-configuring an existing service of the same name
  (stops + reconfigures; does not uninstall).

.PARAMETER DryRun
  Switch — print intended commands without executing.

.EXAMPLE
  # Existing token install + start
  .\install-admin-agent-service.ps1 -ServerUrl https://hydra-prod.duckdns.org `
    -AgentWorkerToken <token> -Start

.EXAMPLE
  # Enrollment token install + start
  .\install-admin-agent-service.ps1 -ServerUrl https://hydra-prod.duckdns.org `
    -EnrollmentToken <enrollment> -Start

.EXAMPLE
  .\install-admin-agent-service.ps1 -Action status

.EXAMPLE
  .\install-admin-agent-service.ps1 -Action uninstall

.NOTES
  Requires Administrator. NSSM bundled or installable via Chocolatey.
  Slice 2.3 does NOT touch existing HydraWorker Task Scheduler / Desktop
  Worker / update ownership. Those are 2.4/2.5.
#>
[CmdletBinding()]
param(
  [ValidateSet('install','start','stop','restart','status','uninstall')]
  [string]$Action = 'install',

  [string]$ServerUrl = '',
  [string]$InstallPath = 'C:\hydra',
  [string]$ServiceName = 'HydraAdminAgent',
  [string]$AgentWorkerToken = '',
  [string]$EnrollmentToken = '',
  [string]$NssmPath = '',
  [switch]$Start,
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# ── helpers ───────────────────────────────────────────────────────────────

function Write-Info([string]$msg) { Write-Host "[admin-agent-installer] $msg" }
function Write-Warn([string]$msg) { Write-Warning "[admin-agent-installer] $msg" }
function Write-Err ([string]$msg) { Write-Error "[admin-agent-installer] $msg" }

function Assert-Admin {
  $current = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator 권한 필요. PowerShell 을 관리자 권한으로 실행하세요."
  }
}

function Resolve-Nssm {
  param([string]$Explicit)
  if ($Explicit -and (Test-Path $Explicit)) { return $Explicit }
  $cmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $choco = 'C:\ProgramData\chocolatey\bin\nssm.exe'
  if (Test-Path $choco) { return $choco }
  # 마지막 시도 — choco 가 있으면 자동 설치
  $chocoCmd = Get-Command choco.exe -ErrorAction SilentlyContinue
  if ($chocoCmd) {
    Write-Info "nssm 미발견. choco install -y nssm 시도..."
    if (-not $DryRun) {
      & $chocoCmd.Source install -y nssm --no-progress | Out-Host
    }
    if (Test-Path $choco) { return $choco }
  }
  throw "NSSM 을 찾지 못함. -NssmPath 명시하거나 Chocolatey 설치 후 다시 시도."
}

function Invoke-NssmCmd {
  param(
    [string]$Nssm,
    [string[]]$Args
  )
  $argText = ($Args -join ' ')
  if ($DryRun) {
    Write-Info "DRYRUN: $Nssm $argText"
    return 0
  }
  Write-Info "nssm $argText"
  & $Nssm @Args
  return $LASTEXITCODE
}

function Get-AgentWorkerTokenViaEnrollment {
  param([string]$ServerUrl, [string]$EnrollmentToken)
  if (-not $ServerUrl) { throw "ServerUrl 필요 (enrollment)." }
  if (-not $EnrollmentToken) { throw "EnrollmentToken 비어있음." }
  $endpoint = "$($ServerUrl.TrimEnd('/'))/api/workers/enroll"
  Write-Info "Enrollment POST → $endpoint (token len=$($EnrollmentToken.Length))"
  if ($DryRun) {
    Write-Info "DRYRUN: enrollment skipped"
    return 'DRYRUN-AGENT-TOKEN'
  }
  # role 은 첫 heartbeat 에서 admin_agent 로 자동 갱신됨. Slice 2.3 은 server API 안 건드림.
  $body = @{ enrollment_token = $EnrollmentToken } | ConvertTo-Json -Compress
  try {
    $resp = Invoke-RestMethod -Method Post -Uri $endpoint -Body $body `
      -ContentType 'application/json' -TimeoutSec 30
  } catch {
    throw "Enrollment 실패: $($_.Exception.Message)"
  }
  if (-not $resp.worker_token) {
    throw "Enrollment 응답에 worker_token 없음."
  }
  Write-Info "Enrollment OK (worker_token len=$($resp.worker_token.Length))"
  return $resp.worker_token
}

function Get-ServiceExists {
  param([string]$Name)
  return [bool](Get-Service -Name $Name -ErrorAction SilentlyContinue)
}

# ── actions ───────────────────────────────────────────────────────────────

function Do-Install {
  Assert-Admin

  if (-not (Test-Path $InstallPath)) {
    throw "InstallPath 미존재: $InstallPath"
  }
  $python = Join-Path $InstallPath '.venv\Scripts\python.exe'
  if (-not (Test-Path $python)) {
    throw "venv python 미발견: $python — Hydra worker 가 설치되지 않은 PC."
  }

  # token 정책: AgentWorkerToken 또는 EnrollmentToken 필요. 원문은 절대 출력 X.
  $token = ''
  if ($AgentWorkerToken) {
    $token = $AgentWorkerToken
    Write-Info "AgentWorkerToken 사용 (len=$($token.Length))"
  } elseif ($EnrollmentToken) {
    $token = Get-AgentWorkerTokenViaEnrollment -ServerUrl $ServerUrl -EnrollmentToken $EnrollmentToken
  } else {
    throw "AgentWorkerToken 또는 EnrollmentToken 필요."
  }
  if (-not $ServerUrl) { throw "ServerUrl 필요." }

  $nssm = Resolve-Nssm -Explicit $NssmPath
  Write-Info "NSSM: $nssm"

  $exists = Get-ServiceExists -Name $ServiceName
  if ($exists -and -not $Force) {
    throw "서비스 '$ServiceName' 이미 존재. -Force 로 재설정 또는 -Action uninstall 후 재설치."
  }
  if ($exists -and $Force) {
    Write-Info "기존 서비스 '$ServiceName' stop + 재설정 (Force)."
    Invoke-NssmCmd -Nssm $nssm -Args @('stop', $ServiceName) | Out-Null
  }

  # 로그 디렉토리 보장
  $logsDir = Join-Path $InstallPath 'logs'
  if (-not (Test-Path $logsDir)) {
    if (-not $DryRun) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
    Write-Info "logs dir 생성: $logsDir"
  }
  $stdoutLog = Join-Path $logsDir 'admin-agent-service.out.log'
  $stderrLog = Join-Path $logsDir 'admin-agent-service.err.log'

  if (-not $exists) {
    # nssm install <ServiceName> <python.exe> <args>
    $rc = Invoke-NssmCmd -Nssm $nssm -Args @('install', $ServiceName, $python, '-m', 'worker.admin_agent')
    if ($rc -ne 0) { throw "nssm install 실패 (exit=$rc)" }
  } else {
    # 이미 존재 + Force: AppPath / AppParameters 만 재설정
    Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'Application', $python) | Out-Null
    Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppParameters', '-m worker.admin_agent') | Out-Null
  }

  # 공통 service config
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppDirectory', $InstallPath) | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'Start', 'SERVICE_AUTO_START') | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'ObjectName', 'LocalSystem') | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'DisplayName', 'Hydra Admin Agent') | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'Description', 'Hydra Admin Agent — remote PC management channel.') | Out-Null

  # 환경 변수: AppEnvironmentExtra. NSSM 는 줄바꿈으로 여러 entry 받음.
  # 토큰 원문은 절대 stdout 에 출력하지 않음 (Invoke-NssmCmd 의 args 만 nssm 에 직접 전달).
  $envLines = @(
    "HYDRA_SERVER_URL=$ServerUrl",
    "HYDRA_AGENT_WORKER_TOKEN=$token",
    "HYDRA_DISABLE_TASK_REGISTER=1",
    "HYDRA_UPDATE_OWNER=agent"
  )
  $envBlob = ($envLines -join "`r`n")
  if ($DryRun) {
    Write-Info "DRYRUN: nssm set $ServiceName AppEnvironmentExtra <env block: 4 entries>"
  } else {
    Write-Info "nssm set $ServiceName AppEnvironmentExtra (4 entries; token redacted)"
    & $nssm set $ServiceName AppEnvironmentExtra $envBlob | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "AppEnvironmentExtra 설정 실패" }
  }

  # 로그 + rotation
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppStdout', $stdoutLog) | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppStderr', $stderrLog) | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppRotateFiles', '1') | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppRotateBytes', '10485760') | Out-Null  # 10MB
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppStdoutCreationDisposition', '4') | Out-Null  # OPEN_ALWAYS

  # restart policy
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppRestartDelay', '5000') | Out-Null  # 5s
  Invoke-NssmCmd -Nssm $nssm -Args @('set', $ServiceName, 'AppExit', 'Default', 'Restart') | Out-Null

  Write-Info "Service '$ServiceName' 설치 완료."

  if ($Start) {
    Do-Start
  } else {
    Write-Info "서비스 시작은 -Start 또는 '-Action start' 로 직접."
  }
}

function Do-Start {
  Assert-Admin
  $nssm = Resolve-Nssm -Explicit $NssmPath
  Invoke-NssmCmd -Nssm $nssm -Args @('start', $ServiceName) | Out-Null
  Write-Info "Service '$ServiceName' start 요청."
}

function Do-Stop {
  Assert-Admin
  $nssm = Resolve-Nssm -Explicit $NssmPath
  Invoke-NssmCmd -Nssm $nssm -Args @('stop', $ServiceName) | Out-Null
  Write-Info "Service '$ServiceName' stop 요청."
}

function Do-Restart {
  Assert-Admin
  $nssm = Resolve-Nssm -Explicit $NssmPath
  Invoke-NssmCmd -Nssm $nssm -Args @('restart', $ServiceName) | Out-Null
  Write-Info "Service '$ServiceName' restart 요청."
}

function Do-Status {
  $nssm = Resolve-Nssm -Explicit $NssmPath
  if (-not (Get-ServiceExists -Name $ServiceName)) {
    Write-Info "Service '$ServiceName' 미설치."
    return
  }
  $svc = Get-Service -Name $ServiceName
  Write-Info "Service: $($svc.Name) Status=$($svc.Status) StartType=$($svc.StartType)"
  # nssm status / dump (token 절대 출력 X — AppEnvironmentExtra 는 표시 안 함)
  & $nssm status $ServiceName | Out-Host
  Write-Info "Config (token redacted):"
  & $nssm get $ServiceName Application | Out-Host
  & $nssm get $ServiceName AppParameters | Out-Host
  & $nssm get $ServiceName AppDirectory | Out-Host
  & $nssm get $ServiceName Start | Out-Host
  & $nssm get $ServiceName ObjectName | Out-Host
  & $nssm get $ServiceName AppStdout | Out-Host
  & $nssm get $ServiceName AppStderr | Out-Host
  Write-Info "AppEnvironmentExtra 는 보안상 출력하지 않음. nssm edit GUI 또는 logs 확인."
}

function Do-Uninstall {
  Assert-Admin
  $nssm = Resolve-Nssm -Explicit $NssmPath
  if (-not (Get-ServiceExists -Name $ServiceName)) {
    Write-Info "Service '$ServiceName' 미존재 — uninstall no-op."
    return
  }
  Invoke-NssmCmd -Nssm $nssm -Args @('stop', $ServiceName) | Out-Null
  Invoke-NssmCmd -Nssm $nssm -Args @('remove', $ServiceName, 'confirm') | Out-Null
  Write-Info "Service '$ServiceName' uninstall 완료. repo/venv/secrets 는 그대로 유지."
}

# ── dispatch ──────────────────────────────────────────────────────────────

switch ($Action) {
  'install'   { Do-Install   }
  'start'     { Do-Start     }
  'stop'      { Do-Stop      }
  'restart'   { Do-Restart   }
  'status'    { Do-Status    }
  'uninstall' { Do-Uninstall }
  default     { throw "알 수 없는 Action: $Action" }
}
