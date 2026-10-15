"""Replay manager that ranks players by a projection model's expected points.

Uses the same greedy policy as the baselines (diffpl.replay.baselines), so a points
difference in the replay comes from the projections alone.
"""

from __future__ import annotations

from diffpl.features.build import gw_features
from diffpl.models.two_part import TwoPartModel
from diffpl.replay.baselines import GreedyManager
from diffpl.replay.data import Observation
from diffpl.rules import Rules


def model_manager(name: str, model: TwoPartModel, rules: Rules) -> GreedyManager:
    def score(obs: Observation) -> dict[int, float]:
        feats = gw_features(obs)
        exp = model.expected_points(model.predict_dist(feats))
        return dict(zip(feats["element_id"].to_list(), exp.tolist(), strict=True))

    return GreedyManager(name, rules, score)
