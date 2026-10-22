"""This GW's plans for a team, as plain data for the web front end and the dashboard.

Builds on `diffpl.optim.live.recommend` (ADR-0010): loads the live season, finds the next
deadline, and turns each plan into players a page can draw (names, clubs, fixtures, xP).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import polars as pl
from pydantic import BaseModel
from sqlalchemy import Engine, text

from diffpl.optim.live import recommend
from diffpl.optim.planner import HORIZON, Projector
from diffpl.replay.data import Observation, load_live
from diffpl.replay.engine import Market
from diffpl.rules import Position, load_rules

LIVE_SEASON = "2026-27"
N_PLANS = 5


class Player(BaseModel):
    element_id: int
    name: str
    team: str  # club short name, e.g. "ARS"
    position: Position
    price: float  # millions
    xp: float  # expected points this GW, before the captain multiplier
    fixtures: list[str]  # e.g. ["NEW (H)"]; empty for a blank GW
    captain: bool = False
    vice: bool = False
    new: bool = False  # bought by this plan


class TransferOut(BaseModel):
    out: Player
    into: Player
    gain: float  # expected points over the horizon, in minus out


class PlanOut(BaseModel):
    rank: int  # 1 is the best by expected points
    objective: float  # weighted expected points over the horizon, after hits
    hits: int
    starters: list[Player]
    bench: list[Player]  # substitution order, goalkeeper first
    transfers: list[TransferOut]


class GwPlan(BaseModel):
    team_id: int
    gw: int
    deadline: datetime
    bank: float  # millions
    free_transfers: int
    squad_value: float  # millions, at current prices
    horizon: int
    picks_gw: int  # last GW the team's picks were ingested for
    data_as_of: datetime
    plans: list[PlanOut]


def next_gw(deadlines: pl.DataFrame, now: datetime) -> tuple[int, datetime]:
    """First GW whose deadline is after `now`."""
    utc = deadlines.with_columns(pl.col("deadline_time").dt.convert_time_zone("UTC"))
    upcoming = utc.filter(pl.col("deadline_time") > now).sort("gw")
    if upcoming.is_empty():
        raise LookupError("no upcoming deadline this season")
    return int(upcoming["gw"][0]), upcoming["deadline_time"][0]


def short_names(engine: Engine) -> dict[int, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "select team_id, short_name from staging.stg_fpl__teams "
                "where as_of = (select max(as_of) from staging.stg_fpl__teams)"
            )
        ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def fixtures_by_team(obs: Observation, short: dict[int, str]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for fx in (
        obs.fixtures.filter(pl.col("gw") == obs.gw).sort("kickoff_time").iter_rows(named=True)
    ):
        h, a = fx["home_team_id"], fx["away_team_id"]
        out.setdefault(h, []).append(f"{short.get(a, '?')} (H)")
        out.setdefault(a, []).append(f"{short.get(h, '?')} (A)")
    return out


def build_plan(
    engine: Engine,
    entry_id: int,
    projector: Callable[[], Projector],
    now: datetime | None = None,
) -> GwPlan:
    """Top plans for the next deadline. `projector` returns the projection to plan with."""
    data = load_live(engine, LIVE_SEASON)
    gw, deadline = next_gw(data.deadlines, now or datetime.now(UTC))
    obs = data.observe(gw)
    rules = load_rules(LIVE_SEASON)
    rec = recommend(engine, rules, obs, entry_id, projector(), N_PLANS)
    market = Market.at(obs.prices, obs.players)
    short = short_names(engine)
    team_id = dict(zip(obs.teams["team_name"], obs.teams["team_id"], strict=True))
    fixtures = fixtures_by_team(obs, short)
    name = dict(zip(obs.players["element_id"], obs.players["player_name"], strict=True))
    owned = {p.element_id for p in rec.entry.squad.picks}

    def player(i: int, captain: int = -1, vice: int = -1) -> Player:
        tid = team_id.get(market.team.get(i, ""), -1)
        return Player(
            element_id=i,
            name=str(name.get(i, i)),
            team=short.get(tid, "?"),
            position=market.position[i],
            price=market.price.get(i, 0) / 10,
            xp=round(rec.xp.get(i, 0.0), 2),
            fixtures=fixtures.get(tid, []),
            captain=i == captain,
            vice=i == vice,
            new=i not in owned,
        )

    plans = []
    for k, o in enumerate(rec.options):
        d = o.decision
        plans.append(
            PlanOut(
                rank=k + 1,
                objective=round(o.plan.objective, 2),
                hits=o.plan.hits,
                starters=[player(i, d.captain, d.vice_captain) for i in d.lineup],
                bench=[player(i, d.captain, d.vice_captain) for i in d.bench],
                transfers=[
                    TransferOut(
                        out=player(t.out_id),
                        into=player(t.in_id),
                        gain=round(
                            rec.xp_horizon.get(t.in_id, 0.0) - rec.xp_horizon.get(t.out_id, 0.0),
                            2,
                        ),
                    )
                    for t in o.plan.transfers
                ],
            )
        )
    with engine.connect() as conn:
        picks_gw = conn.execute(
            text("select max(gw) from staging.stg_fpl__entry_picks where entry_id = :e"),
            {"e": entry_id},
        ).scalar_one()
    squad = rec.entry.squad
    return GwPlan(
        team_id=entry_id,
        gw=gw,
        deadline=deadline,
        bank=squad.bank / 10,
        free_transfers=squad.free_transfers,
        squad_value=sum(market.price.get(p.element_id, 0) for p in squad.picks) / 10,
        horizon=HORIZON,
        picks_gw=int(picks_gw or 0),
        data_as_of=obs.prices["as_of"].max(),  # type: ignore[arg-type]
        plans=plans,
    )
