"""Data freshness: how old is the newest raw FPL snapshot (ADR-0019).

`fetched_at` is when the FPL server answered, so a stale value means the pipeline stopped or the
API served old data. The check returns a result; the flow decides whether to fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select

from diffpl.ingest.store import fpl_api_responses

MAX_AGE = timedelta(hours=36)  # the pipeline refreshes daily; one missed run is tolerated


@dataclass(frozen=True)
class Freshness:
    source: str
    latest: datetime | None
    age: timedelta | None
    limit: timedelta

    @property
    def ok(self) -> bool:
        return self.age is not None and self.age <= self.limit

    def message(self) -> str:
        if self.latest is None:
            return f"{self.source}: no data"
        hours = (self.age or timedelta()).total_seconds() / 3600
        state = "ok" if self.ok else "STALE"
        return f"{self.source}: {state}, newest {self.latest.isoformat()} ({hours:.1f} h old)"


def evaluate(
    source: str, latest: datetime | None, now: datetime, limit: timedelta = MAX_AGE
) -> Freshness:
    if latest is not None and latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return Freshness(source, latest, None if latest is None else now - latest, limit)


def check_fpl(engine: Engine, now: datetime | None = None) -> Freshness:
    with engine.connect() as conn:
        latest = conn.execute(select(func.max(fpl_api_responses.c.fetched_at))).scalar()
    return evaluate("raw.fpl_api_responses", latest, now or datetime.now(UTC))
