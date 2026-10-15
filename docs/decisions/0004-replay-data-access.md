# ADR-0004: Replay env gives managers filtered in-memory snapshots

Status: accepted
Date: 2026-10-15

## Context

The Season Replay Env must let any manager (heuristic, ML, solver, LLM agent) decide each GW
using only data with `as_of` before that GW's deadline. Leakage here would invalidate every
result the project reports.

## Decision

- The env loads a season once into Polars frames from dbt staging and marts.
- Before each deadline it builds an immutable `Observation`: every frame filtered to
  `as_of < deadline`, plus the manager's squad, bank, free transfers and chips.
- Managers implement `act(obs: Observation) -> Decision`. They get no database handle.
- A pure rules engine validates and applies the decision, auto-subs and scores with
  `diffpl.scoring` and `config/rules/<season>.yaml`.
- Two leakage tests: no observation frame holds a row with `as_of >= deadline`; and a
  poisoned-future test injects impossible future rows and asserts decisions do not change.

## Alternatives considered

- Query gateway (managers query through a handle that adds the filter): raw queries can
  bypass it, and per-decision database round trips are slow.
- Per-GW Parquet snapshots: most auditable, but heavier to build and version. Can be added
  later as a cache of the same observations if agents need on-disk audit trails.

## Consequences

- Speed comes from memory; a season fits easily (about 30k player-match rows).
- Seasons 2021-22 to 2025-26 are available, with player scoring verified exactly.
