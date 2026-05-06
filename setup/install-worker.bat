@echo off
REM HYDRA Worker - 더블클릭 설치 런처
REM
REM 사용자가 .bat 파일을 더블클릭하면:
REM   1. 관리자 권한 자동 요청 (UAC 팝업)
REM   2. enrollment 토큰 입력창
REM   3. PowerShell setup.ps1 한 번에 실행
REM
REM 어드민 UI 의 "워커 추가" 에서 발급받은 enrollment_token 만 있으면 됨.
REM 인터넷 연결, 디스크 5GB+, Windows 10/11 필요.

setlocal

REM ── 1. 관리자 권한 체크 / 자동 승격 ──
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [HYDRA] 관리자 권한이 필요합니다. UAC 팝업이 나타나면 "예" 를 누르세요.
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

REM ── 2. 안내 ──
cls
echo.
echo  ============================================================
echo                   HYDRA Worker Setup
echo  ============================================================
echo.
echo   먼저 어드민 페이지에서 "워커 추가" 로 enrollment token 을
echo   발급받아 두세요.
echo.
echo   - 어드민: https://hydra-prod.duckdns.org/workers
echo   - 토큰은 24시간 유효
echo.
echo  ============================================================
echo.

REM ── 3. 토큰 입력 (PowerShell GUI Read-Host) ──
for /f "delims=" %%T in ('powershell -NoProfile -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::InputBox('어드민에서 발급받은 enrollment token 을 붙여넣으세요 (eyJ... 로 시작)', 'HYDRA Worker - Token', '')"') do set TOKEN=%%T

if "%TOKEN%"=="" (
    echo.
    echo [HYDRA] 토큰이 비어있어 설치를 취소합니다.
    pause
    exit /b 1
)

REM ── 4. 서버 URL (기본값 prod) ──
set SERVER_URL=https://hydra-prod.duckdns.org

echo.
echo [HYDRA] 토큰 수신 완료. 설치를 시작합니다 ^(10~20분 소요^).
echo         ServerUrl: %SERVER_URL%
echo.

REM ── 5. PowerShell setup.ps1 실행 (ExecutionPolicy Bypass + setup 다운로드) ──
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "iwr -Uri '%SERVER_URL%/api/workers/setup.ps1' -OutFile $env:TEMP\hydra-setup.ps1; & $env:TEMP\hydra-setup.ps1 -Token '%TOKEN%' -ServerUrl '%SERVER_URL%'"

set RC=%errorlevel%
echo.
if %RC% equ 0 (
    echo  ============================================================
    echo   설치 성공. 어드민 워커 페이지에서 LED 가 녹색인지 확인하세요.
    echo  ============================================================
) else (
    echo  ============================================================
    echo   설치 실패 ^(코드 %RC%^). 위 로그를 확인하세요.
    echo  ============================================================
)
echo.
pause
