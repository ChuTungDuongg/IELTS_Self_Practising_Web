import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "benchmark_modal_web", Path(__file__).resolve().parents[1] / "benchmark_modal_web.py"
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/api/v1/ready")
            self.end_headers()
            return
        content = {
            "/": ("text/html", b'<script src="/_next/static/chunks/real.js"></script>'),
            "/api/v1/ready": ("application/json", b'{"status":"ready"}'),
            "/icon.svg": ("image/svg+xml", b"<svg></svg>"),
            "/_next/static/chunks/real.js": ("application/javascript", b"// fixture"),
        }
        if self.path not in content:
            self.send_response(404)
            self.end_headers()
            return
        mime, body = content[self.path]
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def test_loopback_report_discovers_asset_and_records_metrics(self):
        report = bench.benchmark(self.origin, 4, [1, 4], 1, 5)
        self.assertTrue(report["static_asset_discovered"])
        self.assertEqual(len(report["results"]), 8)
        self.assertTrue(all(row["errors"] == 0 for row in report["results"]))
        self.assertTrue(all(row["ttfb_ms"]["p95"] is not None for row in report["results"]))
        self.assertTrue(all(row["response_bytes"]["min"] > 0 for row in report["results"]))
        json.dumps(report)

    def test_external_targets_need_explicit_staging_confirmation(self):
        with self.assertRaises(ValueError):
            bench.origin_url("https://example.com", False)
        self.assertEqual(bench.origin_url("https://example.com", True), "https://example.com")
        for invalid in (
            "http://user:password@example.com",
            "https://example.com/?token=secret",
            "file:///etc/passwd",
        ):
            with self.assertRaises(ValueError):
                bench.origin_url(invalid, True)

    def test_failures_are_counted_and_not_used_as_successful_latency(self):
        result = bench.run_batch(self.origin, "/missing", 3, 2, 5)
        self.assertEqual(result["statuses"], {"404": 3})
        self.assertEqual(result["errors"], 3)
        self.assertIsNone(result["latency_ms"]["p95"])

    def test_redirect_is_reported_instead_of_followed(self):
        result = bench.fetch(self.origin, "/redirect", 5)
        self.assertEqual(result["status"], 302)
        self.assertEqual(result["error"], "http_status")

    def test_discovery_rejects_external_assets(self):
        parser = bench.Assets()
        parser.feed(
            '<script src="https://example.com/_next/static/a.js"></script><script src="/_next/static/actual.js?x=1"></script>'
        )
        self.assertEqual(parser.paths, ["/_next/static/actual.js"])


if __name__ == "__main__":
    unittest.main()
