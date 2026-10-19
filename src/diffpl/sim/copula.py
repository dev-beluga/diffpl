"""Joint points simulation: champion marginals with the event model's dependence (ADR-0009).

The event model (B) simulates whole fixtures, so its draws are consistent across teammates
and opponents, but its per-player distributions are less accurate than the champion's (A).
`match_marginals` keeps B's ranks in every player's column and swaps in A's quantiles: an
empirical copula. Each player's distribution becomes A's; the rank dependence between
players stays B's.
"""

from __future__ import annotations

import numpy as np


def match_marginals(
    sims: np.ndarray, dist: np.ndarray, values: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Map each column of `sims` (draws x players) onto the matching row of `dist`
    (players x bins) by rank. Ties are broken at random, so a player whose B draws are all
    0 gets A's marginal with no dependence. `values` gives the points per bin."""
    n = sims.shape[0]
    order = np.lexsort((rng.random(sims.shape), sims), axis=0)
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(n)[:, None], axis=0)
    u = (ranks + 0.5) / n
    cdf = np.cumsum(dist, axis=1)[:, :-1]  # players x (bins - 1)
    bins = (u[:, :, None] > cdf[None, :, :]).sum(axis=2)
    return np.asarray(values[bins])


def shuffle_columns(sims: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Same marginals, no dependence: the independence baseline."""
    return np.asarray(rng.permuted(sims, axis=0))
