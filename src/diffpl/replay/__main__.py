"""Replay baseline managers through past seasons.

uv run python -m diffpl.replay --season 2024-25 --manager form [--manager template ...]
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from sqlalchemy import create_engine

from diffpl.replay.baselines import make_baseline
from diffpl.replay.data import load_season
from diffpl.replay.run import run_season
from diffpl.rules import load_rules
from diffpl.settings import get_settings

BASELINES = ("template", "form", "fixtures")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.replay")
    parser.add_argument("--season", action="append", required=True)
    parser.add_argument("--manager", action="append", choices=BASELINES)
    parser.add_argument("--json", action="store_true", help="print one JSON line per run")
    args = parser.parse_args(argv)

    engine = create_engine(get_settings().database_url)
    for season in args.season:
        data = load_season(engine, season)
        rules = load_rules(season)
        for name in args.manager or BASELINES:
            result = run_season(data, rules, make_baseline(name, rules))
            summary = result.summary()
            if args.json:
                print(json.dumps(summary))
            else:
                print(
                    f"{season}  {name:<9} {summary['total_points']:>5} pts  "
                    f"transfers {summary['transfers']:>3}  hits {summary['hit_cost']:>3}  "
                    f"violations {summary['violations']}"
                )


if __name__ == "__main__":
    main()
