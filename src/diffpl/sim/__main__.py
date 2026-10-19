"""Evaluate joint simulation on team totals (ADR-0009).

uv run python -m diffpl.sim eval [--events-version N]

Player marginals cannot tell dependence apart, so the test is a team's total points in a GW
(sum over its players). Three joint models are scored on the test seasons:
- independent: champion marginals, columns shuffled (no dependence);
- events: the event model's own simulations;
- hybrid: champion marginals with the event model's ranks.
Metrics: CRPS of the team total (lower is better) and 50% / 80% interval coverage.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import polars as pl
from sqlalchemy import create_engine

from diffpl.models.events import EventModel
from diffpl.models.two_part import TwoPartModel
from diffpl.replay.data import load_season
from diffpl.rules import load_rules
from diffpl.settings import get_settings
from diffpl.sim.copula import shuffle_columns
from diffpl.sim.simulate import simulate

TEST = ("2024-25", "2025-26")
REGISTERED = "projections"
log = logging.getLogger("diffpl.sim")


def crps(samples: np.ndarray, y: float) -> float:
    """Sample CRPS: E|X - y| - E|X - X'| / 2, with the sorted-sample formula for the second
    term."""
    x = np.sort(samples)
    n = len(x)
    spread = (2 * np.arange(1, n + 1) - n - 1) @ x / (n * n)
    return float(np.abs(x - y).mean() - spread)


def interval_hits(samples: np.ndarray, y: float, level: float) -> bool:
    lo, hi = np.quantile(samples, [(1 - level) / 2, 1 - (1 - level) / 2])
    return bool(lo <= y <= hi)


def score_teams(
    team: list[str], actual: np.ndarray, joints: dict[str, np.ndarray]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    teams = np.array(team)
    for t in sorted(set(team)):
        m = teams == t
        y = float(actual[m].sum())
        for name, sims in joints.items():
            total = sims[:, m].sum(axis=1)
            rows.append(
                {
                    "method": name,
                    "team": t,
                    "crps": crps(total, y),
                    "cov50": interval_hits(total, y, 0.5),
                    "cov80": interval_hits(total, y, 0.8),
                }
            )
    return rows


def load_version(client: object, alias: str | None, version: str | None) -> Path:
    import mlflow

    v = (
        client.get_model_version(REGISTERED, version)  # type: ignore[attr-defined]
        if version
        else client.get_model_version_by_alias(REGISTERED, alias)  # type: ignore[attr-defined]
    )
    return Path(mlflow.artifacts.download_artifacts(run_id=v.run_id, artifact_path="model"))


def eval_cmd(events_version: str | None) -> None:
    import mlflow
    from mlflow import MlflowClient

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient()
    champion = TwoPartModel.load(load_version(client, "champion", None))
    events = EventModel.load(load_version(client, "challenger", events_version))
    engine = create_engine(settings.database_url)
    rng = np.random.default_rng(settings.seed)

    rows = []
    for season in TEST:
        start = int(season[:4]) - 1
        prev = load_season(engine, f"{start}-{str(start + 1)[2:]}")
        data, rules = load_season(engine, season), load_rules(season)
        for gw in data.gameweeks:
            j = simulate(data.observe(gw), champion, events, prev, rules, settings.seed)
            pts = (
                data.player_matches.filter(pl.col("gw") == gw)
                .group_by("element_id")
                .agg(pl.col("total_points").sum())
            )
            got = dict(zip(pts["element_id"].to_list(), pts["total_points"].to_list(), strict=True))
            actual = np.array([got.get(e, 0) for e in j.element_id.tolist()], dtype=float)
            joints = {
                "independent": shuffle_columns(j.sims, rng),
                "events": j.events,
                "hybrid": j.sims,
            }
            rows += [{"season": season, "gw": gw, **r} for r in score_teams(j.team, actual, joints)]
            log.info("sim %s GW%d", season, gw)

    df = pl.DataFrame(rows)
    out = df.group_by("method").agg(
        pl.len().alias("team_gws"),
        pl.col("crps").mean(),
        pl.col("cov50").mean(),
        pl.col("cov80").mean(),
    )
    print(out.sort("crps").with_columns(pl.col(pl.Float64).round(3)))
    mlflow.set_experiment("simulation")
    with mlflow.start_run(run_name="sim_eval"):
        mlflow.log_param("events_version", events_version or "challenger")
        for r in out.iter_rows(named=True):
            for k in ("crps", "cov50", "cov80"):
                mlflow.log_metric(f"sim.{r['method']}.{k}", r[k])


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.sim")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("eval", help="score joint simulation on team totals, test seasons")
    ev.add_argument("--events-version", help="event model version (default: challenger alias)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.cmd == "eval":
        eval_cmd(args.events_version)


if __name__ == "__main__":
    main()
