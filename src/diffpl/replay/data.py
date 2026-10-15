"""Point-in-time season data for the replay env (ADR-0004).

`SeasonData` holds a whole season in memory. `SeasonData.observe(gw)` returns an `Observation`
that contains only rows with `as_of` before that GW's deadline. Managers only ever see
observations, never `SeasonData`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl
from sqlalchemy import Engine, text

# Fixture columns that reveal the result. Masked until result_as_of < deadline.
RESULT_COLUMNS = ("home_score", "away_score", "finished")


@dataclass(frozen=True)
class Observation:
    season: str
    gw: int
    deadline: datetime
    player_matches: pl.DataFrame  # past match rows: stats and points
    prices: pl.DataFrame  # price, ownership, transfers at each deadline so far
    # Whole schedule; results only for matches settled before the deadline. Known gap: vaastav
    # has final kickoff times, so a postponement shows up before it was announced.
    fixtures: pl.DataFrame
    players: pl.DataFrame  # element_id, name, position


@dataclass(frozen=True)
class SeasonData:
    season: str
    deadlines: pl.DataFrame  # gw, deadline_time
    player_matches: pl.DataFrame
    prices: pl.DataFrame
    fixtures: pl.DataFrame
    players: pl.DataFrame

    @property
    def gameweeks(self) -> list[int]:
        return sorted(self.deadlines["gw"].to_list())

    def deadline(self, gw: int) -> datetime:
        row = self.deadlines.filter(pl.col("gw") == gw)
        if row.height != 1:
            raise KeyError(f"{self.season} has no deadline for GW{gw}")
        value: datetime = row["deadline_time"][0]
        return value

    def observe(self, gw: int) -> Observation:
        deadline = self.deadline(gw)
        known = pl.col("as_of") < deadline
        fixtures = self.fixtures.with_columns(
            [
                pl.when(pl.col("result_as_of") < deadline).then(pl.col(c)).otherwise(None).alias(c)
                for c in RESULT_COLUMNS
            ]
        ).drop("result_as_of")
        return Observation(
            season=self.season,
            gw=gw,
            deadline=deadline,
            player_matches=self.player_matches.filter(known),
            prices=self.prices.filter(known),
            fixtures=fixtures,
            players=self.players,
        )


def _read(engine: Engine, sql: str, season: str) -> pl.DataFrame:
    with engine.connect() as conn:
        return pl.read_database(text(sql), conn, execute_options={"parameters": {"s": season}})


def load_season(engine: Engine, season: str) -> SeasonData:
    """Read one season from dbt staging and marts."""
    deadlines = _read(
        engine,
        "select gw, deadline_time from marts.mart_gameweek_deadlines where season = :s",
        season,
    )
    player_matches = _read(
        engine,
        """
        select element_id, team_name, fixture_id, gw, kickoff_time, was_home, opponent_team_id,
               minutes,
               total_points, goals_scored, assists, clean_sheets, goals_conceded, saves,
               penalties_saved, penalties_missed, yellow_cards, red_cards, own_goals, bonus,
               bps, influence, creativity, threat, ict_index, expected_goals,
               expected_assists, starts, as_of
        from staging.stg_vaastav__player_gameweeks
        where season = :s and position <> 'AM'
        """,
        season,
    )
    prices = _read(
        engine,
        """
        select gw, element_id, team_name, price_tenths, selected_by, transfers_in,
               transfers_out, as_of
        from marts.mart_player_deadline_prices where season = :s
        """,
        season,
    )
    fixtures = _read(
        engine,
        """
        select fixture_id, gw, kickoff_time, home_team_id, away_team_id, home_score,
               away_score, finished, result_as_of
        from staging.stg_vaastav__fixtures where season = :s
        """,
        season,
    )
    # Position is fixed for a season. The name and position are known before GW1.
    players = _read(
        engine,
        """
        select distinct on (element_id) element_id, player_name,
               case position when 'GK' then 'GKP' else position end as position
        from staging.stg_vaastav__player_gameweeks
        where season = :s and position <> 'AM'
        order by element_id, kickoff_time
        """,
        season,
    )
    if deadlines.is_empty():
        raise LookupError(f"season {season} is not loaded")
    return SeasonData(season, deadlines, player_matches, prices, fixtures, players)
