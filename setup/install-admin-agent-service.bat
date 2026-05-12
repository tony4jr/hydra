@echo off
REM Hydra Admin Agent service installer wrapper — Slice 2.3.
REM 일반 cmd 에서 더블클릭 / 우클릭 실행해도 PowerShell 관리자 권한으로 승격.
REM 사용 예: install-admin-agent-service.bat -ServerUrl ... -AgentWorkerToken ... -Start
setlocal
set "PS1=%~dp0install-admin-agent-service.ps1"
if not exist "%PS1%" (
  echo [ERROR] install-admin-agent-service.ps1 not found next to this .bat
  exit /b 2
)
REM PowerShell 으로 관리자 권한 실행 (UAC 프롬프트). 인자는 그대로 전달.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%PS1%',%*"
endlocal
