#!/usr/bin/env bash
# Casewright v1.0.0 — Linux / Windows (Git Bash or WSL) launcher
# Author: Mo Shehu — mohammedshehu.com
cd "$(dirname "$0")" || exit 1

# ── Python check ──────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null && "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Python 3.9 or later not found. Install it from https://www.python.org and try again."
  read -rp "Press Enter to close..."
  exit 1
fi

# ── Virtual environment (created only if absent) ───────────────────────────────
if [ ! -d ".venv" ]; then
  echo "First run: creating virtual environment..."
  "$PYTHON" -m venv .venv
fi

# Activate — path differs between Unix and Windows (Git Bash)
if [ -f ".venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# ── Dependencies ───────────────────────────────────────────────────────────────
echo "Checking dependencies..."
pip install -q -r requirements.txt

# ── Find a free port starting at 5050 (portable: uses Python) ─────────────────
PORT=5050
until "$PYTHON" -c "
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('', int(sys.argv[1])))
s.close()
" "$PORT" 2>/dev/null; do
  PORT=$((PORT + 1))
done

# ── Open browser once the server is up ────────────────────────────────────────
(sleep 2 && {
  if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "http://localhost:$PORT" 2>/dev/null
  elif [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* || "$OSTYPE" == "win32"* ]]; then
    start "http://localhost:$PORT"
  else
    "$PYTHON" -m webbrowser "http://localhost:$PORT"
  fi
}) &

# ── Launch ─────────────────────────────────────────────────────────────────────
echo ""
echo "Casewright running at http://localhost:$PORT"
echo "Press Ctrl-C to stop."
echo ""
export PORT
"$PYTHON" app.py
