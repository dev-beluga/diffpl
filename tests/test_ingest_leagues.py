from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import Engine

from diffpl.ingest import fpl_leagues
from diffpl.ingest.http import CachedFetcher
from diffpl.ingest.store import fpl_api_responses, insert_new

FIXTURES = Path(__file__).parent / "fixtures" / "fpl_leagues"
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/api/").strip("/")
    if path == "bootstrap-static":
        name = "bootstrap-static"
    elif path.startswith("leagues-classic/"):
        name = f"standings-{request.url.params['page_standings']}"
    elif path.endswith("/history"):
        name = "entry-history"
    elif "/event/" in path and path.endswith("/picks"):
        name = "entry-picks"
    else:
        return httpx.Response(404)
    return httpx.Response(200, content=(FIXTURES / f"{name}.json").read_bytes())


def fetcher(tmp_path: Path) -> CachedFetcher:
    return CachedFetcher(
        tmp_path, min_interval=0, transport=httpx.MockTransport(handler), clock=lambda: NOW
    )


def test_league_snapshot_pages_members_and_started_gws(tmp_path: Path) -> None:
    with fetcher(tmp_path) as f:
        rows = list(fpl_leagues.fetch_league(f, 999))
    endpoints = [r["endpoint"] for r in rows]
    assert endpoints.count("leagues-classic-standings") == 2
    assert endpoints.count("entry-history") == 3
    # GW1 finished and GW2 current have picks; GW3 has not started.
    picks = [r["url"] for r in rows if r["endpoint"] == "entry-picks"]
    assert len(picks) == 3 * 2
    assert not any("/event/3/" in u for u in picks)


def test_member_cap(tmp_path: Path) -> None:
    with fetcher(tmp_path) as f:
        rows = list(fpl_leagues.fetch_league(f, 999, max_members=2))
    endpoints = [r["endpoint"] for r in rows]
    assert endpoints.count("leagues-classic-standings") == 1
    assert endpoints.count("entry-history") == 2


def test_rerun_adds_nothing(tmp_path: Path, engine: Engine) -> None:
    with fetcher(tmp_path) as f:
        first = insert_new(engine, fpl_api_responses, fpl_leagues.fetch_league(f, 999))
        second = insert_new(engine, fpl_api_responses, fpl_leagues.fetch_league(f, 999))
    assert first > 0
    assert second == 0


def test_standings_url_keeps_query() -> None:
    url = fpl_leagues.league_url(fpl_leagues.standings_endpoint(999, 2))
    assert (
        url
        == "https://fantasy.premierleague.com/api/leagues-classic/999/standings/?page_standings=2"
    )
