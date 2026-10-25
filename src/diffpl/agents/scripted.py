"""Scripted agents: no model, no cost. They test the harness and set the league's floor."""

from __future__ import annotations

from typing import Any

from diffpl.agents.harness import Action, Brief, Submit, ToolCall, Usage


class PlannerAgent:
    """Asks the optimizer for its best plan and submits it unchanged. It plays the same moves as
    `PlannerManager`, so a season run through the harness must score the same (the plumbing
    proof) and every LLM agent has a planner-grade bar to beat."""

    name = "planner_agent"

    def start(self, brief: Brief) -> None:
        pass

    def next(self, observation: dict[str, Any] | None) -> tuple[Action, Usage]:
        if observation is None:
            return ToolCall("plan_transfers", {"n_plans": 1}), Usage()
        plan = observation["plans"][0]
        return (
            Submit(
                {
                    "lineup": plan["lineup"],
                    "bench": plan["bench"],
                    "captain": plan["captain"],
                    "vice_captain": plan["vice_captain"],
                    "transfers": [
                        {"out_id": t["out"]["id"], "in_id": t["in"]["id"]}
                        for t in plan["transfers"]
                    ],
                }
            ),
            Usage(),
        )
