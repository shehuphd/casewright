"""
Remove all generated workup files from outputs/workups/.
Run with: python reset_outputs.py
Data in data/cases.json is not affected.
"""
import shutil
from pathlib import Path

workups_dir = Path(__file__).parent / "outputs" / "workups"
count = 0
for f in workups_dir.glob("*.json"):
    f.unlink()
    count += 1

print(f"Cleared {count} workup file(s) from {workups_dir}")
