@echo off
chcp 65001 >nul
REM 바탕화면에 예쁜 이름과 아이콘의 바로가기를 만듭니다. 더블클릭하세요.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcuts.ps1"
echo.
echo 이 폴더에 바로가기가 생겼어요. 바로가기는 지우고 다시 만들어도 괜찮아요.
pause
