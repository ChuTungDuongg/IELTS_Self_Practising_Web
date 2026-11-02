"""Validate retained evidence offline; never creates load or opens a database."""

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.load.summarize import summarize

ROOT = Path(__file__).resolve().parents[2]


def validate(directory: Path) -> dict:
    directory = directory.resolve()
    documents = {
        path.name: json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.json")
    }
    index = documents["evidence.json"]
    checked_hashes = 0
    for experiment in index["experiments"]:
        path = (directory / experiment["file"]).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Evidence path leaves the repository")
        if hashlib.sha256(path.read_bytes()).hexdigest() != experiment["sha256"]:
            raise ValueError(f"Evidence checksum mismatch: {experiment['test_id']}")
        checked_hashes += 1

    maximum = 0
    for raw_name, summary_name in (
        ("http-baseline-smoke.json", "http-baseline-summary.json"),
        ("http-candidate-smoke.json", "http-candidate-summary.json"),
        ("http-candidate-burst.json", "http-burst-summary.json"),
    ):
        computed = summarize(documents[raw_name])
        if computed != documents[summary_name]:
            raise ValueError(f"Summary differs from raw measurements: {summary_name}")
        maximum = max(maximum, computed["maximum_observed_users"])
    if maximum != index["maximum_observed_http_vus"]:
        raise ValueError("Maximum observed VUs differs from the evidence index")
    if index["verdict_5000"] != "NOT VERIFIED" or 5000 not in index["unexecuted"]["http_vus"]:
        raise ValueError("Retained experiments do not verify 5,000 active learners")
    return {
        "status": "PASS",
        "json_files_parsed": len(documents),
        "experiment_checksums": checked_hashes,
        "http_summaries_recomputed": 3,
        "maximum_observed_http_vus": maximum,
        "verdict_5000": index["verdict_5000"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "docs/performance/5000-user")
    args = parser.parse_args()
    print(json.dumps(validate(args.directory), indent=2))


if __name__ == "__main__":
    main()
