@echo off
chcp 65001 >nul
REM ============================================================
REM  run.bat - 필요한 프로그램을 자동으로 확인/설치한 뒤 시선 추적 데모 실행
REM  직접 실행하지 말고 "시선추적_시작.bat" 또는 "시선추적_캘리브레이션_새로.bat"를 더블클릭
REM  (main.py에 넘길 옵션을 그대로 받음: --skip-calib 등)
REM ============================================================
cd /d "%~dp0"

REM ---- 1) 맞는 파이썬 찾기: mediapipe 0.10.21은 파이썬 3.9~3.12에서만 동작 ----
set "PY="
call :try python
if not defined PY call :try py -3.11
if not defined PY call :try py -3.12
if not defined PY call :try py -3.10
if not defined PY (
    echo [설치] 맞는 버전의 파이썬이 없어서 Python 3.11을 설치합니다...
    where winget >nul 2>&1
    if errorlevel 1 goto :no_winget
    winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    call :try py -3.11
)
if not defined PY (
    echo.
    echo 파이썬 설치가 끝났어요. 이 창을 닫고 방금 그 파일을 다시 더블클릭해 주세요.
    pause
    exit /b 1
)

REM ---- 2) 필요한 패키지 확인, 없으면 설치 - 처음 한 번만 몇 분 걸림 ----
%PY% -c "import mediapipe, PyQt5" >nul 2>&1
if errorlevel 1 (
    echo [설치] 필요한 패키지를 설치합니다. 처음 한 번만이고 몇 분 걸려요...
    %PY% -m pip install PyQt5 mediapipe==0.10.21
)

REM ---- 3) 설치는 됐는데 못 불러오면: 대부분 Visual C++ 런타임이 없어서 ----
%PY% -c "import mediapipe" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [안내] mediapipe를 불러오지 못했어요. 보통 Visual C++ 런타임이 없어서 그래요.
    echo        다운로드를 시작할게요. 설치하거나 이미 있으면 복구를 누른 뒤,
    echo        컴퓨터를 재부팅하고 다시 실행해 주세요.
    start "" https://aka.ms/vs/17/release/vc_redist.x64.exe
    pause
    exit /b 1
)

REM ---- 4) 실행 - 에러로 꺼지면 창을 닫지 않고 메시지를 보여줌 ----
%PY% main.py %*
if errorlevel 1 pause
exit /b

:try
%* -c "import sys; sys.exit(0 if (3, 9) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1 && set "PY=%*"
exit /b

:no_winget
echo.
echo [안내] 자동 설치 도구 winget이 없어요. 아래 주소에서 Python 3.11을 직접 설치해 주세요.
echo        설치 첫 화면에서 Add python.exe to PATH 를 꼭 체크하세요.
start "" https://www.python.org/downloads/release/python-3119/
pause
exit /b 1
