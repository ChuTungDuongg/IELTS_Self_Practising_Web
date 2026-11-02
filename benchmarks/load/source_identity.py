"""Record exact application bytes independently of a dirty worktree's HEAD label."""

import hashlib
import subprocess
from pathlib import Path


def source_identity(backend: Path) -> dict:
    digest = hashlib.sha256()
    for source in sorted((backend / "app").rglob("*.py")):
        digest.update(source.relative_to(backend).as_posix().encode())
        digest.update(b"\x00")
        digest.update(source.read_bytes())
        digest.update(b"\x00")
    result = {"app_source_sha256": digest.hexdigest()}
    try:
        result["git_head"] = subprocess.run(
            ["git", "-C", str(backend), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        diff = subprocess.run(
            [
                "git",
                "-C",
                str(backend),
                "diff",
                "HEAD",
                "--",
                "app",
                "alembic",
                "pyproject.toml",
                "uv.lock",
            ],
            check=True,
            capture_output=True,
        ).stdout
        result["tracked_diff_sha256"] = hashlib.sha256(diff).hexdigest()
    except (OSError, subprocess.CalledProcessError):
        result["git_head"] = None
        result["tracked_diff_sha256"] = None
    return result
