# DiffPL

A free, open Fantasy Premier League decision lab. It gives calibrated, explainable
recommendations and proves them with leakage-free season replays.

Status: Phase 0 (foundations). See `CLAUDE.md` for goals, rules and roadmap.

## Setup

```bash
uv sync
cp .env.example .env
docker compose up -d   # Postgres 16 on :5432, MLflow on :5000
```

## Ingest

```bash
uv run python -m diffpl.ingest fpl                      # live FPL API snapshot
uv run python -m diffpl.ingest vaastav --season 2024-25 # historical season, pinned commit
```

See `docs/data_sources.md` for sources, licenses and leakage notes.

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
# Postgres integration tests run when this is set:
DIFFPL_TEST_DATABASE_URL=postgresql+psycopg://diffpl:diffpl@localhost:5432/diffpl uv run pytest
```
