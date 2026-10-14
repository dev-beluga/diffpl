# ADR-0001: Python stack, repo layout and local services

Status: accepted
Date: 2026-10-14

## Context

DiffPL needs a reproducible base before ingestion, models and agents. It must run on a laptop
(RTX 2050, 4 GB VRAM) and in CI with no paid services.

## Decision

- Python 3.12, managed with uv and a committed `uv.lock`.
- `src/diffpl/` layout, one subpackage per pipeline stage (ingest, features, models, sim,
  optim, replay, nlp, agents, mcp, api, obs).
- ruff for lint and format, mypy in strict mode, pytest.
- Docker Compose runs Postgres 16 (schemas `raw`, `staging`, `marts`) and an MLflow server
  that stores runs in its own Postgres database.
- Settings come from `DIFFPL_*` environment variables via pydantic-settings.
- GitHub Actions runs lint, format check, type check and tests on every push and PR.

## Alternatives considered

- Poetry instead of uv: slower installs, no Python version management.
- Flat layout instead of `src/`: tests could import the working tree instead of the
  installed package.
- SQLite for MLflow: simpler, but a second database engine to operate. Postgres is already
  running.

## Consequences

- Every later phase adds dependencies through `uv add`, so the lock file tracks them.
- Strict mypy costs some annotation time up front and catches interface drift between stages.
