@echo off
title DVM Tool
cd /d "%~dp0"
echo Starting DVM Tool...
echo (The first launch may take a few seconds.)
echo.
"%~dp0python\python.exe" "%~dp0launcher.py"
echo.
echo The tool has stopped. You can close this window.
pause
