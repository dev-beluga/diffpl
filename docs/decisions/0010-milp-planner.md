# ADR-0010: Multi-GW MILP planner on expected points

Status: accepted
Date: 2026-10-19

## Context

Phase 3 needs a planner that chooses transfers, hits and the XI over several GWs. The greedy
baselines make at most one free transfer per GW and never plan ahead. The rank-aware objective
comes later and needs candidate plans to score with simulated outcomes (ADR-0009).

Options considered:

- A. Deterministic MILP on expected points over a horizon.
- B. Sample-average MILP over K joint simulator draws. Larger and slower; a linear average
  over draws equals the mean for squad terms, so the gain is mostly captaincy and bench.
- C. A as the core solver, then a rank-aware layer that rescores the top N plans with
  simulated draws and effective ownership.

Chosen: C. This ADR covers its first half, A. The rank-aware layer gets its own ADR.

## Decision

`diffpl.optim.planner.plan` builds one MILP per deadline and solves it with HiGHS (`highspy`):

- Horizon: next 4 GWs, weight 0.85^t for GW t. Only the first GW's transfers are played
  (rolling horizon).
- Variables per player and GW: in squad, starts, captain, bought, sold. Per GW: bank, free
  transfers, hits.
- Objective: starters' points + captain's points + 0.1 x bench points - 4 x hits.
- Constraints: squad shape, formation, 3 per club (or the current count, if a moved player
  left the squad over), bank >= 0 with FPL selling prices, free-transfer rollover capped at
  `max_banked`, hits >= transfers - free transfers. Special events from the rules config
  (unlimited-transfer GW, free-transfer top-up) are modelled.
- Prices stay fixed at the deadline across the horizon. No chips.
- Pruning: owned players, the top 25 per position by horizon points, the 3 cheapest per
  position. About 110 players.
- Input is any `Projection` (gw -> player -> expected points). `fixture_horizon` turns a
  next-GW scorer into one: points per match times each GW's match count. This lets the
  champion and the baselines drive the planner without a model change.
- XI, bench order and captain for the played GW come from `best_lineup` on the first GW's
  projection, the same choice the MILP valued.

## Evaluation

`python -m diffpl.models replay` now replays the test seasons with the planner next to the
greedy two-part manager and the baselines. Both model managers use the two-part
projections (seed fixed in settings).

| Season  | planner | two_part (greedy) | template | form | fixtures |
|---------|---------|-------------------|----------|------|----------|
| 2024-25 | 2186    | 2081              | 2087     | 2025 | 2042     |
| 2025-26 | 2195    | 2108              | 1984     | 1821 | 1816     |

The planner beats the greedy manager on the same projections by 105 and 87 points, with no
rule violations. The whole replay command, including training, took 8 min 50 s; solve time
per deadline was not measured separately. HiGHS prints harmless `HighsProfiling` clock
warnings to stderr during the run.

## Consequences

- The planner reuses one-GW projections for later GWs. Fixture difficulty beyond the next GW
  is invisible until a model projects future GWs directly.
- A deterministic objective is risk-neutral. Variance and rank goals are the next step (C).
- Tests (`tests/test_planner.py`) check legal squads, budget, hits only when they pay,
  banking a free transfer for a later double move, and the poisoned-future leakage test.
