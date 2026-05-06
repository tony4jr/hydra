@echo off
REM HYDRA Worker - one-click installer launcher
REM
REM Double-click this .bat:
REM   1. Auto-elevates to admin (UAC popup)
REM   2. Asks for enrollment token via GUI dialog
REM   3. Runs setup.ps1 (installs Python, Git, Playwright, registers Task Scheduler)
REM
REM ASCII-only inside this file - Korean prompts live in the PowerShell InputBox
REM (which uses Unicode and is encoding-safe).

setlocal enableextensions

REM --- 1. admin elevation ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cls
echo.
echo  ============================================================
echo                   HYDRA Worker Setup
echo  ============================================================
echo.
echo   Get an enrollment token from the admin UI first:
echo     https://hydra-prod.duckdns.org/workers
echo     ^> + Worker Add ^> issue token (valid 24h)
echo.
echo  ============================================================
echo.

REM --- 2. token via PowerShell InputBox (Unicode-safe) ---
for /f "delims=" %%T in ('powershell -NoProfile -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::InputBox('어드민에서 발급받은 enrollment token 을 붙여넣으세요 (eyJ... 로 시작)', 'HYDRA Worker - Token', '')"') do set TOKEN=%%T

if "%TOKEN%"=="" (
    echo.
    echo [HYDRA] No token entered. Aborted.
    pause
    exit /b 1
)

set SERVER_URL=https://hydra-prod.duckdns.org

echo.
echo [HYDRA] Token received. Starting installation (10-20 min)...
echo         ServerUrl: %SERVER_URL%
echo.

REM --- 3. download + run setup.ps1 ---
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr -Uri '%SERVER_URL%/api/workers/setup.ps1' -OutFile $env:TEMP\hydra-setup.ps1; & $env:TEMP\hydra-setup.ps1 -Token '%TOKEN%' -ServerUrl '%SERVER_URL%'"

set RC=%errorlevel%
echo.
if %RC% equ 0 (
    echo  ============================================================
    echo   Install OK. Check the admin worker page - LED should be green.
    echo  ============================================================
) else (
    echo  ============================================================
    echo   Install failed (exit %RC%). See output above.
    echo  ============================================================
)
echo.
pause
