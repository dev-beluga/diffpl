"""Promotion gate: a challenger replaces the champion only if it passes every check (ADR-0007).

Inputs are what `train` logs per run: per-row RPS on the test seasons, metrics (ECE,
coverage, per-position RPS) and replay totals per test season.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

BOOTSTRAP = 1000
CI = 0.95
POSITION_RPS_TOLERANCE = 0.005  # per-position RPS may not get worse by more than this
MAX_ECE = 0.03
COVERAGE_TOLERANCE = 0.02
REPLAY_TOLERANCE = 20  # points per season the challenger's manager may trail by
POSITIONS = ("ALL", "DEF", "FWD", "GKP", "MID")
EVENTS = ("p60", "pts_ge1", "pts_ge2", "pts_ge6", "pts_ge10")
LEVELS = (50, 80)


@dataclass
class Decision:
    passed: bool = True
    reasons: list[str] = field(default_factory=list)

    def check(self, ok: bool, reason: str) -> None:
        self.reasons.append(f"{'PASS' if ok else 'FAIL'} {reason}")
        self.passed &= ok


def paired_bootstrap(
    champion: pl.DataFrame, challenger: pl.DataFrame, seed: int
) -> tuple[float, float, float]:
    """Mean RPS difference (challenger - champion) and its CI, resampling whole GWs.

    Both frames hold season, gw, element_id, rps. Rows in the same GW share fixtures, so
    resampling GWs keeps their correlation.
    """
    keys = ["season", "gw", "element_id"]
    d = champion.join(challenger, on=keys, suffix="_ch").with_columns(
        diff=pl.col("rps_ch") - pl.col("rps")
    )
    blocks = d.group_by("season", "gw").agg(pl.col("diff").sum(), pl.len())
    s, n = blocks["diff"].to_numpy(), blocks["len"].to_numpy()
    idx = np.random.default_rng(seed).integers(0, len(s), (BOOTSTRAP, len(s)))
    means = s[idx].sum(axis=1) / n[idx].sum(axis=1)
    lo, hi = np.quantile(means, [(1 - CI) / 2, 1 - (1 - CI) / 2])
    return float(s.sum() / n.sum()), float(lo), float(hi)


def decide(
    champion_scores: pl.DataFrame,
    challenger_scores: pl.DataFrame,
    champion_metrics: dict[str, float],
    challenger_metrics: dict[str, float],
    seasons: tuple[str, ...],
    seed: int,
) -> Decision:
    d = Decision()
    mean, lo, hi = paired_bootstrap(champion_scores, challenger_scores, seed)
    d.check(hi < 0, f"RPS diff {mean:+.4f}, {CI:.0%} CI [{lo:+.4f}, {hi:+.4f}] below 0")
    for pos in POSITIONS:
        key = f"two_part.{pos}.rps"
        delta = challenger_metrics[key] - champion_metrics[key]
        d.check(delta <= POSITION_RPS_TOLERANCE, f"{pos} RPS change {delta:+.4f}")
        worst = max(challenger_metrics[f"two_part.{pos}.ece_{e}"] for e in EVENTS)
        d.check(worst <= MAX_ECE, f"{pos} worst ECE {worst:.4f} <= {MAX_ECE}")
        for level in LEVELS:
            cov = challenger_metrics[f"two_part.{pos}.coverage{level}"]
            ok = abs(cov - level / 100) <= COVERAGE_TOLERANCE
            d.check(ok, f"{pos} {level}% coverage {cov:.3f}")
    for season in seasons:
        key = f"replay.{season}.total_points"
        gap = challenger_metrics[key] - champion_metrics[key]
        d.check(gap >= -REPLAY_TOLERANCE, f"{season} replay points {gap:+.0f}")
    return d
