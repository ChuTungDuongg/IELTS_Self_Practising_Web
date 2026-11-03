@echo off
setlocal
cd /d "%~dp0"
set "UV=uv"
where uv >nul 2>nul
if errorlevel 1 set "UV=%USERPROFILE%\.local\bin\uv.exe"
"%UV%" run --locked --project backend python scripts\modal_start.py %*
exit /b %errorlevel%
