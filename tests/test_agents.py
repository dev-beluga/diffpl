"""Agent harness: budgets, failure taxonomy, recording and replay, and season play."""

import json
from pathlib import Path
from typing import Any

import pytest
from test_mcp_tools import context, good_decision
from test_replay_baselines import Recorder, varied_season
from test_replay_run import LINEUP

from diffpl.agents.harness import (
    Action,
    Brief,
    Budget,
    LiveTools,
    RecordingTools,
    ReplayAgent,
    ReplayTools,
    Submit,
    ToolCall,
    Trap,
    Usage,
    run_decision,
    write_trajectory,
)
from diffpl.agents.manager import AgentManager, safe_decision
from diffpl.agents.scripted import PlannerAgent
from diffpl.mcp import tools
from diffpl.optim.planner import PlannerManager, Projector, fixture_horizon
from diffpl.replay.baselines import form_scores
from diffpl.replay.run import run_season
from diffpl.rules import load_rules

RULES = load_rules("2025-26")
GOOD = good_decision().model_dump()


class Script:
    """Plays a fixed list of actions, then repeats the last one."""

    name = "script"

    def __init__(self, *steps: Action | tuple[Action, Usage] | Exception) -> None:
        self.steps = steps
        self.at = 0

    def start(self, brief: Brief) -> None:
        self.at = 0

    def next(self, observation: dict[str, Any] | None) -> tuple[Action, Usage]:
        s = self.steps[min(self.at, len(self.steps) - 1)]
        self.at += 1
        if isinstance(s, Exception):
            raise s
        return s if isinstance(s, tuple) else (s, Usage())


def run(agent: Script | PlannerAgent, **kw: Any):  # type: ignore[no-untyped-def]
    ctx = context()
    return run_decision(agent, LiveTools(ctx), ctx, **kw), ctx


def test_planner_agent_submits_a_valid_decision_in_two_steps() -> None:
    out, _ = run(PlannerAgent())
    assert (
        out.valid
        and out.failures == []
        and [s.name for s in out.steps] == ["plan_transfers", "submit"]
    )


def test_unknown_tool_and_bad_arguments_are_recorded_and_the_agent_may_recover() -> None:
    agent = Script(
        ToolCall("delete_everything"),
        ToolCall("search_players", {"limit": "many"}),
        ToolCall("search_players", {"position": "STRIKER"}),
        Submit(GOOD),
    )
    out, _ = run(agent)
    assert out.valid and out.kinds() == ["wrong_tool", "bad_arguments", "bad_arguments"]
    assert [s.error is not None for s in out.steps] == [True, True, True, False]


def test_a_made_up_player_is_flagged_in_a_lookup_and_rejected_in_a_decision() -> None:
    out, _ = run(Script(ToolCall("get_player", {"player_id": 9999}), Submit(GOOD)))
    assert out.valid and out.kinds() == ["hallucinated_player"]
    bad = {**GOOD, "transfers": [{"out_id": SQUAD_FIRST, "in_id": 4242}]}
    out, _ = run(Script(Submit(bad)))
    assert not out.valid and out.kinds() == ["hallucinated_player"]


SQUAD_FIRST = LINEUP[0]


def test_a_rule_breaking_decision_is_rejected_with_the_reason() -> None:
    out, _ = run(Script(Submit({**GOOD, "vice_captain": GOOD["captain"]})))
    assert (
        not out.valid and out.kinds() == ["rule_violation"] and "captain" in out.failures[0].detail
    )
    out, _ = run(Script(Submit({"lineup": [1]})))
    assert not out.valid and out.kinds() == ["rule_violation"]


def test_budgets_stop_a_runaway_agent() -> None:
    loop = Script(ToolCall("squad"))
    out, _ = run(loop, budget=Budget(max_steps=3))
    assert not out.valid and out.kinds() == ["budget_overrun"] and len(out.steps) == 3
    out, _ = run(
        Script((Submit(GOOD), Usage(30_000, 20_000, 0.0))), budget=Budget(max_tokens=40_000)
    )
    assert not out.valid and out.kinds() == ["budget_overrun"]
    out, _ = run(Script((Submit(GOOD), Usage(10, 10, 0.5))), budget=Budget(max_cost_usd=0.25))
    assert not out.valid and out.kinds() == ["budget_overrun"] and out.steps == []
    out, _ = run(Script((ToolCall("squad"), Usage(100, 50, 0.01)), Submit(GOOD)))
    assert out.valid and out.usage.tokens == 150 and out.usage.cost_usd == 0.01


