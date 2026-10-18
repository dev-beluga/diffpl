# ADR-0007: Model registry and promotion gate

Status: accepted
Date: 2026-10-18

## Context

CLAUDE.md requires that a challenger replaces the champion only if it wins on the replay
and eval harness across held-out seasons. Phase 2 needs a registry and a gate that applies
this rule the same way every time.

## Decision

- Every `models train` run registers a version of the MLflow model `projections`. The first
  version gets the alias `champion`; later versions get `challenger`.
- Each run logs what the gate needs, so promotion never retrains: per-row RPS on the test
  seasons (`scores.parquet`), per-position RPS, ECE and coverage, and the model-driven
  manager's replay total per test season.
- `models promote` compares the challenger with the champion (`diffpl.models.gate`). The
  challenger passes only if every check passes:
  - the 95% CI of the mean RPS difference, from a paired bootstrap that resamples whole GWs,
    is below 0;
  - no position's RPS gets worse by more than 0.005;
  - the worst ECE per position is at most 0.03;
  - 50% and 80% coverage are within 0.02 of nominal;
  - replay points trail the champion by at most 20 per test season.
- The result goes on the challenger as tags `gate`, `gate_vs` and `gate_reasons`. A pass moves
  the `champion` alias and removes `challenger`.

## Alternatives considered

- Metric gate only: cheaper, but it breaks the rule that replay counts.
- Rolling-origin seasons (retrain per held-out season): more honest, about twice the training
  cost. Revisit when challenger B exists.

## Consequences

- One replay per season is a single noisy run, so the replay check is a tolerance, not a
  strict win. The RPS bootstrap carries the significance test.
- Metric keys use the `two_part` prefix. Challenger B must log under the same keys, or the
  gate must read the model name from the run params.
- Thresholds are constants in `gate.py`. Changing one is a model-policy change and needs an
  ADR update.
