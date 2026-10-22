"""Stats pages: player table, team form and a fixture ticker, from ingested FPL data.

Pure functions over a `SeasonData` (live season) so they are testable on synthetic seasons.
Team xG is the sum of its players' xG in a match. Fixture difficulty is expected goals for
and against: league average x own attack x opponent defence, where attack and defence are
xG rates over each team's last FORM_MATCHES matches, shrunk toward the league average.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel

from diffpl.replay.data import SeasonData
from diffpl.rules import Position

FORM_MATCHES = 4  # player form window, matches
TEAM_FORM_MATCHES = 5  # team form table
RATING_MATCHES = 6  # matches behind attack and defence ratings
SHRINK_MATCHES = 3.0  # prior weight toward the league average, in matches


class PlayerRow(BaseModel):
    element_id: int
    name: str
    team: str
    position: Position
    price: float
    ownership: float  # percent of managers
    minutes: int
    points: int
    form: float  # points per match, last FORM_MATCHES matches
    xg90: float
    xa90: float
    xgi90: float


class TeamForm(BaseModel):
    team: str
    matches: int
    xg_for: float  # per match
    xg_against: float
    goals_for: float
    goals_against: float


class TickerCell(BaseModel):
    gw: int
    opponent: str
    home: bool
    xg_for: float  # expected goals for the team in this fixture
    xg_against: float


class TickerRow(BaseModel):
    team: str
    fixtures: list[TickerCell]  # several per GW in a double, none in a blank


class MatchRow(BaseModel):
    gw: int
    opponent: str
    home: bool
    minutes: int
    points: int
    xg: float
    xa: float


class PlayerDetail(BaseModel):
    row: PlayerRow
    matches: list[MatchRow]
    points_bins: list[float]  # values of the next-GW points distribution
    points_probs: list[float]  # probabilities, same order; empty if no projection
    p60: float | None = None  # champion's P(60+ minutes) next GW
    xp_horizon: float = 0.0  # expected points over the planning horizon
    horizon: int = 4


def _latest_prices(data: SeasonData) -> pl.DataFrame:
    return (
        data.prices.sort("as_of", "element_id")
        .group_by("element_id", maintain_order=True)
        .last()
        .select("element_id", "price_tenths")
    )


def player_table(
    data: SeasonData, short: dict[str, str], ownership: dict[int, float]
) -> list[PlayerRow]:
    """One row per player with at least one match. `short` maps team name to short name;
    `ownership` is each player's percent of managers at the latest snapshot."""
    pm = data.player_matches.sort("kickoff_time")
    agg = pm.group_by("element_id").agg(
        pl.col("team_name").last(),
        pl.col("minutes").sum(),
        pl.col("total_points").sum().alias("points"),
        pl.col("total_points").tail(FORM_MATCHES).mean().alias("form"),
        pl.col("expected_goals").cast(pl.Float64).sum().alias("xg"),
        pl.col("expected_assists").cast(pl.Float64).sum().alias("xa"),
    )
    rows = (
        agg.join(_latest_prices(data), on="element_id", how="left")
        .join(data.players.select("element_id", "player_name", "position"), on="element_id")
        .sort("element_id")
    )
    out = []
    for r in rows.iter_rows(named=True):
        per90 = 90 / r["minutes"] if r["minutes"] else 0.0
        out.append(
            PlayerRow(
                element_id=r["element_id"],
                name=r["player_name"],
                team=short.get(r["team_name"], r["team_name"]),
                position=r["position"],
                price=(r["price_tenths"] or 0) / 10,
                ownership=ownership.get(r["element_id"], 0.0),
                minutes=r["minutes"],
                points=r["points"],
                form=round(r["form"] or 0.0, 2),
                xg90=round(r["xg"] * per90, 2),
                xa90=round(r["xa"] * per90, 2),
                xgi90=round((r["xg"] + r["xa"]) * per90, 2),
            )
        )
    return out


def team_matches(data: SeasonData) -> pl.DataFrame:
    """One row per team per finished fixture: xG and goals for and against, by kickoff."""
    fx = data.fixtures.filter(pl.col("home_score").is_not_null())
    names = dict(zip(data.teams["team_id"], data.teams["team_name"], strict=True))
    xg = data.player_matches.group_by("fixture_id", "team_name").agg(
        pl.col("expected_goals").cast(pl.Float64).sum().alias("xg")
    )
    sides = []
    for side, opp, gf, ga in (
        ("home_team_id", "away_team_id", "home_score", "away_score"),
        ("away_team_id", "home_team_id", "away_score", "home_score"),
    ):
        sides.append(
            fx.select(
                "fixture_id",
                "kickoff_time",
                pl.col(side).replace_strict(names, return_dtype=pl.String).alias("team_name"),
                pl.col(opp).replace_strict(names, return_dtype=pl.String).alias("opp_name"),
                pl.col(gf).alias("goals_for"),
                pl.col(ga).alias("goals_against"),
            )
        )
    long = pl.concat(sides)
    long = long.join(xg, on=["fixture_id", "team_name"], how="left").with_columns(
        pl.col("xg").fill_null(0.0).alias("xg_for")
    )
    against = long.select(
        "fixture_id", pl.col("opp_name").alias("team_name"), pl.col("xg_for").alias("xg_against")
    )
    return long.join(against, on=["fixture_id", "team_name"]).sort("kickoff_time")


