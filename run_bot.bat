@echo off
title Khurshid Media Bot (24/7 Auto-Restart)
cd /d "%~dp0"

:loop
echo [%date% %time%] Bot ishga tushirilmoqda...
python bot.py
echo [%date% %time%] Bot to'xtadi yoki uzildi. 3 soniyadan keyin qayta ishga tushadi...
timeout /t 3 /nobreak >nul
goto loop
