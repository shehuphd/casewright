#!/bin/bash
# Casewright v1.0.1 — macOS launcher (double-click in Finder)
# Author: Mo Shehu — mohammedshehu.com
cd "$(dirname "$0")"

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "Python 3 not found. Install it from https://www.python.org and try again."
  read -rp "Press Enter to close..."
  exit 1
fi

# ── Virtual environment (validated, not just checked for existence) ────────────
venv_is_broken() {
  # A venv only counts as valid if its own python actually runs.
  # This catches stale symlinks to another account's pyenv, a missing
  # interpreter after an incomplete build, or any other silent breakage.
  [ ! -x ".venv/bin/python" ] || ! .venv/bin/python --version &>/dev/null
}

if [ -d ".venv" ] && venv_is_broken; then
  echo "Existing virtual environment is broken (stale interpreter path). Rebuilding..."
  rm -rf .venv
fi

if [ ! -d ".venv" ]; then
  echo "First run: creating virtual environment..."
  python3 -m venv .venv
  # ensurepip explicitly, since venv creation can silently skip bundling pip
  .venv/bin/python -m ensurepip --upgrade &>/dev/null
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ── Dependencies ───────────────────────────────────────────────────────────────
echo "Checking dependencies..."
python3 -m pip install -q -r requirements.txt

# ── Find a free port starting at 5050 ─────────────────────────────────────────
PORT=5050
while lsof -i :"$PORT" &>/dev/null; do
  PORT=$((PORT + 1))
done

# ── Open browser once the server is up ────────────────────────────────────────
(sleep 2 && open "http://localhost:$PORT") &

# ── Launch ─────────────────────────────────────────────────────────────────────
echo ""
echo "Casewright running at http://localhost:$PORT"
echo "Press Ctrl-C to stop."
echo ""
export PORT
python3 app.py
