from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine

from diffpl.ingest.store import create_tables


@pytest.fixture
def engine() -> Iterator[Engine]:
    """SQLite stand-in for Postgres; the raw schema maps to SQLite's default schema."""
    eng = create_engine("sqlite://").execution_options(schema_translate_map={"raw": None})
    create_tables(eng)
    yield eng
    eng.dispose()
