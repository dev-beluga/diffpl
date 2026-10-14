# DiffPL

A free, open decision lab for Fantasy Premier League (FPL). It gives calibrated, explainable
recommendations and proves them with leakage-free season replays.

> Status: Phase 0 (foundations). Repo, local services, CI, ingestion, dbt staging and the
> 2026/27 rules config exist. Models and agents do not yet. Nothing below under "Results" is claimed until an eval backs it.

## Why

Existing FPL tools already cover point projections, solvers, planners and live ranks. DiffPL
skips those and focuses on what they leave open:

- **Season Replay Env ("FPL Gym").** Replays past seasons gameweek by gameweek using only data
  available before each deadline. Any manager (heuristic, ML model, solver, LLM agent) plugs in
  and gets scored the same way.
- **Calibrated projections.** A points distribution per player per gameweek, with published
  calibration plots and backtest metrics, not only a point estimate.
- **Rank-aware planner.** Optimizes for the manager's actual goal (win a mini-league, reach the
  top 10k, protect rank) using effective ownership and simulated outcomes.
- **Decision review.** After each gameweek, separates decision quality from luck by comparing the
  ex-ante value of the chosen move against the alternatives.
- **Team-news NLP.** Extracts start probability and injury status from press conferences and
  news, with source quotes.
- **Rival modeling.** Predicts mini-league rivals' transfers and captaincy from their history.
- **Agent league.** LLM agents manage teams in the replay env, compared on points, cost and
  latency.

## Principles

- **No data leakage.** Every row carries `as_of` (UTC). Training, replay and live scoring read
  only rows with `as_of` before the gameweek deadline, and each feature has a leakage test.
- **Distributions, not points.** Models output samples; the simulator and planner consume them.
- **Evals gate changes.** A model, prompt or agent replaces the champion only after it wins in
  the replay env and the eval harness across held-out seasons.
- **Explainable.** Each recommendation carries the evidence behind it.
- **Immutable raw data, versioned rules.** Raw data is written once. Scoring rules live per
  season in `config/rules/<season>.yaml`.
- **Untrusted input stays data.** News, transcripts and user text never act as instructions.
  Agents never write to FPL accounts.
- **Reproducible.** Fixed seeds, versioned datasets, prompts and eval sets; every run is logged
  in MLflow.

## Architecture

One pipeline with one clock. Live mode is the replay env with the cursor set to now, so replay
scores carry over to real recommendations.

```mermaid
flowchart TD
    src["FPL API + vaastav history"] --> ingest["ingest/<br/>cached, rate-limited client"]
    ingest --> raw[("Postgres raw<br/>append-only, as_of")]
    raw --> dbt["dbt<br/>staging + marts"]
    rules["config/rules/<br/>per-season rules"]
    news["news + press conferences"] --> nlp["nlp/<br/>team news"]
    dbt --> features["features/<br/>as_of before deadline"]
    nlp --> features
    features --> models["models/<br/>points distributions"]
    models --> sim["sim/<br/>Monte Carlo outcomes"]
    sim --> optim["optim/<br/>MILP planner"]
    rules --> replay
    rules --> optim
    optim --> replay["replay/<br/>Season Replay Env"]
    agents["agents/ + mcp/<br/>LLM managers"] --> replay
    features --> replay
    replay --> api["api/ + UI"]
```

| Layer | Package | Responsibility | Phase |
| --- | --- | --- | --- |
| Ingest | `ingest/` | Cached, rate-limited FPL API client and vaastav historical loader, writing to `raw` with `as_of` | 0 |
| Transform | `dbt/` | Typed, deduplicated staging and marts; dbt tests and freshness checks | 0 |
| Rules | `config/rules/` | Scoring, chips, squad and transfer rules per season | 0 |
| Features | `features/` | Point-in-time feature rows keyed by player, gameweek and `as_of` | 1 to 2 |
| Replay env | `replay/` | Time cursor, rules engine, `Manager.observe() -> act()`, scoring | 1 |
| Projections | `models/` | Baseline, LightGBM and probabilistic models | 2 |
| Simulator | `sim/` | Monte Carlo gameweek outcomes from projection samples | 3 |
| Planner | `optim/` | Multi-gameweek MILP for transfers, captain and chips, with a rank-aware objective | 3 |
| Team news | `nlp/` | Start probability and injury status with source quotes | 4 |
| Agents | `agents/`, `mcp/` | LLM managers calling MCP tools under step, token and cost budgets | 5 |
| Observability | `obs/` | Metrics, traces, drift reports and alerts | 6 |
| Serving | `api/` | FastAPI and a Streamlit UI | 7 |

