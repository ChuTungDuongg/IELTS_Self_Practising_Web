"""Run from the repository with: cd backend && uv run python ../scripts/restore.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.backup_restore import restore_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(restore_main())
