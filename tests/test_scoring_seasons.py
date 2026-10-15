"""Recompute every loaded player-match from the rules file and compare with FPL's total.

Runs against Postgres when DIFFPL_TEST_DATABASE_URL is set and dbt staging has the season.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from diffpl.rules import Position, load_rules
from diffpl.scoring import MatchStats, player_points

URL = os.environ.get("DIFFPL_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="DIFFPL_TEST_DATABASE_URL not set")
POS: dict[str, Position] = {"GK": "GKP", "GKP": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}
QUERY = text(
    """
    select g.position, g.minutes, g.goals_scored, g.assists, g.clean_sheets,
           g.goals_conceded, g.saves, g.penalties_saved, g.penalties_missed,
           g.yellow_cards, g.red_cards, g.own_goals, g.bonus,
           coalesce(cast(nullif(v.data ->> 'defensive_contribution', '') as int), 0) as dc,
           g.total_points
    from staging.stg_vaastav__player_gameweeks as g
    join staging.base_vaastav__rows as v
        on v.season = g.season and v.row_num = g.row_num and v.file = 'gws/merged_gw.csv'
    where g.season = :season and g.position <> 'AM'
    """
)


@pytest.mark.parametrize("season", ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"])
def test_rules_reproduce_fpl_points(season: str) -> None:
    assert URL is not None
    engine = create_engine(URL)
    try:
        with engine.connect() as conn:
            rows = conn.execute(QUERY, {"season": season}).all()
    except ProgrammingError:
        pytest.skip("dbt staging not built")
    finally:
        engine.dispose()
    if not rows:
        pytest.skip(f"{season} not loaded")
    rules = load_rules(season)
    fields = [f for f in MatchStats.__dataclass_fields__ if f != "defensive_contribution"]
    mismatches = []
    for r in rows:
        m = r._mapping
        stats = MatchStats(**{f: m[f] for f in fields}, defensive_contribution=m["dc"])
        if player_points(rules, POS[m["position"]], stats) != m["total_points"]:
            mismatches.append(r)
    assert not mismatches, f"{len(mismatches)} of {len(rows)} rows differ, e.g. {mismatches[:3]}"
