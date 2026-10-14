# ADR-0002: Raw ingestion stores whole payloads, append-only

Status: accepted
Date: 2026-10-14

## Context

The FPL API is undocumented and changes between seasons. Historical data comes from a
community repo whose CSV columns also change by season. Replay needs to know what was
knowable at each deadline.

## Decision

- Store each FPL API response whole as JSONB in `raw.fpl_api_responses`, keyed by
  `(url, payload_sha256)`. Identical payloads are stored once, keeping the earliest
  `fetched_at`.
- Store each vaastav CSV row as a JSON object of strings in `raw.vaastav_rows`, keyed by
  `(source_commit, season, file, row_num)`. Downloads are pinned to a commit SHA.
- Rows are inserted with `ON CONFLICT DO NOTHING` and never updated or deleted.
- Typing, renaming and `as_of` derivation happen in dbt staging, not in Python.

## Alternatives considered

- Typed raw tables per endpoint: breaks on the first schema change and loses fields we
  did not anticipate.
- Files in object storage (Parquet or JSON on disk): simpler to write, but dbt and the
  freshness checks then need a second engine. Postgres is already running.

## Consequences

- Raw tables grow with every changed snapshot. A daily `element-summary` sweep is about
  800 payloads; most are unchanged between days and deduplicate by hash.
- A schema change surfaces as a failing dbt test in staging, and the raw data is intact.
