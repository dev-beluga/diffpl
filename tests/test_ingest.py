import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, Table, func, select

from diffpl.ingest import fpl_api, vaastav
from diffpl.ingest.http import CachedFetcher, FetchError
from diffpl.ingest.store import fpl_api_responses, insert_new, vaastav_rows

FIXTURES = Path(__file__).parent / "fixtures"
COMMIT = "9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88"
FIXED_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def fpl_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/api/").strip("/")
    name = "element-summary" if path.startswith("element-summary/") else path
    return httpx.Response(200, content=(FIXTURES / "fpl_api" / f"{name}.json").read_bytes())


VAASTAV_FILES = {
    "gws/merged_gw.csv": "name,element,kickoff_time,total_points,GW\n"
    "Saka,2,2024-08-17T14:00:00Z,8,1\nRaya,1,2024-08-17T14:00:00Z,6,1\n",
    "fixtures.csv": "id,event,kickoff_time\n1,1,2024-08-17T14:00:00Z\n",
    "teams.csv": "id,name\n1,Arsenal\n",
    "players_raw.csv": "id,web_name\n1,Raya\n",
}


def vaastav_handler(request: httpx.Request) -> httpx.Response:
    file = request.url.path.split("/data/2024-25/", 1)[1]
    return httpx.Response(200, content=VAASTAV_FILES[file].encode())


Handler = Callable[[httpx.Request], httpx.Response]


def fetcher(tmp_path: Path, handler: Handler) -> CachedFetcher:
    return CachedFetcher(
        tmp_path,
        min_interval=0,
        transport=httpx.MockTransport(handler),
        clock=lambda: FIXED_NOW,
    )


def count(engine: Engine, table: Table) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def test_fpl_snapshot_stores_each_endpoint(tmp_path: Path, engine: Engine) -> None:
    with fetcher(tmp_path, fpl_handler) as f:
        rows = list(fpl_api.fetch_snapshot(f))

    assert [r["endpoint"] for r in rows] == [
        "bootstrap-static",
        "fixtures",
        "element-summary",
        "element-summary",
    ]
    assert all(r["fetched_at"] == FIXED_NOW for r in rows)
    assert insert_new(engine, fpl_api_responses, rows) == 4


def test_fpl_snapshot_rerun_adds_nothing(tmp_path: Path, engine: Engine) -> None:
    with fetcher(tmp_path, fpl_handler) as f:
        insert_new(engine, fpl_api_responses, fpl_api.fetch_snapshot(f, with_players=False))
        insert_new(engine, fpl_api_responses, fpl_api.fetch_snapshot(f, with_players=False))
    assert count(engine, fpl_api_responses) == 2


def test_vaastav_season_rows(tmp_path: Path, engine: Engine) -> None:
    with fetcher(tmp_path, vaastav_handler) as f:
        rows = list(vaastav.fetch_season(f, COMMIT, "2024-25"))

    gw_rows = [r for r in rows if r["file"] == "gws/merged_gw.csv"]
    assert [r["data"]["name"] for r in gw_rows] == ["Saka", "Raya"]
    assert gw_rows[0]["row_num"] == 0
    assert {r["file"] for r in rows} == set(vaastav.SEASON_FILES)
    assert insert_new(engine, vaastav_rows, rows) == 5
    assert insert_new(engine, vaastav_rows, rows) == 0


def test_vaastav_skips_missing_optional_files(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("fixtures.csv", "teams.csv")):
            return httpx.Response(404)
        return vaastav_handler(request)

    with fetcher(tmp_path, handler) as f:
        rows = list(vaastav.fetch_season(f, COMMIT, "2024-25"))
    assert {r["file"] for r in rows} == {"gws/merged_gw.csv", "players_raw.csv"}


def test_vaastav_missing_required_file_raises(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("merged_gw.csv"):
            return httpx.Response(404)
        return vaastav_handler(request)

    with fetcher(tmp_path, handler) as f, pytest.raises(FetchError, match="404"):
        list(vaastav.fetch_season(f, COMMIT, "2024-25"))


def test_vaastav_rejects_unpinned_commit(tmp_path: Path) -> None:
    with fetcher(tmp_path, vaastav_handler) as f, pytest.raises(ValueError, match="SHA"):
        list(vaastav.fetch_season(f, "master", "2024-25"))


def test_resolve_commit_passes_sha_through(tmp_path: Path) -> None:
    with fetcher(tmp_path, vaastav_handler) as f:
        assert vaastav.resolve_commit(f, COMMIT) == COMMIT


def test_resolve_commit_looks_up_branch(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/commits/master")
        return httpx.Response(200, content=json.dumps({"sha": COMMIT}).encode())

    with fetcher(tmp_path, handler) as f:
        assert vaastav.resolve_commit(f, "master") == COMMIT


def test_decode_falls_back_to_cp1252() -> None:
    assert vaastav.decode("Fábio".encode("cp1252")) == "Fábio"
    assert vaastav.decode("Fábio".encode()) == "Fábio"
