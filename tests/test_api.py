"""Web API: plan endpoint shape, caching, errors; next-deadline lookup."""

from collections.abc import Iterator
from datetime import UTC, datetime

import polars as pl
import pytest
from fastapi.testclient import TestClient

from diffpl.api import app as api
from diffpl.api.plan import GwPlan, PlanOut, Player, next_gw

NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)


def gw_plan(team_id: int) -> GwPlan:
    p = Player(
        element_id=1,
        name="Raya",
        team="ARS",
        position="GKP",
        price=5.5,
        xp=4.3,
        fixtures=["EVE (H)"],
    )
    return GwPlan(
        team_id=team_id,
        gw=8,
        deadline=NOW,
        bank=0.5,
        free_transfers=2,
        squad_value=101.2,
        horizon=4,
        picks_gw=7,
        data_as_of=NOW,
        plans=[PlanOut(rank=1, objective=180.0, hits=0, starters=[p], bench=[], transfers=[])],
    )


@pytest.fixture
def client() -> Iterator[tuple[TestClient, list[int]]]:
    calls: list[int] = []

    def build(team_id: int) -> GwPlan:
        calls.append(team_id)
        if team_id == 404:
            raise LookupError("no picks for team 404")
        return gw_plan(team_id)

    api._cache.clear()
    api.app.dependency_overrides[api.get_builder] = lambda: build
    yield TestClient(api.app), calls
    api.app.dependency_overrides.clear()
    api._cache.clear()


def test_health(client: tuple[TestClient, list[int]]) -> None:
    assert client[0].get("/api/health").json() == {"status": "ok"}


def test_plan_returns_the_built_plan_and_caches_it(
    client: tuple[TestClient, list[int]],
) -> None:
    c, calls = client
    first = c.get("/api/plan/1728543")
    second = c.get("/api/plan/1728543")
    assert first.status_code == 200 and first.json() == second.json()
    assert first.json()["plans"][0]["starters"][0]["name"] == "Raya"
    assert calls == [1728543]  # solved once


def test_unknown_team_is_404_and_bad_id_is_422(client: tuple[TestClient, list[int]]) -> None:
    c, _ = client
    assert c.get("/api/plan/404").status_code == 404
    assert c.get("/api/plan/0").status_code == 422
    assert c.get("/api/plan/abc").status_code == 422


def test_next_gw_handles_etc_utc_deadlines() -> None:
    deadlines = pl.DataFrame(
        {"gw": [7, 8], "deadline_time": [datetime(2026, 10, 17, 10), datetime(2026, 10, 23, 17)]}
    ).with_columns(pl.col("deadline_time").dt.replace_time_zone("Etc/UTC"))
    gw, deadline = next_gw(deadlines, NOW)
    assert gw == 8 and deadline.hour == 17
    with pytest.raises(LookupError):
        next_gw(deadlines, datetime(2027, 1, 1, tzinfo=UTC))
