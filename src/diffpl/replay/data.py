"""Point-in-time season data for the replay env (ADR-0004).

`SeasonData` holds a whole season in memory. `SeasonData.observe(gw)` returns an `Observation`
that contains only rows with `as_of` before that GW's deadline. Managers only ever see
observations, never `SeasonData`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    teams: pl.DataFrame  # team_id, team_name


@dataclass(frozen=True)
class SeasonData:
    season: str
    deadlines: pl.DataFrame  # gw, deadline_time
    player_matches: pl.DataFrame
    prices: pl.DataFrame
    fixtures: pl.DataFrame
    players: pl.DataFrame
    teams: pl.DataFrame = field(
        default_factory=lambda: pl.DataFrame(schema={"team_id": pl.Int64, "team_name": pl.String})
    )

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
            teams=self.teams,
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
    teams = _read(
        engine,
        "select team_id, team_name from staging.stg_vaastav__teams where season = :s",
        season,
    )
    if deadlines.is_empty():
        raise LookupError(f"season {season} is not loaded")
    return SeasonData(season, deadlines, player_matches, prices, fixtures, players, teams)


POSITION_BY_TYPE = (
    "case element_type when 1 then 'GKP' when 2 then 'DEF' when 3 then 'MID' else 'FWD' end"
)
# Latest bootstrap snapshot: current team, position and price of every player.
_LATEST = """
    with snap as (select max(as_of) as as_of from staging.stg_fpl__elements),
    el as (select e.* from staging.stg_fpl__elements e join snap on e.as_of = snap.as_of),
    tm as (select t.* from staging.stg_fpl__teams t join snap on t.as_of = snap.as_of)
"""


def load_live(engine: Engine, season: str) -> SeasonData:
    """Read the live season from the FPL API staging models, in `load_season`'s shape.

    Match rows come from element-summary history. Prices at past deadlines come from those
    rows; the price for the next deadline comes from the latest bootstrap snapshot, known as
    of when it was fetched. Teams are each player's current club.
    """
    deadlines = _read(
        engine,
        "select gw, deadline_time from marts.mart_gameweek_deadlines where season = :s",
        season,
    )
    player_matches = _read(
        engine,
        _LATEST
        + """
        select g.element_id, tm.team_name, g.fixture_id, g.gw, g.kickoff_time, g.was_home,
               g.opponent_team_id, g.minutes, g.total_points, g.goals_scored, g.assists,
               g.clean_sheets, g.goals_conceded, g.saves, g.penalties_saved,
               g.penalties_missed, g.yellow_cards, g.red_cards, g.own_goals, g.bonus, g.bps,
               g.influence, g.creativity, g.threat, g.ict_index, g.expected_goals,
               g.expected_assists, g.starts, g.as_of
        from staging.stg_fpl__player_gameweeks g
        join el on el.element_id = g.element_id
        join tm on tm.team_id = el.team_id
        """,
        season,
    )
    prices = _read(
        engine,
        _LATEST
        + """
        , past as (
            select distinct on (g.gw, g.element_id) g.gw, g.element_id, tm.team_name,
                   g.price_tenths, g.selected_by, g.transfers_in, g.transfers_out,
                   d.deadline_time - interval '1 minute' as as_of
            from staging.stg_fpl__player_gameweeks g
            join el on el.element_id = g.element_id
            join tm on tm.team_id = el.team_id
            join marts.mart_gameweek_deadlines d on d.season = :s and d.gw = g.gw
            order by g.gw, g.element_id, g.kickoff_time
        ),
        next_gw as (
            select min(d.gw) as gw from marts.mart_gameweek_deadlines d, snap
            where d.season = :s and d.deadline_time > snap.as_of
        )
        select * from past
        union all
        select n.gw, el.element_id, tm.team_name, el.price_tenths, el.selected_by,
               el.transfers_in_event, el.transfers_out_event, el.as_of
        from el join tm on tm.team_id = el.team_id cross join next_gw n
        where n.gw is not null
        """,
        season,
    )
    fixtures = _read(
        engine,
        """
        with snap as (select max(as_of) as as_of from staging.stg_fpl__fixtures)
        select f.fixture_id, f.gw, f.kickoff_time, f.home_team_id, f.away_team_id,
               f.home_score, f.away_score, f.finished,
               -- same settle interval as dbt's match_settle_interval
               case when f.finished then f.kickoff_time + interval '3 hours' end as result_as_of
        from staging.stg_fpl__fixtures f join snap on f.as_of = snap.as_of
        where f.gw is not null
        """,
        season,
    )
    players = _read(
        engine,
        _LATEST + f"select element_id, web_name as player_name, {POSITION_BY_TYPE} as position "
        "from el",
        season,
    )
    teams = _read(engine, _LATEST + "select team_id, team_name from tm", season)
    if deadlines.is_empty() or players.is_empty():
        raise LookupError(f"live season {season} is not loaded; run `diffpl.ingest fpl`")
    return SeasonData(season, deadlines, player_matches, prices, fixtures, players, teams)
