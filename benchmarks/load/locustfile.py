"""Use through runner.py. Direct --host, distributed mode and >10 users fail closed."""

import json
import math
import os
import time
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path

import gevent
import psutil
import requests
from benchmarks.load.contracts import ContractFailure, assert_key_free
from benchmarks.load.journeys import JOURNEYS
from benchmarks.load.metrics import Metrics
from benchmarks.load.profiles import configured_profile
from benchmarks.load.runtime import read_run
from benchmarks.load.safety import (
    SafetyError,
    validate_attestation,
    validate_manifest,
    validate_path,
    validate_runner_options,
)
from locust import HttpUser, LoadTestShape, between, events, task
from locust.exception import StopUser

DIRECTORY = Path(os.environ["LOAD_RUN_DIRECTORY"])
MANIFEST, PRIVATE = read_run(DIRECTORY)
FIXTURE = json.loads((DIRECTORY / "fixtures.local.json").read_text(encoding="utf-8"))
PROFILE_NAME = os.environ.get("LOAD_PROFILE", "smoke")
PROFILE = configured_profile(PROFILE_NAME, os.environ)
USERS = int(os.environ.get("LOAD_USERS", "5"))
SCENARIO = os.environ.get("LOAD_SCENARIO", "mixed")
validate_manifest(MANIFEST, requested_users=USERS)
if PROFILE.get("design_only") or len(FIXTURE["accounts"]) < USERS:
    raise ValueError("EXECUTABLE_PROFILE_AND_DISTINCT_ACCOUNTS_REQUIRED")
AVAILABLE = deque(enumerate(FIXTURE["accounts"][:USERS]))
METRICS, COMPLETED, FAILED = Metrics(), Counter(), Counter()
START = None
STEADY_START = None
SAMPLES = []
RESOURCES = {}
STARTED_AT = None
PROCESS = psutil.Process()


def resource_snapshot():
    with requests.Session() as client:
        client.trust_env = False
        try:
            response = client.get(
                MANIFEST["base_url"] + "/__load__/metrics",
                headers={"X-Load-Token": PRIVATE["token"]},
                timeout=10,
                allow_redirects=False,
            )
            if response.status_code != 200:
                return {"observation_error": f"HTTP_{response.status_code}"}
            return response.json()
        except (requests.RequestException, ValueError):
            return {"observation_error": "TELEMETRY_UNAVAILABLE"}


@events.test_start.add_listener
def test_start(environment, **_kwargs):
    global START, STARTED_AT
    try:
        validate_runner_options(MANIFEST, environment.parsed_options, requested_users=USERS)
    except SafetyError:
        environment.process_exit_code = 1
        gevent.spawn(environment.runner.quit)
        return
    START = time.monotonic()
    STARTED_AT = datetime.now(UTC).isoformat()
    PROCESS.cpu_percent()
    RESOURCES["before"] = resource_snapshot()


@events.request.add_listener
def capture(
    request_type,
    name,
    response_time,
    response_length,
    response=None,
    exception=None,
    **_kwargs,
):
    if START is not None:
        status = getattr(response, "status_code", 0)
        # Do not serialize arbitrary exception strings: requests can embed auth URLs/headers.
        code = "REQUEST_FAILED" if exception else None
        METRICS.record(name, status, response_time, time.monotonic() - START, code)


@events.quitting.add_listener
def write_report(environment, **_kwargs):
    if START is None:
        return
    actual_end = time.monotonic() - START
    RESOURCES["after"] = resource_snapshot()
    start = STEADY_START if STEADY_START is not None else actual_end + 1
    report = METRICS.report(
        steady_start=start,
        steady_end=PROFILE["ramp"] + PROFILE["steady"],
        actual_end=actual_end,
    )
    report.update(
        {
            "schema_version": 1,
            "started_at_utc": STARTED_AT,
            "ended_at_utc": datetime.now(UTC).isoformat(),
            "workload_profile": PROFILE,
            "source_identity": MANIFEST.get("source_identity"),
            "run_id": MANIFEST["run_id"],
            "profile": PROFILE_NAME,
            "scenario": SCENARIO,
            "target_users": USERS,
            "load_model": "closed-concurrent-journeys",
            "inference": "disabled",
            "resources": RESOURCES,
            "journeys_completed": dict(COMPLETED),
            "journeys_failed": dict(FAILED),
            "load_generator": {"pid": os.getpid(), "samples": SAMPLES},
            "limitations": [
                "loopback only",
                "at most 10 local VUs",
                "HTTP backend only; no browser/rendering measurement",
                "fictional silent audio",
                "B Speaking completes without recorded audio; no ASR/AI capacity claim",
            ],
        }
    )
    destination = DIRECTORY / f"results-{PROFILE_NAME}-{SCENARIO}.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if FAILED or sum(item["failures"] for item in report["all"].values()):
        environment.process_exit_code = 1
    print(f"Sanitized load report: {destination}")


