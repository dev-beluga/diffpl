"""Job metrics in Prometheus text format (ADR-0019).

Flows are short-lived, so they write a `.prom` file that Prometheus' textfile collector (or any
scraper of that directory) reads, instead of running a server that would be gone before a scrape.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from prometheus_client import CollectorRegistry, Gauge, write_to_textfile

from diffpl.obs.freshness import Freshness


class JobMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.duration = Gauge(
            "diffpl_job_duration_seconds", "Last run time of a job", ["job"], registry=self.registry
        )
        self.success = Gauge(
            "diffpl_job_success", "1 if the last run of a job succeeded", ["job"],
            registry=self.registry,
        )  # fmt: skip
        self.last_run = Gauge(
            "diffpl_job_last_run_timestamp_seconds", "Unix time the job last ended", ["job"],
            registry=self.registry,
        )  # fmt: skip
        self.data_age = Gauge(
            "diffpl_data_age_seconds", "Age of the newest row of a source", ["source"],
            registry=self.registry,
        )  # fmt: skip

    @contextmanager
    def job(self, name: str) -> Iterator[None]:
        """Time a job; record success or failure, then re-raise any error."""
        started = time.time()
        ok = 0
        try:
            yield
            ok = 1
        finally:
            ended = time.time()
            self.duration.labels(name).set(ended - started)
            self.success.labels(name).set(ok)
            self.last_run.labels(name).set(ended)

    def record_freshness(self, f: Freshness) -> None:
        if f.age is not None:
            self.data_age.labels(f.source).set(f.age.total_seconds())

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_to_textfile(str(path), self.registry)
