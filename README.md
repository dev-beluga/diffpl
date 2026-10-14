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

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```
