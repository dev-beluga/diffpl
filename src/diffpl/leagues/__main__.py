"""Mini-league report.

uv run python -m diffpl.leagues --id 123456 [--entry 987] [--gw 7]
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import polars as pl
from sqlalchemy import create_engine

from diffpl.leagues.report import exposure, load_league, weekly_outcomes
from diffpl.leagues.rules import load_league_rules
from diffpl.settings import get_settings


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.leagues")
    parser.add_argument("--id", type=int, required=True, help="FPL classic league id")
    parser.add_argument("--entry", type=int, help="your FPL team id, for differentials")
    parser.add_argument("--gw", type=int, help="gameweek for ownership (default: latest)")
    args = parser.parse_args(argv)

    data = load_league(create_engine(get_settings().database_url), args.id)
    rules = load_league_rules(args.id)
    names = dict(zip(data.managers["entry_id"], data.managers["entry_name"], strict=True))
    pl.Config.set_tbl_rows(30).set_tbl_hide_dataframe_shape(True).set_fmt_str_lengths(30)

    print(f"League {args.id}: {data.managers.height} managers, GW{data.last_gw}\n")
    print(
        data.managers.sort("rank").select(
            "rank",
            "entry_name",
            "total_points",
            (pl.col("value_tenths") / 10).alias("value"),
            (pl.col("bank_tenths") / 10).alias("bank"),
            "hit_cost",
            "transfers",
            "chips_used",
        )
    )

    outcomes, overall = weekly_outcomes(data, rules)
    print("\nWeekly winners (league rules):")
    for o in outcomes:
        who = ", ".join(names.get(e, str(e)) for e in o.winners) or "none"
        notes = [
            f"{names.get(s.entry_id, s.entry_id)}: {'; '.join(s.notes)}"
            for s in o.scores
            if s.notes
        ]
        print(
            f"  GW{o.gw:<2} {who}  ({o.explanation})"
            + (f"  [{' | '.join(notes)}]" if notes else "")
        )
    print("\nOverall (league rules):")
    for rank, (e, pts) in enumerate(sorted(overall.items(), key=lambda kv: -kv[1]), start=1):
        print(f"  {rank:>2}. {names.get(e, e)}  {pts}")

    gw = args.gw or data.last_gw
    top = data.ownership.filter(pl.col("gw") == gw).join(data.names, on="element_id", how="left")
    print(f"\nMost owned in the league, GW{gw}:")
    print(
        top.sort("effective_ownership", descending=True)
        .head(10)
        .select("web_name", "ownership", "effective_ownership", "captains")
    )

    if args.entry is not None:
        ex = exposure(data, args.entry, gw).select(
            "web_name", "mine", "ownership", "effective_ownership", "exposure"
        )
        print(f"\nYour differentials (exposure > 0), GW{gw}:")
        print(ex.filter(pl.col("exposure") > 0).head(8))
        print(f"\nYour threats (exposure < 0), GW{gw}:")
        print(ex.filter(pl.col("exposure") < 0).head(8))


if __name__ == "__main__":
    main()
