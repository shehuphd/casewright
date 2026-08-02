@echo off
:: Casewright v1.0.1 — Windows launcher (double-click in Explorer)
:: Author: Mo Shehu — mohammedshehu.com
cd /d "%~dp0"

:: ── Python check ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install it from https://www.python.org and try again.
    pause
    exit /b 1
)

:: ── Virtual environment (validated, not just checked for existence) ────────────
:: A venv only counts as valid if its own python actually runs. Catches a
:: stale interpreter path left over from a different machine, a venv folder
:: copied/synced from elsewhere, or a build interrupted before completion.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if errorlevel 1 (
        echo Existing virtual environment is broken. Rebuilding...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\" (
    echo First run: creating virtual environment...
    python -m venv .venv
    :: ensurepip explicitly, since venv creation can silently skip bundling pip
    ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
)

call .venv\Scripts\activate.bat

:: ── Dependencies ───────────────────────────────────────────────────────────────
echo Checking dependencies...
:: Routed through -m pip rather than a bare `pip` on PATH: after activation
:: `pip` almost always resolves correctly, but any shell/PATH oddity that
:: shadows it would silently install into the wrong environment. -m pip ties
:: the install to the exact interpreter this script is using.
python -m pip install -q -r requirements.txt

:: ── Find a free port starting at 5050 ─────────────────────────────────────────
(
    echo import socket
    echo p = 5050
    echo while True:
    echo     try:
    echo         s = socket.socket^(^)
    echo         s.setsockopt^(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1^)
    echo         s.bind^(^('', p^)^)
    echo         s.close^(^)
    echo         print^(p^)
    echo         break
    echo     except OSError:
    echo         p += 1
) > "%TEMP%\cw_find_port.py"
python "%TEMP%\cw_find_port.py" > "%TEMP%\cw_port.txt"
set /p PORT=< "%TEMP%\cw_port.txt"
del "%TEMP%\cw_find_port.py" "%TEMP%\cw_port.txt"

:: ── Open browser once the server is up ────────────────────────────────────────
start "" /b cmd /c "timeout /t 2 >nul && start http://localhost:%PORT%"

:: ── Launch ─────────────────────────────────────────────────────────────────────
echo.
echo Casewright running at http://localhost:%PORT%
echo Press Ctrl-C to stop.
echo.
python app.py
