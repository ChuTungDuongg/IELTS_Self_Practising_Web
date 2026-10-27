"""Small real console tests; no frontend, backend server or database is started."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/dev_backend.py"
spec = importlib.util.spec_from_file_location("dev_backend", SCRIPT)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console regression")
def test_reload_ctrl_c_stays_in_child_console(capsys):
    # Verify isolation before generating a signal: a broken launcher must fail
    # safely rather than broadcast Ctrl+C into pytest/the invoking terminal.
    code = """
import ctypes, json, os, signal, sys, time
pids = (ctypes.c_ulong * 128)()
count = ctypes.windll.kernel32.GetConsoleProcessList(pids, len(pids))
assert count > 0 and count <= len(pids)
assert int(sys.argv[1]) not in pids[:count], 'Parent console was inherited'
seen = []
signal.signal(signal.SIGINT, lambda *_: seen.append(True))
os.kill(0, signal.CTRL_C_EVENT)
deadline = time.monotonic() + 5
while not seen and time.monotonic() < deadline:
    time.sleep(0.01)
assert seen, 'Private-console reload signal was not received'
print(json.dumps({'signal_received': True, 'parent_isolated': True}))
"""
    assert launcher.run_windows([sys.executable, "-c", code, str(os.getpid())]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "signal_received": True,
        "parent_isolated": True,
    }


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console regression")
def test_backend_failure_keeps_its_output_and_exit_status(capsys):
    assert (
        launcher.run_windows(
            [sys.executable, "-c", "import sys; print('fictional startup error'); sys.exit(7)"]
        )
        == 7
    )
    assert "fictional startup error" in capsys.readouterr().out
