@echo off
setlocal
set SCRIPT_DIR=%~dp0
set VENV_PY=%SCRIPT_DIR%\.venv\Scripts\python.exe
if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT_DIR%downloader.py" --interactive
) else (
  py -3 "%SCRIPT_DIR%downloader.py" --interactive || python "%SCRIPT_DIR%downloader.py" --interactive
)

echo.
pause