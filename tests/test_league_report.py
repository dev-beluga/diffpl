import polars as pl

from diffpl.leagues.report import LeagueData, exposure, weekly_outcomes
from diffpl.leagues.rules import LeagueRules, default_rules


def league() -> LeagueData:
    # Two managers, GW1. Entry 1 captains player 10; entry 2 owns 10 and 20.
    picks = pl.DataFrame(
        {
            "entry_id": [1, 1, 2, 2],
            "gw": [1, 1, 1, 1],
            "element_id": [10, 30, 10, 20],
            "multiplier": [2, 1, 1, 1],
        }
    )
    ownership = pl.DataFrame(
        {
            "gw": [1, 1, 1],
            "element_id": [10, 20, 30],
            "ownership": [1.0, 0.5, 0.5],
            "effective_ownership": [1.5, 0.5, 0.5],
            "captains": [1, 0, 0],
        }
    )
    gameweeks = pl.DataFrame(
        {
            "entry_id": [1, 2],
            "gw": [1, 1],
            "points": [70, 65],
            "hit_cost": [8, 0],
            "transfers": [3, 1],
            "total_points": [62, 65],
            "chip": [None, None],
        }
    )
    return LeagueData(
        league_id=1,
        managers=pl.DataFrame({"entry_id": [1, 2], "entry_name": ["A", "B"]}),
        ownership=ownership,
        gameweeks=gameweeks,
        picks=picks,
        names=pl.DataFrame({"element_id": [10, 20, 30], "web_name": ["X", "Y", "Z"]}),
    )


def test_exposure_marks_differentials_and_threats() -> None:
    ex = exposure(league(), entry_id=1, gw=1)
    by = dict(zip(ex["element_id"], ex["exposure"], strict=True))
    assert by == {10: 0.5, 30: 0.5, 20: -0.5}


def test_weekly_outcomes_follow_league_rules() -> None:
    data = league()
    _, official = weekly_outcomes(data, default_rules(1))
    assert official == {1: 62, 2: 65}
    house = LeagueRules.model_validate(
        {
            "league_id": 1,
            "name": "h",
            "versions": [
                {
                    "effective_from_gw": 1,
                    "steps": [
                        {"type": "adjust_hits", "mode": "ignore_up_to", "limit": 8},
                        {"type": "winner"},
                    ],
                }
            ],
        }
    )
    outcomes, overall = weekly_outcomes(data, house)
    assert outcomes[0].winners == [1]
    assert overall == {1: 62, 2: 65}  # overall stays official unless the league opts in
