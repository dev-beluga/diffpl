"""Simulate a GW's points jointly for every player with a price at the deadline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from diffpl.features.build import gw_features
from diffpl.models.events import EventModel
from diffpl.models.two_part import TwoPartModel
from diffpl.replay.data import Observation, SeasonData
from diffpl.rules import Rules
from diffpl.sim.copula import match_marginals


@dataclass
class Joint:
    element_id: np.ndarray
    team: list[str]
    sims: np.ndarray  # draws x players, the event model's joint points (ADR-0009 results)
    hybrid: np.ndarray  # draws x players, champion marginals with event-model dependence


def simulate(
    obs: Observation,
    champion: TwoPartModel,
    events: EventModel,
    prev: SeasonData | None,
    rules: Rules,
    seed: int,
) -> Joint:
    p = events.predict(obs, prev, rules)
    feats = gw_features(obs)
    row = {e: i for i, e in enumerate(feats["element_id"].to_list())}
    dist = champion.predict_dist(feats)[[row[e] for e in p.element_id.tolist()]]
    assert champion.bin_values is not None
    rng = np.random.default_rng([seed, obs.gw])
    hybrid = match_marginals(p.sims, dist, champion.bin_values, rng)
    return Joint(p.element_id, p.team, p.sims, hybrid)
