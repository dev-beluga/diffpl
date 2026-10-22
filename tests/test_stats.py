"""Stats: per-90 player numbers, team xG from player xG, and the fixture ticker."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from diffpl.api.stats import fixture_ticker, player_matches, player_table, ratings, team_form
from diffpl.replay.data import SeasonData

T0 = datetime(2026, 8, 15, 15, tzinfo=UTC)
SHORT = {"Alpha": "ALP", "Beta": "BET"}


def season() -> SeasonData:
    """Two teams, two finished fixtures (Alpha home then away) and one upcoming in GW3.
    Player 1 (Alpha FWD) has 1.0 xG per match; player 2 (Beta MID) 0.5 xG and 0.2 xA."""
    kick = [T0, T0 + timedelta(days=7)]
    rows = [
        (1, "Alpha", 1, 1, kick[0], True, 2, 90, 8, 1.0, 0.0),
        (2, "Beta", 1, 1, kick[0], False, 1, 90, 3, 0.5, 0.2),
        (1, "Alpha", 2, 2, kick[1], False, 2, 45, 2, 1.0, 0.0),
        (2, "Beta", 2, 2, kick[1], True, 1, 90, 5, 0.5, 0.2),
    ]
    cols = [
        "element_id",
        "team_name",
        "fixture_id",
        "gw",
        "kickoff_time",
        "was_home",
        "opponent_team_id",
        "minutes",
        "total_points",
        "expected_goals",
        "expected_assists",
    ]
    pm = pl.DataFrame([dict(zip(cols, r, strict=True)) for r in rows])
    return SeasonData(
        season="2026-27",
        deadlines=pl.DataFrame({"gw": [1, 2, 3], "deadline_time": [T0, T0, T0]}),
        player_matches=pm,
        prices=pl.DataFrame({"element_id": [1, 2], "price_tenths": [80, 60], "as_of": [T0, T0]}),
        fixtures=pl.DataFrame(
            {
                "fixture_id": [1, 2, 3],
                "gw": [1, 2, 3],
                "kickoff_time": [kick[0], kick[1], kick[1] + timedelta(days=7)],
                "home_team_id": [1, 2, 1],
                "away_team_id": [2, 1, 2],
                "home_score": [2, 0, None],
                "away_score": [1, 1, None],
            }
        ),
        players=pl.DataFrame(
            {"element_id": [1, 2], "player_name": ["Ace", "Bee"], "position": ["FWD", "MID"]}
        ),
        teams=pl.DataFrame({"team_id": [1, 2], "team_name": ["Alpha", "Beta"]}),
    )


def test_player_table_per_90_and_form() -> None:
    rows = {r.element_id: r for r in player_table(season(), SHORT, {1: 12.5})}
    ace = rows[1]
    assert ace.team == "ALP" and ace.price == 8.0 and ace.ownership == 12.5
    assert ace.minutes == 135 and ace.points == 10 and ace.form == 5.0
    assert ace.xg90 == pytest.approx(2.0 * 90 / 135, abs=0.01)
    assert rows[2].xgi90 == pytest.approx(0.7, abs=0.01) and rows[2].ownership == 0.0


def test_team_form_sums_player_xg_and_reads_goals_from_fixtures() -> None:
    form = {t.team: t for t in team_form(season(), SHORT)}
    assert form["ALP"].xg_for == 1.0 and form["ALP"].xg_against == 0.5
    assert form["ALP"].goals_for == 1.5 and form["ALP"].goals_against == 0.5
    assert form["BET"].matches == 2


def test_ratings_shrink_toward_average_and_ticker_uses_them() -> None:
    avg, att, _ = ratings(season())
    assert avg == pytest.approx(0.75)
    assert 1 < att["Alpha"] < 1.0 / 0.75  # above average, pulled toward 1
    ticker = {r.team: r.fixtures for r in fixture_ticker(season(), 3, 6, SHORT)}
    (alp,) = ticker["ALP"]
    assert alp.gw == 3 and alp.opponent == "BET" and alp.home
    assert alp.xg_for > alp.xg_against  # stronger attack against a weaker defence
    assert ticker["BET"][0].xg_for == alp.xg_against


def test_player_matches_list_in_kickoff_order() -> None:
    m = player_matches(season(), 1, {1: "ALP", 2: "BET"})
    assert [(x.gw, x.opponent, x.home, x.points) for x in m] == [
        (1, "BET", True, 8),
        (2, "BET", False, 2),
    ]
