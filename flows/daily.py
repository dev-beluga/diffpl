"""Daily pipeline: refresh FPL data, rebuild marts with dbt, check freshness.

uv run python flows/daily.py            # run once
uv run python flows/daily.py --serve    # run on a schedule (06:00 UK) until stopped

Metrics go to ops/metrics/diffpl.prom for Prometheus' textfile collector.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from prefect import flow, get_run_logger, task
from sqlalchemy import create_engine

from diffpl.ingest.__main__ import main as ingest_main
from diffpl.obs.freshness import Freshness, check_fpl
from diffpl.obs.metrics import JobMetrics
from diffpl.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
METRICS_FILE = ROOT / "ops" / "metrics" / "diffpl.prom"


@task(retries=2, retry_delay_seconds=60)
def ingest_fpl(players: bool = True) -> None:
    args = ["--cache-dir", str(ROOT / "data" / "cache"), "fpl"]
    ingest_main(args if players else [*args, "--no-players"])


@task
def dbt_build() -> None:
    subprocess.run(
        ["dbt", "build", "--project-dir", "dbt", "--profiles-dir", "dbt"], cwd=ROOT, check=True
    )


@task
def check_freshness() -> Freshness:
    return check_fpl(create_engine(get_settings().database_url))


@flow(name="diffpl-daily")
def daily(players: bool = True) -> None:
    log = get_run_logger()
    metrics = JobMetrics()
    try:
        with metrics.job("ingest_fpl"):
            ingest_fpl(players)
        with metrics.job("dbt_build"):
            dbt_build()
        with metrics.job("freshness"):
            fresh = check_freshness()
            metrics.record_freshness(fresh)
            log.info(fresh.message())
            if not fresh.ok:
                raise RuntimeError(fresh.message())
    finally:
        metrics.write(METRICS_FILE)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        daily.serve(name="daily", cron="0 6 * * *", tags=["diffpl"])
    else:
        daily(players="--no-players" not in sys.argv)
