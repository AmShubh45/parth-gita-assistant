@echo off
REM Gita Sarathi Live autopilot: runs the stream and restarts it if it ever stops.
REM Used by the Task Scheduler task that install_autopilot.ps1 creates (or double-click it).
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
:loop
echo [%date% %time%] starting Gita Sarathi Live >> logs\autopilot.log 2>nul
python run_live.py
echo [%date% %time%] stopped (code %errorlevel%), restarting in 15 s >> logs\autopilot.log 2>nul
timeout /t 15 /nobreak >nul
goto loop
