@echo off
:loop
echo [BOT] Starting...
python RBR_Bot.py
if exist shutdown.flag (
    echo [BOT] Shutdown flag detected. Exiting loop.
    del shutdown.flag
    exit /b
)
echo [BOT] Restarting in 5 seconds...
timeout /t 5 >nul
goto loop
