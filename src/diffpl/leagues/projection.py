"""Projected final standings for a mini-league by Monte Carlo (ADR-0005).

Version A, deliberately rough: each manager's remaining gameweeks are resampled from their own
scores so far, mixed with the league's pooled scores while their history is short. It ignores
squads, fixtures and chips. Replace with squad-level calibrated projections in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from diffpl.leagues.rules import EntryGw, GwOutcome, LeagueRules

SEASON_GWS = 38
METHOD = "bootstrap of each manager's own GW scores, shrunk to the league pool (rough)"


@dataclass(frozen=True)
class Projection:
    entry_id: int
    current: int
    expected_final: float
    p_win: float
    p_top3: float


def overall_contributions(
    rules: LeagueRules, outcomes: list[GwOutcome], rows: list[EntryGw]
) -> dict[int, list[int]]:
    """Each manager's per-GW contribution to the overall table, under the league's rules."""
    official = {(r.entry_id, r.gw): r.points - r.hit_cost for r in rows}
    out: dict[int, list[int]] = {}
    for o in sorted(outcomes, key=lambda o: o.gw):
        use_league = rules.for_gw(o.gw).overall == "league_score"
        for s in o.scores:
            pts = s.score if use_league else official[(s.entry_id, s.gw)]
            out.setdefault(s.entry_id, []).append(pts)
    return out


def project(
    contributions: dict[int, list[int]],
    gws_left: int,
    *,
    n_sims: int = 10_000,
    prior_weight: float = 5.0,
    seed: int = 42,
) -> list[Projection]:
    """Simulate `gws_left` more gameweeks. A manager with n past GWs draws from their own
    history with probability n / (n + prior_weight), else from the league pool."""
    entries = sorted(contributions)
    if not entries:
        return []
    rng = np.random.default_rng(seed)
    pool = np.concatenate([np.asarray(contributions[e]) for e in entries])
    current = np.array([sum(contributions[e]) for e in entries])
    finals = np.tile(current, (n_sims, 1)).astype(float)
    if gws_left > 0:
        for j, e in enumerate(entries):
            own = np.asarray(contributions[e])
            p_own = len(own) / (len(own) + prior_weight)
            use_own = rng.random((n_sims, gws_left)) < p_own
            draws = np.where(
                use_own,
                rng.choice(own, size=(n_sims, gws_left)),
                rng.choice(pool, size=(n_sims, gws_left)),
            )
            finals[:, j] += draws.sum(axis=1)
    # Rank 0 is first; ties share the better rank. Ties for first split the title.
    order = (-finals).argsort(axis=1).argsort(axis=1)
    best = finals.max(axis=1, keepdims=True)
    winners = finals == best
    win_share = winners / winners.sum(axis=1, keepdims=True)
    return [
        Projection(
            entry_id=e,
            current=int(current[j]),
            expected_final=float(finals[:, j].mean()),
            p_win=float(win_share[:, j].mean()),
            p_top3=float((order[:, j] < 3).mean()),
        )
        for j, e in enumerate(entries)
    ]
