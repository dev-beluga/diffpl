# ADR-0006: Projection models, two-part LightGBM champion then Bayesian challenger

Status: accepted
Date: 2026-10-15

## Context

Phase 2 needs a points distribution per player per GW, built only from data before the
deadline, scored for calibration and in the replay env.

## Decision

- Features are computed only from the replay `Observation` (ADR-0004), so a feature cannot
  see past the deadline. Targets (points, minutes) come from the season data. The
  poisoned-future test covers every feature.
- Champion (A): a minutes classifier (0, 1-59, 60+) and a points regressor conditioned on the
  minutes class, mixed into a discrete points distribution.
- Challenger (B): a Bayesian event model (NumPyro) over minutes, goals, assists, clean sheets
  and bonus, simulated through `diffpl.scoring`. It replaces A only if it wins on held-out
  seasons.
- Splits: train 2021-22 and 2022-23, validate 2023-24, test 2024-25 and 2025-26.
- Metrics: CRPS, log loss over points bins, calibration curves, MAE against the form baseline,
  split by position. Every run is logged in MLflow with dataset version and params.
- Calibration report (`diffpl.models.calibration`): reliability and ECE for P(60+ minutes)
  and P(points >= 1, 2, 6, 10); randomized PIT histogram for the full distribution; 50% and
  80% central interval coverage read off the PIT, so discrete bins do not inflate it. Split by
  position, seeded, logged to MLflow as metrics, CSVs and PNGs.

## Alternatives considered

- Quantile regression only: cheap, but quantiles can cross and there are no joint outcomes
  for the simulator.

## Consequences

- A ships first and sets the bar. B costs more to build and must earn promotion.
