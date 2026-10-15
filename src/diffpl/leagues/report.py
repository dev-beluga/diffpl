"""Mini-league stats and weekly winners from dbt marts (ADR-0005)."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from sqlalchemy import Engine, text

from diffpl.leagues.rules import EntryGw, GwOutcome, LeagueRules, overall_table, score_gameweek


@dataclass(frozen=True)
class LeagueData:
    league_id: int
    managers: pl.DataFrame  # mart_league_managers
    ownership: pl.DataFrame  # mart_league_ownership
    gameweeks: pl.DataFrame  # stg_fpl__entry_gameweeks for members, with chip
    picks: pl.DataFrame  # stg_fpl__entry_picks for members
    names: pl.DataFrame  # element_id, web_name

    @property
    def last_gw(self) -> int:
        return int(self.picks["gw"].max())  # type: ignore[arg-type]


def _read(engine: Engine, sql: str, league_id: int) -> pl.DataFrame:
    with engine.connect() as conn:
        return pl.read_database(text(sql), conn, execute_options={"parameters": {"l": league_id}})


MEMBERS = "select entry_id from marts.mart_league_managers where league_id = :l"


def load_league(engine: Engine, league_id: int) -> LeagueData:
    managers = _read(
        engine, "select * from marts.mart_league_managers where league_id = :l", league_id
    )
    if managers.is_empty():
        raise LookupError(
            f"league {league_id} is not loaded; "
            f"run: python -m diffpl.ingest league --id {league_id}"
        )
    ownership = _read(
        engine, "select * from marts.mart_league_ownership where league_id = :l", league_id
    )
    gameweeks = _read(
        engine,
        f"""
        select g.entry_id, g.gw, g.points, g.hit_cost, g.transfers, g.total_points,
               g.value_tenths, g.bank_tenths, c.chip
        from staging.stg_fpl__entry_gameweeks as g
        left join staging.stg_fpl__entry_chips as c on c.entry_id = g.entry_id and c.gw = g.gw
        where g.entry_id in ({MEMBERS})
        """,
        league_id,
    )
    picks = _read(
        engine,
        f"select * from staging.stg_fpl__entry_picks where entry_id in ({MEMBERS})",
        league_id,
    )
    names = _read(
        engine,
        """
        select distinct on (element_id) element_id, web_name
        from staging.stg_fpl__elements order by element_id, as_of desc
        """,
        league_id,
    )
    return LeagueData(league_id, managers, ownership, gameweeks, picks, names)


def exposure(data: LeagueData, entry_id: int, gw: int | None = None) -> pl.DataFrame:
    """Per player: the entry's multiplier minus league effective ownership for a GW.

    Positive rows are differentials (you gain on the league when they score); negative rows
    are threats (you lose ground). Sorted by absolute exposure.
    """
    gw = gw or data.last_gw
    eo = data.ownership.filter(pl.col("gw") == gw).select(
        "element_id", "ownership", "effective_ownership"
    )
    mine = data.picks.filter((pl.col("entry_id") == entry_id) & (pl.col("gw") == gw)).select(
        "element_id", pl.col("multiplier").alias("mine")
    )
    return (
        eo.join(mine, on="element_id", how="full", coalesce=True)
        .with_columns(
            pl.col("mine").fill_null(0),
            pl.col("ownership").fill_null(0.0).cast(pl.Float64),
            pl.col("effective_ownership").fill_null(0.0).cast(pl.Float64),
        )
        .with_columns((pl.col("mine") - pl.col("effective_ownership")).alias("exposure"))
        .join(data.names, on="element_id", how="left")
        .sort(pl.col("exposure").abs(), descending=True)
    )


def entry_rows(data: LeagueData) -> list[EntryGw]:
    return [
        EntryGw(
            entry_id=r["entry_id"],
            gw=r["gw"],
            points=r["points"],
            hit_cost=r["hit_cost"],
            transfers=r["transfers"],
            chip=r["chip"],
            total_points=r["total_points"],
        )
        for r in data.gameweeks.iter_rows(named=True)
    ]


def weekly_outcomes(data: LeagueData, rules: LeagueRules) -> tuple[list[GwOutcome], dict[int, int]]:
    rows = entry_rows(data)
    by_gw: dict[int, list[EntryGw]] = {}
    for r in rows:
        by_gw.setdefault(r.gw, []).append(r)
    outcomes = [score_gameweek(rules, by_gw[gw]) for gw in sorted(by_gw)]
    return outcomes, overall_table(rules, outcomes, rows)
