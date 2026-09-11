@echo off
REM Arch Assistant Persistent Tunnel
REM This script runs cloudflared tunnel in a loop, automatically restarting
REM if the connection drops. Run this in background for 24/7 operation.

set CLOUDFLARED=C:\Users/trevo/tmp/cloudflared.exe
set TARGET=http://127.0.0.1:8090
set URL_FILE=C:\Users/trevo/tmp\current-tunnel-url.txt
set LOG_FILE=C:\Users/trevo/tmp\cloudflared-persistent.log

echo [%date% %time%] Starting persistent Cloudflare Tunnel... >> "%LOG_FILE%"

:loop
"%CLOUDFLARED%" tunnel --url %TARGET% --logfile "%LOG_FILE%" --loglevel info 2>&1 | findstr /C:"trycloudflare" >> "%URL_FILE%" 
echo [%date% %time%] Tunnel exited, restarting in 5 seconds... >> "%LOG_FILE%"
timeout /t 5 /nobreak >nul
goto loop
