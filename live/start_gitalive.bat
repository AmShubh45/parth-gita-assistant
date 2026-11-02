@echo off
REM Streams Gita Sarathi Live to YouTube from this PC (vertical, no OBS needed) and restarts it if it stops.
REM Put the stream key in .env first, and install ffmpeg once:  winget install Gyan.FFmpeg
REM Close this window to stop streaming. The Task Scheduler task from install_autopilot.ps1 runs this file.
title Gita Sarathi Live - streaming
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
if not exist logs mkdir logs
:loop
echo [%date% %time%] starting Gita Sarathi Live >> logs\autopilot.log
python run_live.py
echo.
echo Stream stopped. Restarting in 10 seconds... (close this window to stop for good)
echo [%date% %time%] stopped (code %errorlevel%), restarting >> logs\autopilot.log
timeout /t 10 /nobreak >nul
goto loop
