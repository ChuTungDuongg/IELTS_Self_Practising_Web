"""Explicit build/setup download of the pinned CPU model; never invoked by a request."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

SHA256 = "597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004"
URL = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/"
    "fba061dc5559f696e62171e9a0741782b0fdc23c/src/silero_vad/data/silero_vad.onnx"
)


def install(destination):
    with urlopen(URL, timeout=60) as response:
        data = response.read(4 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Pinned VAD checksum mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    try:
        temporary.write_bytes(data)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    install(parser.parse_args().destination)
