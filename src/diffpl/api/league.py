"""Mini-league page: standings, a manager's exposure, and transfer targets (ADR-0012).

Targets come from two references:
- template: players at least TEMPLATE_MIN of a reference league owns (the overall top 100 by
  default) that the manager does not own, ranked by that ownership;
- differentials: the best players by expected points over the horizon that at most
  DIFFERENTIAL_MAX of the manager's own league owns, ranked by those points.
"""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl
from pydantic import BaseModel

from diffpl.api.stats import PlayerRow
from diffpl.leagues.report import LeagueData, exposure

TEMPLATE_MIN = 0.20
DIFFERENTIAL_MAX = 0.10
N_TARGETS = 10
N_EXPOSURE = 8


class Standing(BaseModel):
    rank: int
    entry_id: int
    entry_name: str
    manager: str
    total_points: int
    gap: int  # points behind the leader


class ExposureRow(BaseModel):
    element_id: int
    name: str
    team: str
    position: str
    mine: int  # 0 not owned, 1 owned, 2 captain, 3 triple captain
    ownership: float  # percent of the league
    effective_ownership: float  # percent, captaincy counted
    exposure: float  # mine minus effective ownership, in multiples


class Target(BaseModel):
    element_id: int
    name: str
    team: str
    position: str
    price: float
    xp_horizon: float  # expected points over the planning horizon
    reference_ownership: float  # percent of the reference league (template list)
    league_ownership: float  # percent of this mini-league


class LeagueView(BaseModel):
    league_id: int
    gw: int  # last GW with picks
    managers: int
    standings: list[Standing]
    differentials: list[ExposureRow]  # you own, the league does not
    threats: list[ExposureRow]  # the league owns, you do not
    template_targets: list[Target]
    differential_targets: list[Target]
    reference: str  # which league the template comes from


def _ownership(data: LeagueData) -> dict[int, float]:
    o = data.ownership.filter(pl.col("gw") == data.last_gw)
    return dict(
        zip(o["element_id"].to_list(), o["ownership"].cast(pl.Float64).to_list(), strict=True)
    )


def _owned_by(data: LeagueData, entry_id: int) -> set[int]:
    p = data.picks.filter((pl.col("entry_id") == entry_id) & (pl.col("gw") == data.last_gw))
    return set(p["element_id"].to_list())


def league_view(
    data: LeagueData,
    entry_id: int | None,
    reference: LeagueData,
    reference_name: str,
    players: Mapping[int, PlayerRow],
    xp_horizon: Mapping[int, float],
) -> LeagueView:
    """Everything the league page shows. `players` and `xp_horizon` cover the live season."""
    top = int(data.managers["total_points"].max() or 0)  # type: ignore[arg-type]
    standings = [
        Standing(
            rank=int(r["rank"]),
            entry_id=int(r["entry_id"]),
            entry_name=str(r["entry_name"]),
            manager=str(r["player_name"]),
            total_points=int(r["total_points"]),
            gap=top - int(r["total_points"]),
        )
        for r in data.managers.sort("rank").iter_rows(named=True)
    ]
    league_own = _ownership(data)
    ref_own = _ownership(reference)
    mine = _owned_by(data, entry_id) if entry_id else set()

    differentials: list[ExposureRow] = []
    threats: list[ExposureRow] = []
    if entry_id:
        for r in exposure(data, entry_id).iter_rows(named=True):
            p = players.get(r["element_id"])
            row = ExposureRow(
                element_id=r["element_id"],
                name=p.name if p else str(r["web_name"]),
                team=p.team if p else "?",
                position=p.position if p else "?",
                mine=int(r["mine"]),
                ownership=round(100 * r["ownership"], 1),
                effective_ownership=round(100 * r["effective_ownership"], 1),
                exposure=round(r["exposure"], 2),
            )
            if row.exposure > 0 and len(differentials) < N_EXPOSURE:
                differentials.append(row)
            elif row.exposure < 0 and len(threats) < N_EXPOSURE:
                threats.append(row)

    def target(i: int) -> Target:
        p = players[i]
        return Target(
            element_id=i,
            name=p.name,
            team=p.team,
            position=p.position,
            price=p.price,
            xp_horizon=round(xp_horizon.get(i, 0.0), 1),
            reference_ownership=round(100 * ref_own.get(i, 0.0), 1),
            league_ownership=round(100 * league_own.get(i, 0.0), 1),
        )

    pool = [i for i in players if i not in mine]
    template = sorted(
        (i for i in pool if ref_own.get(i, 0.0) >= TEMPLATE_MIN),
        key=lambda i: (-ref_own.get(i, 0.0), -xp_horizon.get(i, 0.0), i),
    )
    diffs = sorted(
        (i for i in pool if league_own.get(i, 0.0) <= DIFFERENTIAL_MAX),
        key=lambda i: (-xp_horizon.get(i, 0.0), i),
    )
    return LeagueView(
        league_id=data.league_id,
        gw=data.last_gw,
        managers=data.managers.height,
        standings=standings,
        differentials=differentials,
        threats=threats,
        template_targets=[target(i) for i in template[:N_TARGETS]],
        differential_targets=[target(i) for i in diffs[:N_TARGETS]],
        reference=reference_name,
    )