def test_following_a_hidden_instruction_is_flagged_even_when_the_decision_is_legal() -> None:
    captain = GOOD["captain"]
    out, _ = run(Script(Submit(GOOD)), trap=Trap(captain))
    assert out.valid and out.kinds() == ["injection_followed"]
    out, _ = run(Script(Submit(GOOD)), trap=Trap(3))  # 3 is on neither side of the decision
    assert out.kinds() == []


def test_agent_errors_are_failures_not_crashes() -> None:
    out, _ = run(Script(RuntimeError("API down")))
    assert not out.valid and out.kinds() == ["agent_error"] and "API down" in out.failures[0].detail


def test_replay_reproduces_a_run_exactly_and_flags_anything_unrecorded() -> None:
    ctx = context()
    rec = RecordingTools(LiveTools(ctx))
    live = run_decision(PlannerAgent(), rec, ctx)
    replayed = run_decision(ReplayAgent("r", live.steps), ReplayTools(rec.calls), ctx)
    assert replayed.decision == live.decision and replayed.kinds() == []
    assert [s.result for s in replayed.steps] == [s.result for s in live.steps]
    missing = run_decision(ReplayAgent("r", live.steps), ReplayTools([]), ctx)
    assert not missing.valid and missing.kinds() == ["replay_miss"]
    short = run_decision(ReplayAgent("r", live.steps[:1]), ReplayTools(rec.calls), ctx)
    assert short.kinds() == ["replay_miss"]


def test_trajectory_is_written_as_json_lines(tmp_path: Path) -> None:
    out, _ = run(Script(ToolCall("nope"), Submit(GOOD)))
    path = tmp_path / "t.jsonl"
    write_trajectory(path, "2025-26-gw2", out)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in rows] == ["step", "step", "failure", "outcome"]
    assert rows[2]["kind"] == "wrong_tool" and rows[3]["valid"] is True


def test_tool_registry_matches_the_server_and_dispatch_rejects_the_unknown() -> None:
    assert set(tools.FUNCTIONS) == set(tools.TOOL_NAMES)
    with pytest.raises(tools.UnknownTool):
        tools.dispatch(context(), "squad2", {})
    with pytest.raises(tools.BadArguments):
        tools.dispatch(context(), "get_player", {"player_id": "x"})
    assert tools.dispatch(context(), "squad", {})["gw"] == 2


def projector() -> Projector:
    return fixture_horizon(form_scores, horizon=2)


def test_planner_agent_through_the_harness_matches_the_planner_manager_exactly() -> None:
    data = varied_season()
    direct = Recorder(PlannerManager("planner", RULES, projector()))
    viaharness = Recorder(
        AgentManager(
            "planner_agent",
            RULES,
            projector(),
            PlannerAgent(),
            initial=PlannerManager("planner", RULES, projector()),
        )
    )
    a = run_season(data, RULES, direct)
    b = run_season(data, RULES, viaharness)
    assert a.total_points == b.total_points and a.violations == b.violations == []
    assert direct.log == viaharness.log


def test_a_failing_agent_still_plays_a_legal_season_and_reports_its_failures(
    tmp_path: Path,
) -> None:
    liar = Script(ToolCall("get_player", {"player_id": 9999}), Submit({**GOOD, "captain": 9999}))
    m = AgentManager(
        "liar", RULES, projector(), liar,
        initial=PlannerManager("planner", RULES, projector()), out_dir=tmp_path,
    )  # fmt: skip
    r = run_season(varied_season(), RULES, m)
    assert r.violations == []  # the fallback keeps every decision legal
    rep = m.report()
    assert rep["decisions"] == 2 and rep["invalid"] == 2
    assert rep["failures"] == {"hallucinated_player": 4}
    assert (tmp_path / "liar-2025-26.jsonl").exists()


def test_safe_decision_keeps_the_squad_and_is_legal() -> None:
    ctx = context()
    d = safe_decision(ctx)
    assert d.transfers == () and set(d.lineup) | set(d.bench) == {
        p.element_id for p in ctx.squad.picks
    }
    assert tools.check_decision(ctx, tools.DecisionIn.model_validate(
        {"lineup": list(d.lineup), "bench": list(d.bench), "captain": d.captain,
         "vice_captain": d.vice_captain}))["ok"]  # fmt: skip
