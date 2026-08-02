#!/usr/bin/env bash
# Casewright v1.1.0 — Linux / Windows (Git Bash or WSL) launcher
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

# ── Virtual environment (validated, not just checked for existence) ────────────
venv_python() {
  # Unix layout vs. Windows (Git Bash) layout — try both.
  if [ -x ".venv/bin/python" ]; then echo ".venv/bin/python";
  elif [ -x ".venv/Scripts/python.exe" ]; then echo ".venv/Scripts/python.exe";
  else echo ""; fi
}

venv_is_broken() {
  # A venv only counts as valid if its own python actually runs. Catches a
  # stale interpreter path left over from a different machine or account —
  # e.g. a venv synced via Dropbox from a machine with a different Python
  # install — or a build that got interrupted before completion.
  local vp; vp="$(venv_python)"
  [ -z "$vp" ] || ! "$vp" --version &>/dev/null
}

if [ -d ".venv" ] && venv_is_broken; then
  echo "Existing virtual environment is broken (stale interpreter path). Rebuilding..."
  rm -rf .venv
fi

if [ ! -d ".venv" ]; then
  echo "First run: creating virtual environment..."
  "$PYTHON" -m venv .venv
  # ensurepip explicitly, since venv creation can silently skip bundling pip
  "$(venv_python)" -m ensurepip --upgrade &>/dev/null
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
# Routed through $PYTHON explicitly rather than a bare `pip` on PATH: after
# activation `pip` almost always resolves correctly, but a shell with a
# shadowing pip earlier in PATH (pyenv shims, a corporate image, a personal
# alias) would silently install into the wrong environment. -m pip ties the
# install to the exact interpreter this script already resolved.
"$PYTHON" -m pip install -q -r requirements.txt

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
