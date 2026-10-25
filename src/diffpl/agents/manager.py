"""Let an agent play replay seasons as a Manager (ADR-0017).

Each deadline the agent gets only that deadline's tools. A decision the harness rejects, or any
failure, is replaced by a safe default: keep the squad, play the best lineup by projection.
Every outcome is kept, so a season reports its failures, tokens, cost and latency next to its
points.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from diffpl.agents.harness import (
    Agent,
    Budget,
    LiveTools,
    Outcome,
    RecordingTools,
    Trap,
    run_decision,
    write_trajectory,
)
from diffpl.mcp.tools import ToolContext
from diffpl.optim.planner import Projector
from diffpl.replay.baselines import best_lineup
from diffpl.replay.data import Observation
from diffpl.replay.types import Decision, InitialSquad, Manager, ManagerView
from diffpl.rules import Rules


def safe_decision(ctx: ToolContext) -> Decision:
    """No transfers, best lineup by expected points this gameweek."""
    ids = [p.element_id for p in ctx.squad.picks]
    d = best_lineup(ctx.rules, ids, ctx.xp.get(ctx.obs.gw, {}), ctx.market.position)
    return Decision(d.lineup, d.bench, d.captain, d.vice_captain)


@dataclass
class AgentManager:
    name: str
    rules: Rules
    project: Projector
    agent: Agent
    initial: Manager  # picks the GW1 squad: agents decide from GW2
    budget: Budget = field(default_factory=Budget)
    trap: Callable[[Observation], Trap | None] | None = None
    out_dir: Path | None = None  # one trajectory file per season
    outcomes: list[tuple[str, int, Outcome]] = field(default_factory=list)  # season, gw, outcome

    def pick_squad(self, view: ManagerView) -> InitialSquad:
        return self.initial.pick_squad(view)

    def act(self, view: ManagerView) -> Decision:
        assert view.squad is not None
        ctx = ToolContext(view.obs, view.squad, self.rules, self.project)
        outcome = run_decision(
            self.agent,
            RecordingTools(LiveTools(ctx)),
            ctx,
            self.budget,
            self.trap(view.obs) if self.trap else None,
        )
        self.outcomes.append((view.obs.season, view.obs.gw, outcome))
        if self.out_dir:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            write_trajectory(
                self.out_dir / f"{self.name}-{view.obs.season}.jsonl",
                f"{view.obs.season}-gw{view.obs.gw}",
                outcome,
            )
        return outcome.decision or safe_decision(ctx)

    def report(self) -> dict[str, object]:
        """What the season cost and how it failed."""
        done = [o for _, _, o in self.outcomes]
        return {
            "decisions": len(done),
            "invalid": sum(not o.valid for o in done),
            "failures": dict(Counter(k for o in done for k in o.kinds())),
            "tokens": sum(o.usage.tokens for o in done),
            "cost_usd": round(sum(o.usage.cost_usd for o in done), 6),
            "mean_seconds": round(sum(o.seconds for o in done) / max(len(done), 1), 3),
        }
