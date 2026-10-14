"""Runs against a real Postgres when DIFFPL_TEST_DATABASE_URL is set (CI sets it)."""

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, select, text

from diffpl.ingest.store import create_tables, fpl_api_responses, insert_new, vaastav_rows

URL = os.environ.get("DIFFPL_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="DIFFPL_TEST_DATABASE_URL not set")
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def pg() -> Iterator[Engine]:
    assert URL is not None
    schema = f"raw_test_{uuid.uuid4().hex[:8]}"
    base = create_engine(URL)
    with base.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    eng = base.execution_options(schema_translate_map={"raw": schema})
    create_tables(eng)
    yield eng
    with base.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    base.dispose()


def test_jsonb_round_trip_and_conflict_skip(pg: Engine) -> None:
    row = {
        "endpoint": "fixtures",
        "url": "https://fantasy.premierleague.com/api/fixtures/",
        "payload_sha256": "a" * 64,
        "payload": [{"id": 1, "team_h_score": None}],
        "fetched_at": NOW,
    }
    assert insert_new(pg, fpl_api_responses, [row]) == 1
    assert insert_new(pg, fpl_api_responses, [{**row, "fetched_at": datetime.now(UTC)}]) == 0
    with pg.connect() as conn:
        payload, fetched_at = conn.execute(
            select(fpl_api_responses.c.payload, fpl_api_responses.c.fetched_at)
        ).one()
    assert payload == [{"id": 1, "team_h_score": None}]
    assert fetched_at == NOW


def test_bulk_insert_counts_only_new_rows(pg: Engine) -> None:
    rows = [
        {
            "source_commit": "c" * 40,
            "season": "2024-25",
            "file": "teams.csv",
            "row_num": i,
            "data": {"id": str(i)},
            "fetched_at": NOW,
        }
        for i in range(500)
    ]
    assert insert_new(pg, vaastav_rows, rows[:300]) == 300
    assert insert_new(pg, vaastav_rows, rows) == 200
