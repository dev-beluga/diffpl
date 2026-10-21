# ADR-0011: Rank-aware planner, P(beat a rival)

Status: rejected (failed its eval gate on 2024-25; kept on branch phase3-rank-aware)
Date: 2026-10-20

## Context

The MILP planner (ADR-0010) maximizes expected points. A mini-league manager wants to beat
specific rivals, and the variance of a plan matters relative to the rival's squad: a
template-heavy squad tracks the rival, differentials swing away from them. ADR-0010 chose
option C: the MILP proposes, a rank-aware layer scores with simulated outcomes.

Objectives considered: P(beat a named rival), P(reach a rank threshold), expected utility with
a risk setting. Chosen: P(beat a named rival). It needs only the rival's squad, uses the
league's own rules, and is the simplest to validate.

## Decision

`diffpl.optim.rival`:

- The MILP returns up to 10 plans with distinct first-GW squads (no-good cuts), best EV first.
- For each plan and each joint draw (ADR-0009, champion marginals with event-model
  dependence): my first-GW points (XI plus captain) minus the rival's, with hits counted by
  the league's rules (ADR-0005; ineligible means the GW cannot be won). Later GWs add each
  side's weighted expected points: the plan's MILP value for me, the rival's current squad
  held unchanged for them.
- P(beat) is the share of draws with a positive margin, ties counting half. The plan with the
  highest P(beat) is played; ties go to the higher EV plan. With no rival known, the EV plan.

Simplifications, each a known bias:

- Only the first GW is random; later GWs are means.
- The rival makes no transfers, while my plan may. This favours my side by a similar amount
  in every plan, so it shifts P(beat) more than it changes the ranking.
- No auto-subs inside the draws (the simulator gives points, not minutes).
- The initial squad is the EV plan.

## Live use

Same live path as ADR-0010, plus a rival picker: the rival's last lineup and captain come from
the league ingest, and each plan shows its P(beat rival).

## Evaluation

`python -m diffpl.optim eval` replays the test seasons. History has no real rivals, so the
rival is the greedy champion manager playing the same season, and the rank-aware planner sees
its decision from the previous GW. The EV planner and the rank-aware planner face it head to
head: share of GWs won and season points. Results are logged to MLflow (`planner_eval`) and
shown in the dashboard's Planner tab.

Results (champion v3, event model v5, seed 42, horizon 4; MLflow run `planner_eval`):

| Season  | Manager    | Points | Rival points | h2h   | Hits |
|---------|------------|--------|--------------|-------|------|
| 2024-25 | planner    | 2167   | 2081         | 0.618 | 136  |
| 2024-25 | rank_aware | 2159   | 2081         | 0.579 | 120  |
| 2025-26 | planner    | 2195   | 2108         | 0.513 | 76   |
| 2025-26 | rank_aware | 2193   | 2108         | 0.526 | 76   |

The gate needed a higher head-to-head win rate in both seasons. Rank-aware loses 2024-25 by
0.039 and wins 2025-26 by 0.013, at a cost of 8 and 2 points. Not better than the EV planner,
so it stays off main.

Likely causes, to test before a retry:

- The objective is the horizon total (4 GWs), but the metric is single-GW wins. Most of the
  margin is the deterministic later-GW part, so P(beat) mostly tracks EV and the few overrides
  are noise.
- Only the first GW is random, and the held-rival assumption adds the same bias to every plan.
- One rival and two seasons: a 0.04 gap is about 1.5 GWs, inside the noise of 37 GWs.

Next options: score P(win this GW) to match the metric, or use the draws for captaincy only.

The EV planner here scores 2167 in 2024-25, not ADR-0010's 2186: this eval loads the registry
champion, while ADR-0010's replay trained a fresh two-part model.

## Consequences

- Each deadline needs one joint simulation and up to 10 MILP solves.
- Rival modeling (Phase 7) can replace the held-squad assumption without changing the scorer.
- The objective is per-horizon, while many leagues pay per GW. A per-GW prize objective is a
  later variant.
