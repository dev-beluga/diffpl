# ADR-0019: Daily Prefect flow, freshness check and job metrics

Status: accepted
Date: 2026-10-26

## Context

CLAUDE.md asks for scheduled pipelines, alerts on stale FPL data, and metrics for job duration,
failures and data freshness. Phase 6 starts with the daily refresh.

## Decision

- `flows/daily.py`: Prefect flow `diffpl-daily` = ingest FPL (2 retries), `dbt build`, freshness
  check. `--serve` runs it on a cron (06:00 UK); `--no-players` skips the per-player calls.
- `diffpl.obs.freshness`: the newest `fetched_at` in `raw.fpl_api_responses` must be at most
  36 hours old (one missed daily run is tolerated). A stale or empty source fails the flow.
- `diffpl.obs.metrics.JobMetrics`: per-job duration, success flag and last-run time, plus data
  age, written as a Prometheus text file at `ops/metrics/diffpl.prom` (git-ignored). Flows are
  short-lived, so a file for the textfile collector replaces a server nobody could scrape.

## Verification

3 unit tests (fresh, stale, empty, naive timestamps, metrics file). A real run with
`--no-players`: ingest 1.4 s, dbt build 69 s (4 tables, 15 views, 41 tests pass), freshness ok.

## Consequences

- A full run with player summaries (hundreds of rate-limited calls) failed under Prefect's
  temporary server on this machine (connection refused to its own API after minutes). Run
  `prefect server start` and set `PREFECT_API_URL` for long jobs; ingest itself is unaffected.
- Alerts (Grafana to Telegram), the Prometheus scrape config and dashboards come next; Telegram
  needs a bot token from the owner.
