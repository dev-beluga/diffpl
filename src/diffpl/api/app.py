"""HTTP API for the web front end (ADR-0012).

uv run uvicorn diffpl.api.app:app --port 8000

Read-only: plans are computed from ingested data and never written to FPL. No accounts; the
team id comes from the request. Plans take a while to solve, so each is cached per team for
CACHE_TTL_S, and one team is never solved twice at once.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine, create_engine, text

from diffpl.api.league import LeagueView, league_view
from diffpl.api.plan import GwPlan, build_plan
from diffpl.api.stats import (
    PlayerDetail,
    PlayerRow,
    TeamForm,
    TickerRow,
    fixture_ticker,
    player_matches,
    player_table,
    team_form,
)
from diffpl.optim.planner import HORIZON, Projector, fixture_horizon
from diffpl.settings import get_settings

CACHE_TTL_S = 600
WEB_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

app = FastAPI(title="DiffPL", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=WEB_ORIGINS, allow_methods=["GET"])


_cache: dict[int, tuple[float, GwPlan]] = {}
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


@cache
def engine() -> Engine:
    return create_engine(get_settings().database_url)


@cache
def champion_projector() -> Projector:
    """The registered champion's projections, spread over the planning horizon."""
    from diffpl.models.__main__ import two_part_scorer
    from diffpl.models.two_part import TwoPartModel

    model = champion_model()
    assert isinstance(model, TwoPartModel)
    return fixture_horizon(two_part_scorer(model), HORIZON)


def plan_for(team_id: int, build: Callable[[int], GwPlan]) -> GwPlan:
    """Cached plan for a team; concurrent requests for one team wait for a single solve."""
    hit = _cache.get(team_id)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]
    with _locks_guard:
        lock = _locks.setdefault(team_id, threading.Lock())
    with lock:
        hit = _cache.get(team_id)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]
        plan = build(team_id)
        _cache[team_id] = (time.monotonic(), plan)
        return plan


def default_build(team_id: int) -> GwPlan:
    return build_plan(engine(), team_id, champion_projector)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def get_builder() -> Callable[[int], GwPlan]:
    """The plan builder; tests override this dependency with a stub."""
    return default_build


@app.get("/api/plan/{team_id}", response_model=GwPlan)
def plan(
    build: Annotated[Callable[[int], GwPlan], Depends(get_builder)],
    team_id: int = Path(gt=0, lt=100_000_000),
) -> GwPlan:
    """Top plans for the next deadline. Sync handler: FastAPI runs it in a worker thread."""
    try:
        return plan_for(team_id, build)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --- Stats -----------------------------------------------------------------------------------

STATS_TTL_S = 600
TICKER_GWS = 6


