import numpy as np
import polars as pl

from diffpl.models import events
from diffpl.rules import load_rules
from diffpl.scoring import MatchStats, player_points


def test_base_points_match_scoring_rules() -> None:
    rules = load_rules("2024-25")
    table = events.base_points(rules)
    full = MatchStats(minutes=90, goals_scored=1, assists=1, clean_sheets=1)
    assert table["DEF"][2, 1, 1, 0] == player_points(rules, "DEF", full)
    assert table["DEF"][2, 0, 0, 0] > table["DEF"][2, 0, 0, 2]  # clean sheet beats 2 conceded
    assert table["MID"][0].max() == 0  # no minutes, no points


def test_allocate_never_gives_more_events_than_team_goals() -> None:
    rng = np.random.default_rng(0)
    goals = rng.poisson(1.5, 5000)
    weights = np.tile([0.3, 0.2, 0.1], (5000, 1))
    out = events._allocate(goals, weights, rng)
    assert (out.sum(axis=1) <= goals).all()
    share = out.sum(axis=0) / goals.sum()
    assert np.allclose(share, [0.3, 0.2, 0.1], atol=0.02)
    full = events._allocate(goals, np.tile([0.7, 0.6], (5000, 1)), rng)
    assert (full.sum(axis=1) == goals).all()  # weights above 1 are normalized


def test_sample_classes_follow_probabilities() -> None:
    rng = np.random.default_rng(0)
    probs = np.array([[0.2, 0.3, 0.5], [1.0, 0.0, 0.0]])
    mc = events._sample_classes(probs, rng)
    assert mc.shape == (events.N_SIMS, 2)
    assert np.allclose(np.bincount(mc[:, 0], minlength=3) / events.N_SIMS, probs[0], atol=0.03)
    assert (mc[:, 1] == 0).all()


def test_team_model_ranks_the_strong_attack_first() -> None:
    rng = np.random.default_rng(0)
    teams = ["A", "B", "C", "D"]
    rows = []
    for _ in range(40):
        for h in teams:
            for a in teams:
                if h != a:
                    rate = 2.5 if h == "A" else 1.0
                    rows.append((h, a, rng.poisson(rate), rng.poisson(2.5 if a == "A" else 1.0)))
    matches = pl.DataFrame(rows, schema=["home", "away", "hg", "ag"], orient="row").with_columns(
        pl.col("hg", "ag").cast(pl.Float64), weight=pl.lit(1.0)
    )
    idx, draws = events.fit_teams(matches, seed=0)
    att = draws["att"].mean(axis=0)
    assert att[idx["A"]] == max(att[idx[t]] for t in teams)
    assert draws["att"].shape[0] == events.N_DRAWS
