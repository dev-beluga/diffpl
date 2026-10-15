"""Mini-league snapshots from the public FPL API into `raw.fpl_api_responses` (ADR-0005).

For one classic league: standings pages, each member's season history, and each member's
picks for every GW whose deadline has passed. Read-only; nothing is written to FPL.
Picks for finished GWs never change, so they are cached forever.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from diffpl.ingest.fpl_api import API_TTL, endpoint_url, fetch_bootstrap, to_row
from diffpl.ingest.http import CachedFetcher


def standings_endpoint(league_id: int, page: int) -> str:
    return f"leagues-classic/{league_id}/standings/?page_standings={page}"


def league_url(endpoint: str) -> str:
    """Like endpoint_url, but keeps a query string after the trailing slash."""
    path, _, query = endpoint.partition("?")
    url = endpoint_url(path.rstrip("/"))
    return f"{url}?{query}" if query else url


def fetch_members(
    fetcher: CachedFetcher, league_id: int, max_members: int
) -> tuple[list[dict[str, Any]], list[int]]:
    """Standings rows and member entry ids, up to max_members."""
    rows: list[dict[str, Any]] = []
    entries: list[int] = []
    page = 1
    while len(entries) < max_members:
        fetched = fetcher.get(league_url(standings_endpoint(league_id, page)), ttl=API_TTL)
        row = to_row("leagues-classic-standings", fetched)
        rows.append(row)
        standings = row["payload"]["standings"]
        entries += [int(r["entry"]) for r in standings["results"]]
        if not standings["has_next"]:
            break
        page += 1
    return rows, entries[:max_members]


def fetch_league(
    fetcher: CachedFetcher, league_id: int, *, max_members: int = 50
) -> Iterator[dict[str, Any]]:
    _, bootstrap = fetch_bootstrap(fetcher)
    started = [e for e in bootstrap["events"] if e.get("finished") or e.get("is_current")]
    standings, entries = fetch_members(fetcher, league_id, max_members)
    yield from standings
    for entry in entries:
        yield to_row(
            "entry-history", fetcher.get(endpoint_url(f"entry/{entry}/history"), ttl=API_TTL)
        )
        for event in started:
            ttl = None if event.get("finished") else API_TTL
            url = endpoint_url(f"entry/{entry}/event/{event['id']}/picks")
            yield to_row("entry-picks", fetcher.get(url, ttl=ttl))
