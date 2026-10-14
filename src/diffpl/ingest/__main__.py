"""Command line entry point.

uv run python -m diffpl.ingest fpl [--no-players]
uv run python -m diffpl.ingest vaastav --season 2024-25 [--season ...] [--ref master]
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import create_engine

from diffpl.ingest import fpl_api, vaastav
from diffpl.ingest.http import CachedFetcher
from diffpl.ingest.store import create_tables, fpl_api_responses, insert_new, vaastav_rows
from diffpl.settings import get_settings

log = logging.getLogger("diffpl.ingest")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.ingest")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    sub = parser.add_subparsers(dest="source", required=True)
    fpl = sub.add_parser("fpl", help="snapshot the live FPL API")
    fpl.add_argument("--no-players", action="store_true", help="skip element-summary calls")
    hist = sub.add_parser("vaastav", help="load historical seasons")
    hist.add_argument("--season", action="append", required=True)
    hist.add_argument("--ref", default="master", help="branch, tag or commit SHA to pin")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    engine = create_engine(get_settings().database_url)
    create_tables(engine)

    with CachedFetcher(args.cache_dir) as fetcher:
        if args.source == "fpl":
            rows = list(fpl_api.fetch_snapshot(fetcher, with_players=not args.no_players))
            added = insert_new(engine, fpl_api_responses, rows)
            log.info("fpl api: %d responses fetched, %d new", len(rows), added)
        else:
            commit = vaastav.resolve_commit(fetcher, args.ref)
            for season in args.season:
                rows = list(vaastav.fetch_season(fetcher, commit, season))
                added = insert_new(engine, vaastav_rows, rows)
                log.info("vaastav %s @ %s: %d rows, %d new", season, commit[:7], len(rows), added)


if __name__ == "__main__":
    main()
