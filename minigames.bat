@echo off
chcp 65001 >nul
REM ============================================================
REM  minigames.bat - 파이썬/PyQt5를 자동으로 확인해서 시선 미니게임만 실행
REM  (카메라용 프로그램 cv2, mediapipe는 필요 없어요)
REM  이 파일과 minigames.py를 같은 폴더에 두고 더블클릭하세요.
REM  옵션을 붙이면 그대로 전달됩니다. 예: minigames.bat --windowed
REM ============================================================
cd /d "%~dp0"

if not exist "minigames.py" (
    echo [오류] minigames.py 가 이 파일과 같은 폴더에 없어요.
    pause
    exit /b 1
)

REM ---- 1) 파이썬 찾기 (3.8 이상이면 됨) ----
set "PY="
call :try python
if not defined PY call :try py -3.11
if not defined PY call :try py -3.12
if not defined PY call :try py -3.10
if not defined PY call :try py -3
if not defined PY (
    echo [설치] 파이썬이 없어서 Python 3.11을 설치합니다...
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

REM ---- 2) PyQt5 확인, 없으면 설치 (처음 한 번만) ----
%PY% -c "import PyQt5.QtWidgets" >nul 2>&1
if errorlevel 1 (
    echo [설치] 화면 라이브러리 PyQt5를 설치합니다. 처음 한 번만이에요...
    %PY% -m pip install PyQt5
    %PY% -c "import PyQt5.QtWidgets" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [오류] PyQt5 설치에 실패했어요. 인터넷 연결을 확인하고 다시 실행해 주세요.
        pause
        exit /b 1
    )
)

REM ---- 3) 실행 - 에러로 꺼지면 창을 닫지 않고 메시지를 보여줌 ----
%PY% minigames.py %*
if errorlevel 1 pause
exit /b

:try
%* -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 8) else 1)" >nul 2>&1 && set "PY=%*"
exit /b

:no_winget
echo.
echo [안내] 자동 설치 도구 winget이 없어요. 아래 주소에서 Python 3.11을 직접 설치해 주세요.
echo        설치 첫 화면에서 Add python.exe to PATH 를 꼭 체크하세요.
start "" https://www.python.org/downloads/release/python-3119/
pause
exit /b 1
