"""Point-in-time features per player and GW (ADR-0006).

Features come only from `SeasonData.observe(gw)`, the same leakage-safe view replay managers
get, so nothing after the deadline can enter. Targets (the GW's actual points and minutes)
are joined from the season data afterwards and must never be used as features.
"""

from __future__ import annotations

import polars as pl

from diffpl.replay.data import Observation, SeasonData

WINDOWS = (3, 6)
FEATURES = (
    "position_code",
    "price_tenths",
    "selected_by",
    "net_transfers",
    "n_fixtures",
    "home_share",
    "opp_conceded_pg",
    "team_scored_pg",
    "games_played",
    *(f"{s}_last{w}" for w in WINDOWS for s in ("points", "minutes", "starts", "xgi", "bonus")),
    "points_season_pg",
    "minutes_season_pg",
    "played_last_gw",
)
POSITION_CODE = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}


def _team_form(obs: Observation) -> tuple[dict[int, float], dict[int, float]]:
    """Goals conceded and scored per game so far, per team id."""
    done = obs.fixtures.filter(pl.col("home_score").is_not_null())
    if done.is_empty():
        return {}, {}
    long = (
        pl.concat(
            [
                done.select(
                    pl.col("home_team_id").alias("team_id"),
                    pl.col("home_score").alias("gf"),
                    pl.col("away_score").alias("ga"),
                ),
                done.select(
                    pl.col("away_team_id").alias("team_id"),
                    pl.col("away_score").alias("gf"),
                    pl.col("home_score").alias("ga"),
                ),
            ]
        )
        .group_by("team_id", maintain_order=True)
        .agg(pl.col("gf").mean(), pl.col("ga").mean())
    )
    ids = long["team_id"].to_list()
    return (
        dict(zip(ids, long["ga"].to_list(), strict=True)),
        dict(zip(ids, long["gf"].to_list(), strict=True)),
    )


def gw_features(obs: Observation) -> pl.DataFrame:
    """One row per player with a price at this deadline."""
    market = (
        obs.prices.sort("as_of", "element_id")
        .group_by("element_id", maintain_order=True)
        .last()
        .select(
            "element_id",
            "team_name",
            "price_tenths",
            pl.col("selected_by").cast(pl.Float64),
            (pl.col("transfers_in") - pl.col("transfers_out"))
            .cast(pl.Float64)
            .alias("net_transfers"),
        )
        .join(obs.players.select("element_id", "position"), on="element_id", how="left")
        .with_columns(
            pl.col("position").replace_strict(POSITION_CODE, default=None).alias("position_code")
        )
    )

    # Fixtures this GW per team: count, share at home, opponent defence, own attack.
    conceded, scored = _team_form(obs)
    team_id = dict(zip(obs.teams["team_name"], obs.teams["team_id"], strict=True))
    upcoming = obs.fixtures.filter(pl.col("gw") == obs.gw)
    rows: dict[int, list[tuple[int, bool]]] = {}
    for h, a in zip(upcoming["home_team_id"], upcoming["away_team_id"], strict=True):
        rows.setdefault(h, []).append((a, True))
        rows.setdefault(a, []).append((h, False))
    league_ga = sum(conceded.values()) / len(conceded) if conceded else None

    def fixture_cols(team: str | None) -> tuple[int, float | None, float | None, float | None]:
        tid = team_id.get(team or "")
        fx = rows.get(tid, []) if tid is not None else []
        if not fx:
            return 0, None, None, None
        home = sum(h for _, h in fx) / len(fx)
        opp = [conceded.get(o, league_ga) for o, _ in fx]
        opp_known = [x for x in opp if x is not None]
        own = scored.get(tid) if tid is not None else None
        return len(fx), home, (sum(opp_known) / len(opp_known) if opp_known else None), own

    fx_cols = [fixture_cols(t) for t in market["team_name"].to_list()]
    market = market.with_columns(
        pl.Series("n_fixtures", [c[0] for c in fx_cols], dtype=pl.Int64),
        pl.Series("home_share", [c[1] for c in fx_cols], dtype=pl.Float64),
        pl.Series("opp_conceded_pg", [c[2] for c in fx_cols], dtype=pl.Float64),
        pl.Series("team_scored_pg", [c[3] for c in fx_cols], dtype=pl.Float64),
    )

    # Rolling player form over past matches (all before the deadline by construction).
    pm = obs.player_matches
    if pm.is_empty():
        form_cols = [f for f in FEATURES if f not in market.columns]
        form = pl.DataFrame(
            schema={"element_id": pl.Int64, **{c: pl.Float64 for c in form_cols}}
        ).with_columns(
            pl.col("games_played").cast(pl.UInt32), pl.col("played_last_gw").cast(pl.Int64)
        )
    else:
        pm = pm.sort("element_id", "kickoff_time").with_columns(
            (pl.col("expected_goals").fill_null(0) + pl.col("expected_assists").fill_null(0)).alias(
                "xgi"
            ),
            pl.col("starts").fill_null((pl.col("minutes") >= 60).cast(pl.Int64)),
        )
        aggs = [
            pl.len().alias("games_played"),
            pl.col("total_points").mean().alias("points_season_pg"),
            pl.col("minutes").mean().alias("minutes_season_pg"),
            (pl.col("gw").max() == obs.gw - 1).cast(pl.Int64).alias("played_last_gw"),
        ]
        for w in WINDOWS:
            for src, name in (
                ("total_points", "points"),
                ("minutes", "minutes"),
                ("starts", "starts"),
                ("xgi", "xgi"),
                ("bonus", "bonus"),
            ):
                aggs.append(pl.col(src).tail(w).mean().cast(pl.Float64).alias(f"{name}_last{w}"))
        form = pm.group_by("element_id", maintain_order=True).agg(aggs)

    out = market.join(form, on="element_id", how="left").with_columns(
        pl.lit(obs.season).alias("season"),
        pl.lit(obs.gw).alias("gw"),
        pl.col("games_played").fill_null(0),
    )
    return out.select("season", "gw", "element_id", "position", *FEATURES)


def gw_targets(data: SeasonData, gw: int) -> pl.DataFrame:
    """Actual points and minutes in the GW, summed over its matches. Never a feature."""
    return (
        data.player_matches.filter(pl.col("gw") == gw)
        .group_by("element_id", maintain_order=True)
        .agg(pl.col("total_points").sum().alias("points"), pl.col("minutes").sum().alias("minutes"))
    )


def season_table(data: SeasonData) -> pl.DataFrame:
    """Features and targets for every GW of a season. Players without a match score 0."""
    frames = []
    for gw in data.gameweeks:
        feats = gw_features(data.observe(gw))
        frames.append(
            feats.join(gw_targets(data, gw), on="element_id", how="left").with_columns(
                pl.col("points").fill_null(0), pl.col("minutes").fill_null(0)
            )
        )
    return pl.concat(frames, how="diagonal_relaxed")
