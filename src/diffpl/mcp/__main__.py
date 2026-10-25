"""Serve the read-only tools for a real team's next deadline over stdio (ADR-0016).

uv run python -m diffpl.mcp serve --team <team_id>

Needs `diffpl.ingest fpl` and the league ingest for the team, the dbt models, and the registered
champion in MLflow. Logs go to stderr: stdout carries the protocol.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

import polars as pl

from diffpl.mcp.server import build_server
from diffpl.mcp.tools import ToolContext

LIVE_SEASON = "2026-27"


def live_context(team_id: int) -> ToolContext:
    import mlflow
    from mlflow import MlflowClient
    from sqlalchemy import create_engine

    from diffpl.models.__main__ import two_part_scorer
    from diffpl.models.two_part import TwoPartModel
    from diffpl.optim.live import load_entry
    from diffpl.optim.planner import HORIZON, fixture_horizon
    from diffpl.replay.data import load_live
    from diffpl.replay.engine import Market
    from diffpl.rules import load_rules
    from diffpl.settings import get_settings
    from diffpl.sim.__main__ import load_version

    settings = get_settings()
    db = create_engine(settings.database_url)
    data = load_live(db, LIVE_SEASON)
    deadlines = data.deadlines.with_columns(pl.col("deadline_time").dt.convert_time_zone("UTC"))
    upcoming = deadlines.filter(pl.col("deadline_time") > datetime.now(UTC)).sort("gw")
    if upcoming.is_empty():
        raise LookupError("no upcoming deadline this season")
    gw = int(upcoming["gw"][0])
    obs = data.observe(gw)
    rules = load_rules(LIVE_SEASON)
    entry = load_entry(db, team_id, rules, Market.at(obs.prices, obs.players), gw)
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    champion = TwoPartModel.load(load_version(MlflowClient(), "champion", None))
    return ToolContext(obs, entry.squad, rules, fixture_horizon(two_part_scorer(champion), HORIZON))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.mcp")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="serve the tools over stdio")
    serve.add_argument("--team", type=int, required=True, help="FPL team id")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    if args.cmd == "serve":
        build_server(live_context(args.team)).run()


if __name__ == "__main__":
    main()
