@echo off
:: Casewright v1.0.0 — Windows launcher (double-click in Explorer)
:: Author: Mo Shehu — mohammedshehu.com
cd /d "%~dp0"

:: ── Python check ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install it from https://www.python.org and try again.
    pause
    exit /b 1
)

:: ── Virtual environment (created only if absent) ───────────────────────────────
if not exist ".venv\" (
    echo First run: creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

:: ── Dependencies ───────────────────────────────────────────────────────────────
echo Checking dependencies...
pip install -q -r requirements.txt

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
