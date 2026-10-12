@echo off
REM Gaze tracker - ignore saved calibration and redo the mole calibration
call "%~dp0run.bat" --recalibrate
