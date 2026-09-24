"""Remove ephemeral auth credentials from Playwright failure artifacts."""

import os
import re
import tempfile
from pathlib import Path
from zipfile import ZipFile

JWT = re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
COOKIE = re.compile(rb"(?i)(ielts_(?:access|refresh|oauth_state)=)[^;\s\"\\]+")
HEADER = re.compile(
    rb'(?i)("name"\s*:\s*"(?:cookie|set-cookie|authorization)"\s*,\s*"value"\s*:\s*")(?:\\.|[^"\\])*'
)
PASSWORD = os.environ["E2E_ADMIN_PASSWORD"].encode()
ROOTS = (Path("frontend/playwright-report"), Path("frontend/test-results"))
TEXT_SUFFIXES = {".html", ".json", ".md", ".txt", ".log", ".trace", ".network", ".stacks"}


def redact(data: bytes) -> bytes:
    data = data.replace(PASSWORD, b"[REDACTED]")
    data = JWT.sub(b"[REDACTED_JWT]", data)
    data = COOKIE.sub(rb"\1[REDACTED]", data)
    return HEADER.sub(rb"\1[REDACTED]", data)


for root in ROOTS:
    if not root.exists():
        continue
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".zip":
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temp:
                temp_path = Path(temp.name)
            try:
                with ZipFile(path) as source, ZipFile(temp_path, "w") as target:
                    for member in source.infolist():
                        target.writestr(member, redact(source.read(member)))
                temp_path.replace(path)
            finally:
                temp_path.unlink(missing_ok=True)
        elif path.suffix in TEXT_SUFFIXES:
            path.write_bytes(redact(path.read_bytes()))

backend_log = Path(os.environ["RUNNER_TEMP"]) / "backend.log"
if backend_log.exists():
    backend_log.write_bytes(redact(backend_log.read_bytes()))