The replay env is the hub: heuristic baselines, the planner and LLM agents all implement the same
`Manager` interface and are scored on total points, rank percentile, hits taken and regret
against the hindsight optimum.

## Stack

| Concern | Choice |
| --- | --- |
| Language and tooling | Python 3.12, uv, ruff, mypy (strict), pytest |
| Storage | PostgreSQL 16 (`raw`, `staging`, `marts`, plus an `mlflow` database); DuckDB for local analysis |
| Transform | dbt-core |
| Models | LightGBM, PyMC or NumPyro, PyTorch |
| Optimization | PuLP or highspy (HiGHS) |
| NLP and agents | Hugging Face, Ollama (small quantized models), API LLMs, MCP Python SDK |
| MLOps | Prefect, MLflow, Evidently, GitHub Actions |
| Observability | Prometheus, Grafana, OpenTelemetry, Langfuse |
| Serving | FastAPI, Streamlit |
| Deploy | Docker Compose, later k3d and Helm |

Choices and the alternatives considered are recorded as ADRs in [`docs/decisions/`](docs/decisions/).

## Quickstart

Requirements: [uv](https://docs.astral.sh/uv/) and Docker with Compose.

```bash
uv sync
cp .env.example .env
docker compose up -d   # Postgres 16 on :5432, MLflow on :5000
```

Settings come from `DIFFPL_*` environment variables (see `.env.example`), read by
`src/diffpl/settings.py`.

## Ingest and transform

```bash
uv run python -m diffpl.ingest fpl                      # live FPL API snapshot
uv run python -m diffpl.ingest vaastav --season 2024-25 # historical season, pinned commit
uv run dbt build --project-dir dbt --profiles-dir dbt   # staging views and tests
```

See `docs/data_sources.md` for sources, licenses and leakage notes.

## Development checks

The same checks run in CI on every push and pull request.

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
# Postgres integration tests run when this is set:
DIFFPL_TEST_DATABASE_URL=postgresql+psycopg://diffpl:diffpl@localhost:5432/diffpl uv run pytest
docker compose config --quiet
```

## Repo layout

```
src/diffpl/
  ingest/  features/  models/  sim/  optim/  replay/  nlp/  agents/  mcp/  api/  obs/
dbt/                # staging and marts models
flows/              # Prefect flows
config/rules/       # scoring rules per season
prompts/            # versioned prompts
evals/              # golden sets, judge configs, eval runners
ops/                # Postgres init, later Prometheus, Grafana, Helm
tests/
notebooks/          # exploration only, never imported
docs/decisions/     # ADRs
```

## Roadmap

- [ ] **Phase 0:** repo, Docker Compose (Postgres, MLflow), CI, FPL ingestion, historical load,
  dbt models, rules config, first leakage test
- [ ] **Phase 1:** Season Replay Env, baseline managers (template, form, fixtures), metrics,
  leakage tests in CI
- [ ] **Phase 2:** projections (baseline, LightGBM, probabilistic), calibration report, MLflow
  champion and challenger
- [ ] **Phase 3:** simulator, MILP multi-gameweek planner, rank-aware objective
- [ ] **Phase 4:** team-news NLP, golden set, eval harness in CI, prompt-injection tests
- [ ] **Phase 5:** MCP server, agents, agent harness, Langfuse tracing, agent league
- [ ] **Phase 6:** Prefect orchestration, Prometheus and Grafana, drift reports, alerts
- [ ] **Phase 7:** FastAPI and UI, FPL ID import, decision review, rival modeling, k3d and Helm

## Results

None yet. This section will hold replay scores against baselines, calibration plots, and cost
and latency per agent decision, each linked to the eval run that produced it.

## Data sources

- [FPL API](https://fantasy.premierleague.com/api/bootstrap-static/): public but unofficial and
  undocumented. DiffPL caches responses and respects rate limits.
- [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League):
  historical seasons at gameweek level.

DiffPL does not scrape paid sites or use any source against its terms.

## Non-goals

Live scores, live ranks and price change prediction (official FPL covers these), mobile apps,
payments, and accounts beyond FPL team ID import.
