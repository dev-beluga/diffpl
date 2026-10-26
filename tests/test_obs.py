"""Freshness verdicts and the metrics file."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from diffpl.obs.freshness import evaluate
from diffpl.obs.metrics import JobMetrics

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def test_fresh_stale_and_empty() -> None:
    assert evaluate("s", NOW - timedelta(hours=3), NOW).ok
    stale = evaluate("s", NOW - timedelta(hours=40), NOW)
    assert not stale.ok and "STALE" in stale.message()
    empty = evaluate("s", None, NOW)
    assert not empty.ok and empty.message() == "s: no data"


def test_naive_timestamps_are_read_as_utc() -> None:
    assert evaluate("s", datetime(2026, 10, 26, 11, 0), NOW).ok


def test_job_metrics_record_success_and_failure_then_write(tmp_path: Path) -> None:
    m = JobMetrics()
    with m.job("a"):
        pass
    with pytest.raises(ValueError), m.job("b"):
        raise ValueError("boom")
    m.record_freshness(evaluate("raw", NOW - timedelta(hours=1), NOW))
    out = tmp_path / "m" / "x.prom"
    m.write(out)
    text = out.read_text(encoding="utf-8")
    assert 'diffpl_job_success{job="a"} 1.0' in text
    assert 'diffpl_job_success{job="b"} 0.0' in text
    assert 'diffpl_data_age_seconds{source="raw"} 3600.0' in text
