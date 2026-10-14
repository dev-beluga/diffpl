# ADR-0003: dbt staging conventions

Status: accepted
Date: 2026-10-15

## Context

Raw tables hold untyped JSON (ADR-0002). Features and replay need typed rows that carry
`as_of`, and must never see information from after a deadline.

## Decision

- dbt project in `dbt/`, profile in `dbt/profiles.yml` read from env vars. Staging models are
  views in the `staging` schema.
- vaastav: `base_vaastav__rows` keeps one commit per season, the most recently ingested.
  Older commits stay in raw.
- `stg_vaastav__player_gameweeks.as_of = kickoff_time + 3 hours` (var `match_settle_interval`),
  so bonus is settled. Replay filters `as_of < deadline`.
- `stg_vaastav__players` exposes identity columns only. End-of-season prices, totals and news
  in `players_raw.csv` are left out, and a dbt test fails if they appear.
- FPL API models explode bootstrap and fixtures payloads; `as_of = fetched_at`.
- Leakage and uniqueness checks are singular SQL tests in `dbt/tests/`.

## Alternatives considered

- Tables instead of views: faster reads, but staging is small and views stay in sync with raw.
- dbt_utils for multi-column uniqueness: one more package for one test.

## Consequences

- Fixture difficulty ratings in vaastav are end-of-season values; features must not use them
  until a point-in-time source exists.
- CI runs `dbt build` on empty raw tables. That catches SQL and schema errors, not data errors.
