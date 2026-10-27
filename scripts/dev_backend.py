"""Keep Windows Uvicorn reload signals out of the frontend's console."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def backend_command() -> list[str]:
    return [sys.executable, "-m", "fastapi", "dev", "app/main.py", "--reload-dir", "app"]


def stop_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        # Only the child created by this launcher and its own reload workers.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        process.wait(timeout=10)


def run_windows(command: list[str]) -> int:
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    # A process group alone does not isolate CTRL_C_EVENT. Uvicorn must have
    # its own console; pipes keep its logs in the existing npm terminal.
    process = subprocess.Popen(
        command,
        cwd=BACKEND,
        env=environment,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        startupinfo=startup,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    try:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
        return process.wait()
    except KeyboardInterrupt:
        stop_tree(process)
        return 130
    finally:
        stop_tree(process)
        if process.stdout is not None:
            process.stdout.close()


def main() -> int:
    command = backend_command()
    if sys.platform == "win32":
        return run_windows(command)
    os.chdir(BACKEND)
    os.execv(sys.executable, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
