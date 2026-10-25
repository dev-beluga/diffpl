# ADR-0017: Agent harness

Status: accepted
Date: 2026-10-25

## Context

CLAUDE.md asks for budgets per decision (steps, tokens, cost), full trajectory logs, recorded
tool outputs for deterministic replay, and a failure taxonomy. Agents must be comparable in the
same replay env as every other manager, and a model that misbehaves must not break a season.

## Decision

`diffpl.agents`:

- **Agent protocol.** `start(brief)` and `next(observation) -> (action, usage)`, where an action
  is a `ToolCall` or a `Submit` (a decision). A scripted agent, a replay agent and an LLM agent
  all fit it; the LLM client will live inside the agent and report its tokens and cost.
- **`run_decision(agent, backend, ctx, budget, trap)`** runs one decision. Budgets: 8 steps,
  40k tokens, $0.25 by default. A decision counts only if it parses, names players that exist in
  the market, and passes the rules' dry run (`check_decision`); otherwise the caller falls back.
- **Failure taxonomy**, as a list on the outcome (several can occur in one decision):
  `wrong_tool`, `bad_arguments`, `hallucinated_player`, `rule_violation`, `budget_overrun`,
  `injection_followed`, plus `agent_error` (the agent raised), `replay_miss` and the step limit
  (counted as `budget_overrun`). Wrong tool, bad arguments and a made-up id in a lookup are
  recoverable: the agent sees an error and may continue. `injection_followed` is checked against
  a `Trap`, a player id that an instruction hidden in the data tells the agent to pick; a legal
  decision can still be flagged.
- **Tools.** `LiveTools` calls `tools.dispatch`, which validates arguments against each tool's
  signature and runs the same functions the MCP server wraps (ADR-0016).
- **Record and replay.** `RecordingTools` keeps every call and result; `ReplayTools` answers the
  n-th identical call with the n-th recorded result; `ReplayAgent` returns the recorded actions
  and usage. Together they reproduce a run exactly even when the model is not deterministic.
- **Trajectories** are appended as JSON lines: one record per step, per failure and per outcome.
- **`AgentManager`** adapts any agent to the replay `Manager` interface. The agent sees only the
  deadline's tools, so replay's no-leakage rule holds. Any failure falls back to a safe default
  (keep the squad, best lineup by projection), so a season always stays legal; the failures are
  counted in `report()` with tokens, cost and mean latency. The GW1 squad comes from a baseline
  manager: agents decide from GW2.
- **`PlannerAgent`** is a scripted agent that calls `plan_transfers` and submits its first plan.
  It is the plumbing proof (it must score exactly like `PlannerManager`) and the bar an LLM agent
  has to beat.

`python -m diffpl.agents run --agent planner --season 2024-25 --out DIR` plays a real season.

## Verification

13 tests: every failure kind, budgets on steps, tokens and cost, replay equality and misses,
trajectory format, the tool registry, a season through the harness matching `PlannerManager`
decision for decision, and a deliberately failing agent that still plays a legal season.

On real data, `planner_agent` through the harness scored 2186 points on 2024-25 with no
violations or failures over 37 decisions (mean 4.2 s per decision, no tokens): exactly the EV
planner's score from the same champion (ADR-0010, ADR-0011).

## Consequences

- An agent that fails every time scores as the safe default, not as zero: league tables must show
  the failure counts beside the points.
- Cost and token accounting trusts the agent's reported usage; the LLM agent must read it from
  the API response.
- Langfuse and OpenTelemetry tracing wrap `run_decision` later; the trajectory already holds
  what they need.
