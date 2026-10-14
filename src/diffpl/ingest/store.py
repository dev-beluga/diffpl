"""Append-only tables in the `raw` schema.

Rows are inserted once and never updated or deleted. Re-running an ingest is safe: a row whose
natural key already exists is skipped, so the earliest `fetched_at` for a payload survives.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.sql.dml import Insert

RAW_SCHEMA = "raw"
metadata = MetaData(schema=RAW_SCHEMA)
JsonType = JSON().with_variant(postgresql.JSONB(), "postgresql")

fpl_api_responses = Table(
    "fpl_api_responses",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True),
    Column("endpoint", String, nullable=False),
    Column("url", String, nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("payload", JsonType, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("url", "payload_sha256"),
)

vaastav_rows = Table(
    "vaastav_rows",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True),
    Column("source_commit", String(40), nullable=False),
    Column("season", String(7), nullable=False),
    Column("file", String, nullable=False),
    Column("row_num", Integer, nullable=False),
    Column("data", JsonType, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("source_commit", "season", "file", "row_num"),
)


def create_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        metadata.create_all(conn)


def insert_new(engine: Engine, table: Table, rows: Iterable[Mapping[str, Any]]) -> int:
    """Insert rows, skipping any that conflict with an existing unique key. Returns rows added."""
    batch = list(rows)
    if not batch:
        return 0
    dialect = engine.dialect.name
    stmt: Insert
    if dialect == "postgresql":
        stmt = postgresql.insert(table).on_conflict_do_nothing()
    elif dialect == "sqlite":
        stmt = sqlite.insert(table).on_conflict_do_nothing()
    else:
        raise NotImplementedError(f"unsupported dialect: {dialect}")
    # rowcount is -1 for batched inserts on psycopg, so count the ids that come back instead.
    with engine.begin() as conn:
        return len(conn.execute(stmt.returning(table.c.id), batch).all())
