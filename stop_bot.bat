@echo off
chcp 65001 >nul
title Botni To'xtatish

echo ==============================================
echo    Khurshid Media Bot to'xtatilmoqda...
echo ==============================================

taskkill /f /fi "WINDOWTITLE eq Khurshid Media Bot*" >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo.
echo [OK] Bot to'xtatildi!
timeout /t 3 >nul