class _Live:
    """The live season and lookups every stats request needs, reloaded every STATS_TTL_S."""

    def __init__(self) -> None:
        from diffpl.api.plan import LIVE_SEASON, next_gw
        from diffpl.replay.data import load_live

        self.data = load_live(engine(), LIVE_SEASON)
        self.gw, _ = next_gw(self.data.deadlines, datetime.now(UTC))
        with engine().connect() as conn:
            teams = conn.execute(
                text(
                    "select team_id, team_name, short_name from staging.stg_fpl__teams "
                    "where as_of = (select max(as_of) from staging.stg_fpl__teams)"
                )
            ).fetchall()
            owned = conn.execute(
                text(
                    "select element_id, selected_by_percent from staging.stg_fpl__elements "
                    "where as_of = (select max(as_of) from staging.stg_fpl__elements)"
                )
            ).fetchall()
        self.short = {str(r[1]): str(r[2]) for r in teams}
        self.short_by_id = {int(r[0]): str(r[2]) for r in teams}
        self.ownership = {int(r[0]): float(r[1] or 0) for r in owned}
        self._dist: dict[int, list[float]] | None = None
        self._p60: dict[int, float] = {}
        self._xp: dict[int, float] | None = None
        self._players: dict[int, PlayerRow] | None = None

    def _projections(self) -> None:
        """Champion's next-GW points distribution and P(60+ minutes), computed once."""
        from diffpl.features.build import gw_features
        from diffpl.models.two_part import TwoPartModel

        model = champion_model()
        assert isinstance(model, TwoPartModel)
        feats = gw_features(self.data.observe(self.gw))
        ids = [int(e) for e in feats["element_id"].to_list()]
        probs = model.predict_dist(feats)
        p60 = model.predict_minutes(feats)[:, 2]
        self._dist = {
            e: [round(float(p), 4) for p in row] for e, row in zip(ids, probs, strict=True)
        }
        self._p60 = {e: round(float(p), 3) for e, p in zip(ids, p60, strict=True)}

    def distribution(self) -> tuple[list[float], dict[int, list[float]], dict[int, float]]:
        """(bin values, per-player bin probabilities, per-player P(60+ minutes))."""
        from diffpl.models.two_part import TwoPartModel

        model = champion_model()
        assert isinstance(model, TwoPartModel) and model.bin_values is not None
        if self._dist is None:
            self._projections()
        return [float(v) for v in model.bin_values], self._dist or {}, self._p60

    def xp_horizon(self) -> dict[int, float]:
        """Champion's expected points summed over the planning horizon, per player."""
        if self._xp is None:
            xp: dict[int, float] = {}
            for per_gw in champion_projector()(self.data.observe(self.gw)).values():
                for i, v in per_gw.items():
                    xp[i] = xp.get(i, 0.0) + v
            self._xp = xp
        return self._xp

    def players(self) -> dict[int, PlayerRow]:
        if self._players is None:
            rows = player_table(self.data, self.short, self.ownership)
            self._players = {r.element_id: r for r in rows}
        return self._players


_live: tuple[float, _Live] | None = None
_live_lock = threading.Lock()


def live() -> _Live:
    global _live
    with _live_lock:
        if _live is None or time.monotonic() - _live[0] > STATS_TTL_S:
            _live = (time.monotonic(), _Live())
        return _live[1]


@cache
def champion_model() -> object:
    import mlflow
    from mlflow import MlflowClient

    from diffpl.models.two_part import TwoPartModel
    from diffpl.sim.__main__ import load_version

    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    return TwoPartModel.load(load_version(MlflowClient(), "champion", None))


@app.get("/api/stats/players", response_model=list[PlayerRow])
def stats_players() -> list[PlayerRow]:
    return list(live().players().values())


@app.get("/api/stats/players/{element_id}", response_model=PlayerDetail)
def stats_player(element_id: int = Path(gt=0, lt=10_000)) -> PlayerDetail:
    lv = live()
    row = lv.players().get(element_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no matches for player {element_id}")
    bins, dist, p60 = lv.distribution()
    return PlayerDetail(
        row=row,
        matches=player_matches(lv.data, element_id, lv.short_by_id),
        points_bins=bins if element_id in dist else [],
        points_probs=dist.get(element_id, []),
        p60=p60.get(element_id),
        xp_horizon=round(lv.xp_horizon().get(element_id, 0.0), 1),
        horizon=HORIZON,
    )


@app.get("/api/stats/teams", response_model=list[TeamForm])
def stats_teams() -> list[TeamForm]:
    lv = live()
    return team_form(lv.data, lv.short)


@app.get("/api/stats/fixtures", response_model=list[TickerRow])
def stats_fixtures() -> list[TickerRow]:
    lv = live()
    return fixture_ticker(lv.data, lv.gw, TICKER_GWS, lv.short)


# --- Mini-leagues ----------------------------------------------------------------------------

TOP_LEAGUE_ID = 314  # overall league; its first 100 members are the template reference


@app.get("/api/league/{league_id}", response_model=LeagueView)
def league(
    league_id: int = Path(gt=0, lt=100_000_000),
    team: int | None = Query(default=None, gt=0, lt=100_000_000),
) -> LeagueView:
    from diffpl.leagues.report import load_league

    try:
        data = load_league(engine(), league_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        reference, name = load_league(engine(), TOP_LEAGUE_ID), "overall top 100"
    except LookupError:
        reference, name = data, "this league (top 100 not ingested)"
    lv = live()
    return league_view(data, team, reference, name, lv.players(), lv.xp_horizon())
