"""Play a replay season with an agent and report points, failures, tokens, cost and latency.

uv run python -m diffpl.agents run --agent planner --season 2024-25 [--out data/trajectories]

Projections come from the registered champion, as in `python -m diffpl.optim eval`.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from diffpl.agents.harness import Agent
from diffpl.agents.manager import AgentManager
from diffpl.agents.scripted import PlannerAgent

AGENTS: dict[str, Callable[[], Agent]] = {"planner": PlannerAgent}


def run_cmd(agent_name: str, season: str, out: Path | None) -> None:
    import mlflow
    from mlflow import MlflowClient
    from sqlalchemy import create_engine

    from diffpl.models.__main__ import two_part_scorer
    from diffpl.models.two_part import TwoPartModel
    from diffpl.optim.planner import HORIZON, PlannerManager, fixture_horizon
    from diffpl.replay.data import load_season
    from diffpl.replay.run import run_season
    from diffpl.rules import load_rules
    from diffpl.settings import get_settings
    from diffpl.sim.__main__ import load_version

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    champion = TwoPartModel.load(load_version(MlflowClient(), "champion", None))
    project = fixture_horizon(two_part_scorer(champion), HORIZON)
    data = load_season(create_engine(settings.database_url), season)
    rules = load_rules(season)
    manager = AgentManager(
        f"{agent_name}_agent",
        rules,
        project,
        AGENTS[agent_name](),
        initial=PlannerManager("planner", rules, project),
        out_dir=out,
    )
    result = run_season(data, rules, manager)
    print(f"{season} {manager.name}: {result.total_points} points")
    print(f"violations: {len(result.violations)}")
    print(manager.report())


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.agents")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="play one season with an agent")
    run.add_argument("--agent", choices=sorted(AGENTS), required=True)
    run.add_argument("--season", required=True)
    run.add_argument("--out", type=Path, help="write trajectories (JSON lines) here")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.cmd == "run":
        run_cmd(args.agent, args.season, args.out)


if __name__ == "__main__":
    main()
