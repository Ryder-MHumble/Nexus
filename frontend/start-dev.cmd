@echo off
setlocal enabledelayedexpansion
set "PORT=43819"
set "NEXT_PUBLIC_API_BASE_URL=http://localhost:43817/api/v1"
cd /d "%~dp0"
npm run dev -- --port %PORT%
