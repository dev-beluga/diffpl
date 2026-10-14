"""Historical seasons from github.com/vaastav/Fantasy-Premier-League into `raw.vaastav_rows`.

Downloads are pinned to a commit so a re-run reads the same bytes. Each CSV row is stored as a
JSON object of strings; typing and `as_of` derivation happen in dbt staging.

Leakage note: `players_raw.csv` is an end-of-season snapshot (final prices, news, totals). It
must never feed a feature for a gameweek inside that season.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from diffpl.ingest.http import CachedFetcher, FetchError

log = logging.getLogger(__name__)

REPO = "vaastav/Fantasy-Premier-League"
SEASON_FILES = ("gws/merged_gw.csv", "fixtures.csv", "teams.csv", "players_raw.csv")
# 2016-17 and 2017-18 have no fixtures.csv or teams.csv; 2018-19 has no teams.csv.
OPTIONAL_FILES = frozenset({"fixtures.csv", "teams.csv"})
SEASON_RE = re.compile(r"^\d{4}-\d{2}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def file_url(commit: str, season: str, file: str) -> str:
    return f"https://raw.githubusercontent.com/{REPO}/{commit}/data/{season}/{file}"


def resolve_commit(fetcher: CachedFetcher, ref: str) -> str:
    """Return the commit SHA for a branch, tag or SHA."""
    if SHA_RE.match(ref):
        return ref
    url = f"https://api.github.com/repos/{REPO}/commits/{ref}"
    fetched = fetcher.get(url, ttl=timedelta(minutes=5))
    sha = str(json.loads(fetched.body)["sha"])
    if not SHA_RE.match(sha):
        raise ValueError(f"unexpected commit sha for {ref}: {sha!r}")
    return sha


def decode(body: bytes) -> str:
    """Older seasons are not all UTF-8; fall back to cp1252."""
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return body.decode("cp1252")


def parse_csv(text: str) -> Iterator[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    for record in reader:
        yield {k: v for k, v in record.items() if k is not None}


def fetch_season(fetcher: CachedFetcher, commit: str, season: str) -> Iterator[dict[str, Any]]:
    if not SEASON_RE.match(season):
        raise ValueError(f"season must look like 2024-25, got {season!r}")
    if not SHA_RE.match(commit):
        raise ValueError("commit must be a full 40-character SHA")
    for file in SEASON_FILES:
        try:
            fetched = fetcher.get(file_url(commit, season, file), ttl=None)
        except FetchError as exc:
            if exc.status == 404 and file in OPTIONAL_FILES:
                log.info("vaastav %s has no %s, skipping", season, file)
                continue
            raise
        for row_num, data in enumerate(parse_csv(decode(fetched.body))):
            yield {
                "source_commit": commit,
                "season": season,
                "file": file,
                "row_num": row_num,
                "data": data,
                "fetched_at": fetched.fetched_at,
            }
