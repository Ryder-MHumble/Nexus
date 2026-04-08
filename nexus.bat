@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0nexus.ps1" %*
exit /b %ERRORLEVEL%
