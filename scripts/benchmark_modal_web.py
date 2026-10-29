"""Bounded, unauthenticated GET benchmark for an explicitly chosen staging origin."""

from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import ipaddress
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser

MAX_BODY_BYTES = 8 * 1024 * 1024


def origin_url(value: str, confirm_staging: bool) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Base URL must be an HTTP(S) origin without credentials, path, query or fragment"
        )
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.lower() == "localhost"
    if not loopback and not confirm_staging:
        raise ValueError(
            "Non-local targets require --confirm-staging; never benchmark production without authorization"
        )
    # Validate the port before using the URL.
    _ = parsed.port
    return f"{parsed.scheme}://{parsed.netloc}"


class Assets(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        value = (
            attributes.get("src")
            if tag == "script"
            else attributes.get("href")
            if tag == "link"
            else None
        )
        if not value:
            return
        parsed = urllib.parse.urlsplit(value)
        # Only local, real HTML-referenced Next assets. Ignore queries and external hosts.
        if not parsed.scheme and not parsed.netloc and parsed.path.startswith("/_next/static/"):
            self.paths.append(parsed.path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(origin: str, path: str, timeout: float, *, include_body: bool = False) -> dict:
    started = time.perf_counter()
    result: dict = {"status": None, "error": None, "bytes": 0, "ttfb_ms": None}
    request = urllib.request.Request(
        origin + path, headers={"Accept-Encoding": "identity"}, method="GET"
    )
    try:
        opener = urllib.request.build_opener(NoRedirect())
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            result["ttfb_ms"] = (time.perf_counter() - started) * 1000
            result["status"] = response.status
            data = response.read(MAX_BODY_BYTES + 1)
            result["bytes"] = len(data)
            content_type = response.headers.get_content_type()
            if response.status != 200:
                result["error"] = "http_status"
            elif len(data) > MAX_BODY_BYTES:
                result["error"] = "body_too_large"
            elif not data:
                result["error"] = "empty_body"
            elif path == "/" and content_type != "text/html":
                result["error"] = "unexpected_content_type"
            elif path == "/api/v1/ready":
                try:
                    payload = json.loads(data)
                    if not isinstance(payload, dict) or payload.get("status") != "ready":
                        result["error"] = "not_ready"
                except (ValueError, UnicodeDecodeError):
                    result["error"] = "invalid_json"
            elif path == "/icon.svg" and (content_type != "image/svg+xml" or b"<svg" not in data):
                result["error"] = "invalid_icon"
            elif path.startswith("/_next/static/") and content_type == "text/html":
                result["error"] = "unexpected_content_type"
            if include_body and result["error"] is None:
                result["body"] = data.decode("utf-8", errors="replace")
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
        # Do not emit exception strings that could contain sensitive URL data.
        result["error"] = "request_failed"
    result["latency_ms"] = (time.perf_counter() - started) * 1000
    return result


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[math.ceil(len(values) * fraction) - 1], 2)


def run_batch(origin: str, path: str, count: int, concurrency: int, timeout: float) -> dict:
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda _: fetch(origin, path, timeout), range(count)))
    elapsed = time.perf_counter() - started
    successful = [r for r in results if r["error"] is None]
    latencies = [r["latency_ms"] for r in successful]
    ttfb = [r["ttfb_ms"] for r in successful if r["ttfb_ms"] is not None]
    sizes = [r["bytes"] for r in successful]
    return {
        "path": path,
        "concurrency": concurrency,
        "requests": count,
        "elapsed_s": round(elapsed, 3),
        "requests_per_s": round(count / elapsed, 2),
        "successful_requests_per_s": round(len(successful) / elapsed, 2),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p90": percentile(latencies, 0.90),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 2) if latencies else None,
        },
        "ttfb_ms": {"p50": percentile(ttfb, 0.50), "p95": percentile(ttfb, 0.95)},
        "response_bytes": {
            "min": min(sizes),
            "max": max(sizes),
            "mean": round(sum(sizes) / len(sizes)),
        }
        if sizes
        else None,
        "errors": count - len(successful),
        "statuses": dict(
            Counter(
                str(r["status"]) if r["status"] is not None else "network_error" for r in results
            )
        ),
        "error_types": dict(Counter(r["error"] for r in results if r["error"])),
    }


def benchmark(origin: str, count: int, levels: list[int], warmup: int, timeout: float) -> dict:
    root = fetch(origin, "/", timeout, include_body=True)
    parser = Assets()
    parser.feed(root.get("body", ""))
    paths = ["/", "/api/v1/ready", "/icon.svg"]
    if parser.paths:
        paths.append(parser.paths[0])
    batches = []
    warmup_errors = {}
    for path in paths:
        failures = sum(fetch(origin, path, timeout)["error"] is not None for _ in range(warmup))
        warmup_errors[path] = failures
        for concurrency in levels:
            batches.append(run_batch(origin, path, count, concurrency, timeout))
    return {
        "origin": origin,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "warmup_per_endpoint": warmup,
        "warmup_errors": warmup_errors,
        "static_asset_discovered": bool(parser.paths),
        "results": batches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--confirm-staging",
        action="store_true",
        help="Confirm a non-local target is an authorized isolated staging deployment",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=16,
        help="Requests per endpoint and concurrency level (1–100)",
    )
    parser.add_argument(
        "--concurrency", default="1,4,8,16", help="Comma-separated concurrency levels, each 1–16"
    )
    parser.add_argument(
        "--warmup", type=int, default=2, help="Sequential warmup requests per endpoint (0–10)"
    )
    parser.add_argument("--timeout", type=float, default=15, help="Timeout in seconds (0–60]")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout")
    args = parser.parse_args()
    try:
        origin = origin_url(args.base_url, args.confirm_staging)
        levels = [int(x) for x in args.concurrency.split(",")]
        if (
            not 1 <= args.requests <= 100
            or not levels
            or any(not 1 <= x <= 16 for x in levels)
            or args.requests < max(levels)
        ):
            raise ValueError(
                "Requests must be 1–100 and at least the largest concurrency level (1–16)"
            )
        if not 0 <= args.warmup <= 10 or not 0 < args.timeout <= 60:
            raise ValueError("Warmup must be 0–10 and timeout in (0, 60]")
    except ValueError as exc:
        parser.error(str(exc))
    report = benchmark(origin, args.requests, levels, args.warmup, args.timeout)
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(output)
    else:
        print(output, end="")
    return int(
        not report["static_asset_discovered"]
        or any(report["warmup_errors"].values())
        or any(r["errors"] for r in report["results"])
    )


if __name__ == "__main__":
    raise SystemExit(main())
