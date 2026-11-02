"""Aggregate diagnostics for the attested benchmark wrapper, never production.

No statement text, parameters, routes, headers or learner identifiers are kept.
The observer uses one extra database connection.
"""

import asyncio
import math
from collections import Counter, deque
from contextlib import suppress
from time import perf_counter

import psutil
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine


class Distribution:
    def __init__(self):
        self.values = Counter()

    def add(self, milliseconds):
        self.values[min(60000, max(0, round(milliseconds)))] += 1

    def summary(self):
        count = self.values.total()

        def percentile(fraction):
            target, total = math.ceil(count * fraction), 0
            for value, amount in sorted(self.values.items()):
                total += amount
                if total >= target:
                    return value
            return None

        return {
            "samples": count,
            "p50_ms": percentile(0.5),
            "p95_ms": percentile(0.95),
            "p99_ms": percentile(0.99),
            "max_ms": max(self.values, default=None),
        }


class LoadTelemetry:
    def __init__(self, engine, database_url):
        self.engine = engine
        self.observer = create_async_engine(
            database_url,
            pool_size=1,
            max_overflow=0,
            connect_args={"server_settings": {"application_name": "load-aggregate-observer"}},
        )
        self.process = psutil.Process()
        self.started = perf_counter()
        self.cpu_start = self._cpu()
        self.rss_peak = self.process.memory_info().rss
        self.lag, self.sql = Distribution(), Distribution()
        self.sql_errors = self.observation_errors = 0
        self.samples = deque(maxlen=7200)
        self.jobs = []
        self.listeners = [
            ("before_cursor_execute", self._before),
            ("after_cursor_execute", self._after),
            ("handle_error", self._error),
        ]

    def _cpu(self):
        times = self.process.cpu_times()
        return times.user + times.system

    def _before(self, connection, *_):
        connection.info["load_query_start"] = perf_counter()

    def _after(self, connection, *_):
        started = connection.info.pop("load_query_start", None)
        if started is not None:
            self.sql.add((perf_counter() - started) * 1000)

    def _error(self, context):
        self.sql_errors += 1

    def start(self):
        for name, handler in self.listeners:
            event.listen(self.engine.sync_engine, name, handler)
        self.jobs = [
            asyncio.create_task(self._lag()),
            asyncio.create_task(self._sample()),
        ]

    async def close(self):
        for task in self.jobs:
            task.cancel()
        for task in self.jobs:
            with suppress(asyncio.CancelledError):
                await task
        for name, handler in self.listeners:
            event.remove(self.engine.sync_engine, name, handler)
        await self.observer.dispose()

    async def _lag(self):
        while True:
            target = perf_counter() + 0.02
            await asyncio.sleep(0.02)
            self.lag.add((perf_counter() - target) * 1000)

    async def _sample(self):
        while True:
            try:
                async with self.observer.connect() as connection:
                    activity = (
                        (
                            await connection.execute(
                                text(
                                    "SELECT count(*) AS connections, "
                                    "count(*) FILTER (WHERE state = 'active') AS active, "
                                    "count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiters, "
                                    "count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction, "
                                    "coalesce(max(extract(epoch from clock_timestamp()-xact_start)),0) AS oldest_tx_seconds "
                                    "FROM pg_stat_activity WHERE datname=current_database() "
                                    "AND application_name <> 'load-aggregate-observer'"
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                    database = (
                        (
                            await connection.execute(
                                text(
                                    "SELECT deadlocks,xact_commit,xact_rollback,blks_read,blks_hit,"
                                    "temp_bytes FROM pg_stat_database WHERE datname=current_database()"
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                rss = self.process.memory_info().rss
                self.rss_peak = max(self.rss_peak, rss)
                self.samples.append(
                    {
                        "elapsed_seconds": round(perf_counter() - self.started, 3),
                        "rss_bytes": rss,
                        "cpu_seconds": round(self._cpu() - self.cpu_start, 4),
                        "pool_checked_out": self.engine.pool.checkedout(),
                        "pool_overflow": self.engine.pool.overflow(),
                        "database": {
                            key: float(value)
                            for key, value in (dict(activity) | dict(database)).items()
                        },
                    }
                )
            except (SQLAlchemyError, psutil.Error, OSError, ValueError):
                self.observation_errors += 1
            await asyncio.sleep(1)

    def snapshot(self):
        return {
            "source": "benchmark-wrapper; psutil; SQLAlchemy cursor events; pg_stat_activity/database",
            "elapsed_seconds": round(perf_counter() - self.started, 3),
            "cpu_seconds": round(self._cpu() - self.cpu_start, 4),
            "rss_peak_bytes": self.rss_peak,
            "event_loop_lag": self.lag.summary(),
            "sql_cursor_latency": self.sql.summary(),
            "sql_errors": self.sql_errors,
            "observation_errors": self.observation_errors,
            "sample_interval_seconds": 1,
            "samples_retained": len(self.samples),
            "samples": list(self.samples),
            "limitations": [
                "SQL cursor time excludes pool checkout, ORM loading, commit and Python processing",
                "one-second samples can miss connection/lock/memory peaks",
                "database counters are cumulative; compare snapshots/deltas",
                "startup/fixture activity included; only HTTP report separates steady window",
                "p99 diagnostic only; small sample counts do not establish tail SLO",
                "observer uses one additional DB connection; no pool wait/ingress queue measurement",
            ],
        }
