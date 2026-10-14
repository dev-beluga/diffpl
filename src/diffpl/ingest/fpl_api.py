"""Snapshots of the public FPL API into `raw.fpl_api_responses`.

The API is unofficial and undocumented, so payloads are stored whole as JSON. Parsing happens
in dbt staging models, where a schema change shows up as a failing test instead of lost data.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from diffpl.ingest.http import CachedFetcher, Fetched

BASE_URL = "https://fantasy.premierleague.com/api"
API_TTL = timedelta(hours=1)


def endpoint_url(endpoint: str) -> str:
    return f"{BASE_URL}/{endpoint}/"


def to_row(endpoint: str, fetched: Fetched) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "url": fetched.url,
        "payload_sha256": fetched.sha256,
        "payload": json.loads(fetched.body),
        "fetched_at": fetched.fetched_at,
    }


def fetch_bootstrap(fetcher: CachedFetcher) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the raw row and the parsed payload, which lists every player id."""
    fetched = fetcher.get(endpoint_url("bootstrap-static"), ttl=API_TTL)
    row = to_row("bootstrap-static", fetched)
    return row, row["payload"]


def fetch_snapshot(
    fetcher: CachedFetcher, *, with_players: bool = True
) -> Iterator[dict[str, Any]]:
    """Yield raw rows for bootstrap-static, fixtures and, optionally, every element-summary."""
    bootstrap_row, bootstrap = fetch_bootstrap(fetcher)
    yield bootstrap_row
    yield to_row("fixtures", fetcher.get(endpoint_url("fixtures"), ttl=API_TTL))
    if not with_players:
        return
    for element in bootstrap["elements"]:
        endpoint = f"element-summary/{element['id']}"
        yield to_row("element-summary", fetcher.get(endpoint_url(endpoint), ttl=API_TTL))
