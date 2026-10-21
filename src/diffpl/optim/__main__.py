"""Replay the rank-aware planner against a rival on the test seasons (ADR-0011).

uv run python -m diffpl.optim eval [--events-version N]

Each deadline's simulated draws are cached under ~/.cache/diffpl/draws, so a run that is
stopped resumes at the first deadline not yet simulated.

History has no real rivals, so the rival is the greedy champion manager playing the same
season. Its last decision before each deadline is what the rank-aware planner sees. Both the
EV planner (ADR-0010) and the rank-aware planner are scored head to head against it: share of
GWs won (ties count half) and season points. Results go to MLflow (run name `planner_eval`).
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl
from sqlalchemy import create_engine

from diffpl.models.events import EventModel
from diffpl.models.two_part import TwoPartModel
from diffpl.optim.planner import HORIZON, PlannerManager, fixture_horizon
from diffpl.optim.rival import Draws, RivalManager, RivalView
from diffpl.replay.baselines import GreedyManager
from diffpl.replay.data import Observation, SeasonData, load_season
from diffpl.replay.run import RunResult, run_season
from diffpl.replay.types import Decision, InitialSquad, Manager, ManagerView
from diffpl.rules import Rules, load_rules
from diffpl.settings import get_settings

TEST = ("2024-25", "2025-26")
REGISTERED = "projections"
# Each deadline's joint draws, so a killed run resumes without re-simulating. Stored exactly
# (float64) so a resumed run matches a fresh one. Kept on the home filesystem: under WSL,
# large writes to the Windows mount (/mnt/c) failed with EIO.
DRAWS_CACHE = Path.home() / ".cache" / "diffpl" / "draws"
RIVAL_ID = 1
log = logging.getLogger("diffpl.optim")


@dataclass
class Recording:
    """Wraps the rival and keeps the decision it played at each GW."""

    inner: Manager
    decisions: dict[int, Decision] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.inner.name

    def pick_squad(self, view: ManagerView) -> InitialSquad:
        out = self.inner.pick_squad(view)
        self.decisions[view.obs.gw] = out.decision
        return out

    def act(self, view: ManagerView) -> Decision:
        out = self.inner.act(view)
        self.decisions[view.obs.gw] = out
        return out


def head_to_head(me: RunResult, rival: RunResult) -> list[float]:
    """Per GW: 1 for a win, 0.5 for a tie, 0 for a loss, on points after hits."""
    theirs = {g.gw: g.points for g in rival.gws}
    return [float(g.points > theirs[g.gw]) + 0.5 * (g.points == theirs[g.gw]) for g in me.gws]


def eval_cmd(events_version: str | None) -> None:
    import mlflow
    from mlflow import MlflowClient

    from diffpl.models.__main__ import two_part_scorer
    from diffpl.sim.__main__ import load_version
    from diffpl.sim.simulate import simulate

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient()
    champion = TwoPartModel.load(load_version(client, "champion", None))
    events = EventModel.load(load_version(client, "challenger", events_version))
    champ_v = client.get_model_version_by_alias(REGISTERED, "champion").version
    events_v = events_version or client.get_model_version_by_alias(REGISTERED, "challenger").version
    engine = create_engine(settings.database_url)
    score = two_part_scorer(champion)
    project = fixture_horizon(score, HORIZON)

    summary, rows = [], []
    for season in TEST:
        start = int(season[:4]) - 1
        prev = load_season(engine, f"{start}-{str(start + 1)[2:]}")
        data, rules = load_season(engine, season), load_rules(season)

        rival = Recording(GreedyManager("two_part", rules, score))
        rival_run = run_season(data, rules, rival)

        def rival_of(obs: Observation, rival: Recording = rival) -> RivalView | None:
            last = rival.decisions.get(obs.gw - 1)
            return RivalView(RIVAL_ID, last) if last else None

        def draws(obs: Observation, prev: SeasonData = prev, rules: Rules = rules) -> Draws:
            path = (
                DRAWS_CACHE / f"{obs.season}_gw{obs.gw}_c{champ_v}_e{events_v}_s{settings.seed}.npz"
            )
            if path.exists():
                with np.load(path) as f:
                    return Draws(f["element_id"], f["points"])
            j = simulate(obs, champion, events, prev, rules, settings.seed)
            tmp = path.with_suffix(".tmp.npz")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                np.savez(tmp, element_id=j.element_id, points=j.hybrid)
                tmp.replace(path)  # a kill mid-write leaves no half file under the real name
            except OSError as exc:  # the cache only saves time; never fail the eval over it
                log.warning("could not cache draws at %s: %s", path, exc)
            log.info("planner %s GW%d simulated", obs.season, obs.gw)
            return Draws(j.element_id, j.hybrid)

        rank_aware = RivalManager("rank_aware", rules, project, draws, rival_of)
        managers: tuple[Manager, ...] = (PlannerManager("planner", rules, project), rank_aware)
        for m in managers:
            run = run_season(data, rules, m)
            h2h = head_to_head(run, rival_run)
            summary.append(
                {
                    "season": season,
                    "manager": m.name,
                    "points": run.total_points,
                    "rival_points": rival_run.total_points,
                    "h2h": sum(h2h) / len(h2h),
                    "hits": run.hit_cost,
                    "violations": len(run.violations),
                }
            )
            choice = {c.gw: c for c in rank_aware.choices} if m is rank_aware else {}
            theirs = {g.gw: g.points for g in rival_run.gws}
            for g, w in zip(run.gws, h2h, strict=True):
                c = choice.get(g.gw)
                rows.append(
                    {
                        "season": season,
                        "manager": m.name,
                        "gw": g.gw,
                        "points": g.points,
                        "rival_points": theirs[g.gw],
                        "result": w,
                        "hit_cost": g.hit_cost,
                        "p_beat_chosen": c.p_beat[c.chosen] if c and c.p_beat else None,
                        "p_beat_ev_plan": c.p_beat[0] if c and c.p_beat else None,
                        "chosen_plan": c.chosen if c else None,
                        "transfers": " ".join(f"{o}>{i}" for o, i in c.transfers) if c else "",
                    }
                )

    table = pl.DataFrame(summary)
    print(table.with_columns(pl.col("h2h").round(3)))
    mlflow.set_experiment("planner")
    with mlflow.start_run(run_name="planner_eval"):
        mlflow.log_params(
            {
                "events_version": events_version or "challenger",
                "horizon": HORIZON,
                "seed": settings.seed,
            }
        )
        for r in table.iter_rows(named=True):
            key = f"{r['season']}.{r['manager']}"
            mlflow.log_metric(f"{key}.points", r["points"])
            mlflow.log_metric(f"{key}.h2h", r["h2h"])
            mlflow.log_metric(f"{key}.hits", r["hits"])
        with tempfile.TemporaryDirectory() as tmp:
            for name, df in (
                ("planner_summary.csv", table),
                ("planner_gws.csv", pl.DataFrame(rows)),
            ):
                path = Path(tmp) / name
                df.write_csv(path)
                mlflow.log_artifact(str(path))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.optim")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("eval", help="replay EV and rank-aware planners against a rival")
    ev.add_argument("--events-version", help="event model version (default: challenger alias)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.cmd == "eval":
        eval_cmd(args.events_version)


if __name__ == "__main__":
    main()
