@echo off
:loop
echo [BOT] Starting...
python RBR_Bot.py
echo [BOT] Restarting in 3 seconds...
timeout /t 3 >nul
goto loop