import numpy as np

from diffpl.sim.__main__ import crps, score_teams
from diffpl.sim.copula import match_marginals, shuffle_columns


def test_match_marginals_takes_champion_marginals_and_keeps_event_ranks() -> None:
    rng = np.random.default_rng(0)
    n = 20000
    shared = rng.poisson(1.5, n)
    sims = np.stack([shared + rng.poisson(0.3, n), shared + rng.poisson(0.3, n)], axis=1)
    dist = np.array([[0.5, 0.3, 0.2], [0.1, 0.1, 0.8]])
    values = np.array([0.0, 2.0, 6.0])
    out = match_marginals(sims.astype(float), dist, values, rng)
    for j in range(2):
        freq = np.array([(out[:, j] == v).mean() for v in values])
        assert np.allclose(freq, dist[j], atol=0.01)
    assert np.corrcoef(out.T)[0, 1] > 0.25  # dependence survives (shuffled is ~0)
    indep = shuffle_columns(out, rng)
    assert abs(np.corrcoef(indep.T)[0, 1]) < 0.03
    assert np.allclose(np.sort(indep, axis=0), np.sort(out, axis=0))


def test_all_tied_column_gets_marginal_without_dependence() -> None:
    rng = np.random.default_rng(1)
    sims = np.zeros((10000, 1))
    out = match_marginals(sims, np.array([[0.25, 0.75]]), np.array([0.0, 1.0]), rng)
    assert abs(out.mean() - 0.75) < 0.02


def test_crps_is_zero_for_a_perfect_point_mass_and_grows_with_error() -> None:
    assert crps(np.full(100, 3.0), 3.0) == 0
    rng = np.random.default_rng(0)
    s = rng.normal(0, 1, 20000)
    assert abs(crps(s, 0.0) - 0.2337) < 0.01  # closed form for N(0, 1) at its mean
    assert crps(s, 3.0) > crps(s, 0.0)


def test_team_totals_reward_dependence_when_teammates_move_together() -> None:
    rng = np.random.default_rng(0)
    seasons = 400
    rows = []
    for _ in range(seasons):
        good = rng.random() < 0.5
        actual = np.full(4, 6.0 if good else 1.0)
        draws = rng.random(2000) < 0.5
        joint = np.where(draws[:, None], 6.0, 1.0) * np.ones((1, 4))
        joints = {"joint": joint, "independent": shuffle_columns(joint, rng)}
        rows += score_teams(["T"] * 4, actual, joints)
    mean = {
        m: np.mean([r["crps"] for r in rows if r["method"] == m]) for m in ("joint", "independent")
    }
    assert mean["joint"] < mean["independent"]