class IsolatedUser(HttpUser):
    host = MANIFEST["base_url"]
    wait_time = between(2, 4)

    def api(
        self,
        method,
        path,
        name,
        *,
        expected=(200,),
        active=False,
        binary=False,
        **kwargs,
    ):
        rate = PROFILE["max_rps_per_user"]
        if rate:
            gevent.sleep(max(0, getattr(self, "next_request", 0) - time.monotonic()))
            self.next_request = time.monotonic() + 1 / rate
        path = (
            path
            if path.startswith("/api/v1/") or path == "/__load__/identity"
            else "/api/v1" + path
        )
        validate_path(path)
        if path == "/api/v1/auth/login":
            self.client.cookies.clear()
        with self.client.request(
            method,
            path,
            name=name,
            allow_redirects=False,
            timeout=30,
            catch_response=True,
            **kwargs,
        ) as response:
            if response.status_code not in expected:
                response.failure(f"HTTP_{response.status_code}")
                raise ContractFailure(f"HTTP_{response.status_code}")
            try:
                data = response.content if binary else response.json() if response.content else None
                if active:
                    assert_key_free(data)
            except (ValueError, ContractFailure):
                response.failure("RESPONSE_CONTRACT_INVALID")
                raise ContractFailure("RESPONSE_CONTRACT_INVALID") from None
            response.success()
            return data

    def on_start(self):
        try:
            validate_runner_options(
                MANIFEST, self.environment.parsed_options, requested_users=USERS
            )
        except SafetyError:
            self.environment.process_exit_code = 1
            gevent.spawn(self.environment.runner.quit)
            raise StopUser() from None
        if self.client.base_url != MANIFEST["base_url"]:
            self.environment.process_exit_code = 1
            gevent.spawn(self.environment.runner.quit)
            raise StopUser()
        if not AVAILABLE:
            raise StopUser()
        self.slot, self.cohort = AVAILABLE.popleft()
        self.iteration = 0
        self.client.trust_env = False
        self.client.headers["X-Load-Token"] = PRIVATE["token"]
        identity = self.api("GET", "/__load__/identity", "safety.attestation")
        validate_attestation(MANIFEST, identity)

    @task
    def journey(self):
        scenario = (
            SCENARIO if SCENARIO != "mixed" else ("A", "B", "C")[(self.slot + self.iteration) % 3]
        )
        try:
            JOURNEYS[scenario](
                self.api,
                lambda seconds: gevent.sleep(seconds * PROFILE["think_scale"]),
                FIXTURE,
                self.cohort,
                self.iteration,
            )
            COMPLETED[scenario] += 1
            self.iteration += 1
        except Exception as error:  # noqa: BLE001 -- report sanitized lifecycle failure, then stop
            code = str(error) if isinstance(error, ContractFailure) else type(error).__name__
            FAILED[f"{scenario}:{code}"] += 1
            self.environment.events.request.fire(
                request_type="CHECK",
                name=f"journey.{scenario}",
                response_time=0,
                response_length=0,
                exception=ContractFailure(code),
                context={},
            )
            # Fail fast on broken lifecycle/privacy; report actual window rather than running invalid traffic.
            gevent.spawn(self.environment.runner.quit)
            raise StopUser() from None


class IsolatedShape(LoadTestShape):
    def tick(self):
        global STEADY_START
        elapsed = self.get_run_time()
        actual = self.get_current_user_count()
        SAMPLES.append(
            {
                "elapsed_seconds": round(elapsed, 2),
                "users": actual,
                "cpu_percent": PROCESS.cpu_percent(),
                "rss_bytes": PROCESS.memory_info().rss,
            }
        )
        if elapsed < PROFILE["ramp"]:
            return max(1, math.ceil(USERS * elapsed / PROFILE["ramp"])), max(
                1, USERS / PROFILE["ramp"]
            )
        if elapsed < PROFILE["ramp"] + PROFILE["steady"]:
            if actual == USERS and STEADY_START is None:
                STEADY_START = math.ceil(elapsed)
            return USERS, USERS
        # Locust stop_timeout permits in-flight journeys to finish during the drain.
        return None
