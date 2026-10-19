# ADR-0009: Joint simulation with champion marginals and event-model dependence

Status: accepted
Date: 2026-10-19

## Context

Phase 3 needs joint draws of every player's GW points: the planner and the rank-aware
objective care about stacks, captaincy risk and effective ownership, which all depend on
how teammates and opponents move together. The champion (A, ADR-0006) has the best
per-player distributions but no joint structure. The event model (B, ADR-0008) simulates
whole fixtures, so its draws are consistent, but its marginals lose to A.

## Decision

Combine them with an empirical copula (`diffpl.sim`):

- B simulates the GW (`EventModel.predict` now returns its joint draws).
- For each player, B's draws are ranked (ties broken at random) and replaced by A's quantile
  at the same rank. Each player's marginal becomes A's; the rank dependence stays B's.
- A player whose B draws are all equal (no fixture, never plays) gets A's marginal with no
  dependence.

Evaluation (`python -m diffpl.sim eval`): per-player scores cannot see dependence, so the
test is each team's total points per GW on the test seasons, scored by sample CRPS and 50% /
80% interval coverage. Three joint models are compared: independent (A's marginals,
shuffled), B's own draws, and the hybrid. The hybrid is used only if it beats both.

## Alternatives considered

- A's marginals sampled independently: the most accurate per player, but team totals are
  too narrow, and stacking risk is invisible.
- B's draws as they are: correct structure, weaker marginals.

## Consequences

- Each GW's simulation needs both models and one team-model fit (about 2 seconds on CPU).
- The dependence is only as good as B's: the copula keeps B's ranks, so if B misorders
  outcomes within a fixture, the hybrid inherits it.
- Random tie breaking weakens dependence for players with few distinct B outcomes (most
  draws at 0 or 1 points).

## Results (2026-10-19)

Team totals, 1520 team-GWs on 2024-25 and 2025-26 (events v5, champion v3):

| Joint model | CRPS | 50% coverage | 80% coverage |
|---|---|---|---|
| events | 9.692 | 0.530 | 0.815 |
| hybrid | 9.892 | 0.491 | 0.778 |
| independent | 10.291 | 0.324 | 0.566 |

- Dependence matters: independent team totals are far too narrow (80% interval holds 57%).
- The hybrid does not beat the event model's own draws, so by the rule above the simulator
  uses B's draws for now. Likely cause: random tie breaking drops dependence for players
  whose B draws are mostly 0 or 1 points.
