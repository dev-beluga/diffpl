import pytest

from diffpl.leagues.projection import overall_contributions, project
from diffpl.leagues.rules import EntryGw, LeagueRules, default_rules, score_gameweek


def test_probabilities_are_coherent() -> None:
    proj = project({1: [60, 70, 65], 2: [55, 60, 58], 3: [50, 52, 51]}, gws_left=10, n_sims=4000)
    assert sum(p.p_win for p in proj) == pytest.approx(1.0)
    assert sum(p.p_top3 for p in proj) == pytest.approx(3.0)
    assert proj[0].p_win > proj[1].p_win > proj[2].p_win


def test_season_over_is_deterministic() -> None:
    proj = project({1: [60, 70], 2: [80, 50]}, gws_left=0, n_sims=100)
    assert [p.p_win for p in proj] == [0.5, 0.5]  # tied on 130: shared title
    assert [p.expected_final for p in proj] == [130.0, 130.0]


def test_big_lead_late_is_near_certain() -> None:
    proj = project({1: [100] * 36, 2: [50] * 36}, gws_left=2, n_sims=2000)
    assert proj[0].p_win > 0.999


def test_same_seed_same_answer() -> None:
    data = {1: [60, 72, 41], 2: [58, 66, 70]}
    assert project(data, 20, seed=7) == project(data, 20, seed=7)


def test_contributions_follow_overall_rule() -> None:
    rows = [EntryGw(1, 1, 70, 8), EntryGw(2, 1, 65, 0)]
    league = LeagueRules.model_validate(
        {
            "league_id": 1,
            "name": "h",
            "versions": [
                {
                    "effective_from_gw": 1,
                    "overall": "league_score",
                    "steps": [{"type": "adjust_hits", "mode": "ignore_all"}, {"type": "winner"}],
                }
            ],
        }
    )
    official = default_rules(1)
    assert overall_contributions(official, [score_gameweek(official, rows)], rows) == {
        1: [62],
        2: [65],
    }
    assert overall_contributions(league, [score_gameweek(league, rows)], rows) == {1: [70], 2: [65]}
