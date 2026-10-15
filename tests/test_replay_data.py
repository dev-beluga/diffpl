"""Leakage tests for replay observations (ADR-0004)."""

import os
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError

from diffpl.replay.data import Observation, SeasonData, load_season

T0 = datetime(2024, 8, 16, 18, 30, tzinfo=UTC)
D1, D2 = T0, T0 + timedelta(days=7)


def season() -> SeasonData:
    kick1 = D1 + timedelta(hours=1)
    kick2 = D2 + timedelta(hours=1)
    return SeasonData(
        season="2024-25",
        deadlines=pl.DataFrame({"gw": [1, 2], "deadline_time": [D1, D2]}),
        player_matches=pl.DataFrame(
            {
                "element_id": [1, 1],
                "gw": [1, 2],
                "total_points": [2, 15],
                "as_of": [kick1 + timedelta(hours=3), kick2 + timedelta(hours=3)],
            }
        ),
        prices=pl.DataFrame(
            {
                "gw": [1, 2],
                "element_id": [1, 1],
                "price_tenths": [50, 51],
                "as_of": [D1 - timedelta(minutes=1), D2 - timedelta(minutes=1)],
            }
        ),
        fixtures=pl.DataFrame(
            {
                "fixture_id": [10, 20],
                "gw": [1, 2],
                "home_score": [2, 4],
                "away_score": [0, 1],
                "finished": [True, True],
                "result_as_of": [kick1 + timedelta(hours=3), kick2 + timedelta(hours=3)],
            }
        ),
        players=pl.DataFrame({"element_id": [1], "player_name": ["A"], "position": ["MID"]}),
    )


def test_first_gw_sees_no_matches_but_sees_its_price() -> None:
    obs = season().observe(1)
    assert obs.player_matches.is_empty()
    assert obs.prices["price_tenths"].to_list() == [50]


def test_second_gw_sees_only_first_match() -> None:
    obs = season().observe(2)
    assert obs.player_matches["total_points"].to_list() == [2]
    assert obs.prices["price_tenths"].to_list() == [50, 51]


def test_future_results_are_masked_but_schedule_is_visible() -> None:
    fx = season().observe(2).fixtures
    assert fx["fixture_id"].to_list() == [10, 20]
    assert fx.filter(pl.col("gw") == 2)["home_score"].to_list() == [None]
    assert fx.filter(pl.col("gw") == 1)["home_score"].to_list() == [2]
    assert "result_as_of" not in fx.columns


def test_unknown_gw_raises() -> None:
    with pytest.raises(KeyError):
        season().observe(3)


def assert_no_future(obs: Observation) -> None:
    for frame in (obs.player_matches, obs.prices):
        if not frame.is_empty():
            assert frame["as_of"].max() < obs.deadline  # type: ignore[operator]


URL = os.environ.get("DIFFPL_TEST_DATABASE_URL")


@pytest.mark.skipif(URL is None, reason="DIFFPL_TEST_DATABASE_URL not set")
@pytest.mark.parametrize("name", ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"])
def test_loaded_seasons_never_leak(name: str) -> None:
    assert URL is not None
    engine = create_engine(URL)
    try:
        data = load_season(engine, name)
    except (LookupError, ProgrammingError):
        pytest.skip(f"{name} not loaded or dbt not built")
    finally:
        engine.dispose()
    # Every GW with a fixture has a deadline. 2022-23 GW7 had none (all postponed).
    assert data.gameweeks == sorted(data.fixtures["gw"].drop_nulls().unique().to_list())
    for gw in data.gameweeks:
        assert_no_future(data.observe(gw))
