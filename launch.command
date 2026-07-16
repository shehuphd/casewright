#!/bin/bash
# Casewright v1.0.0 — macOS launcher (double-click in Finder)
# Author: Mo Shehu — mohammedshehu.com
cd "$(dirname "$0")"

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "Python 3 not found. Install it from https://www.python.org and try again."
  read -rp "Press Enter to close..."
  exit 1
fi

# ── Virtual environment (created only if absent) ───────────────────────────────
if [ ! -d ".venv" ]; then
  echo "First run: creating virtual environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ── Dependencies ───────────────────────────────────────────────────────────────
echo "Checking dependencies..."
pip install -q -r requirements.txt

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
python app.py