def team_form(data: SeasonData, short: dict[str, str]) -> list[TeamForm]:
    recent = (
        team_matches(data)
        .group_by("team_name", maintain_order=True)
        .agg(
            pl.len().alias("n"),
            pl.col("xg_for").tail(TEAM_FORM_MATCHES).mean(),
            pl.col("xg_against").tail(TEAM_FORM_MATCHES).mean(),
            pl.col("goals_for").tail(TEAM_FORM_MATCHES).mean(),
            pl.col("goals_against").tail(TEAM_FORM_MATCHES).mean(),
        )
        .sort("team_name")
    )
    return [
        TeamForm(
            team=short.get(r["team_name"], r["team_name"]),
            matches=min(r["n"], TEAM_FORM_MATCHES),
            xg_for=round(r["xg_for"], 2),
            xg_against=round(r["xg_against"], 2),
            goals_for=round(r["goals_for"], 2),
            goals_against=round(r["goals_against"], 2),
        )
        for r in recent.iter_rows(named=True)
    ]


def ratings(data: SeasonData) -> tuple[float, dict[str, float], dict[str, float]]:
    """League xG per team-match, and each team's attack and defence multipliers (1 = average).
    Teams without matches sit at 1."""
    tm = team_matches(data)
    if tm.is_empty():
        return 1.3, {}, {}
    avg = float(tm["xg_for"].mean())  # type: ignore[arg-type]
    rec = tm.group_by("team_name", maintain_order=True).agg(
        pl.col("xg_for").tail(RATING_MATCHES).sum(),
        pl.col("xg_against").tail(RATING_MATCHES).sum(),
        pl.len().clip(upper_bound=RATING_MATCHES).alias("n"),
    )
    att, dfn = {}, {}
    for r in rec.iter_rows(named=True):
        att[r["team_name"]] = (r["xg_for"] + SHRINK_MATCHES * avg) / (
            (r["n"] + SHRINK_MATCHES) * avg
        )
        dfn[r["team_name"]] = (r["xg_against"] + SHRINK_MATCHES * avg) / (
            (r["n"] + SHRINK_MATCHES) * avg
        )
    return avg, att, dfn


def fixture_ticker(
    data: SeasonData, from_gw: int, n_gws: int, short: dict[str, str]
) -> list[TickerRow]:
    avg, att, dfn = ratings(data)
    names = {
        int(i): str(n) for i, n in zip(data.teams["team_id"], data.teams["team_name"], strict=True)
    }
    fx = data.fixtures.filter(pl.col("gw").is_between(from_gw, from_gw + n_gws - 1)).sort(
        "gw", "kickoff_time"
    )
    cells: dict[str, list[TickerCell]] = {t: [] for t in sorted(names.values())}
    for r in fx.iter_rows(named=True):
        h, a = names[r["home_team_id"]], names[r["away_team_id"]]
        for team, opp, home in ((h, a, True), (a, h, False)):
            cells[team].append(
                TickerCell(
                    gw=r["gw"],
                    opponent=short.get(opp, opp),
                    home=home,
                    xg_for=round(avg * att.get(team, 1.0) * dfn.get(opp, 1.0), 2),
                    xg_against=round(avg * att.get(opp, 1.0) * dfn.get(team, 1.0), 2),
                )
            )
    return [TickerRow(team=short.get(t, t), fixtures=c) for t, c in cells.items()]


def player_matches(
    data: SeasonData, element_id: int, short_by_id: dict[int, str]
) -> list[MatchRow]:
    pm = data.player_matches.filter(pl.col("element_id") == element_id).sort("kickoff_time")
    return [
        MatchRow(
            gw=r["gw"],
            opponent=short_by_id.get(r["opponent_team_id"], "?"),
            home=bool(r["was_home"]),
            minutes=r["minutes"],
            points=r["total_points"],
            xg=round(float(r["expected_goals"] or 0), 2),
            xa=round(float(r["expected_assists"] or 0), 2),
        )
        for r in pm.iter_rows(named=True)
    ]
