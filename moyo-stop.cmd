@echo off
rem Stop the Moyo background server.
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if ($c) { $c | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }; 'Moyo stopped.' } else { 'Moyo was not running.' }"
timeout /t 2 >nul
