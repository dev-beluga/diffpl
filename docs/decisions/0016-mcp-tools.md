# ADR-0016: Read-only MCP tools for agents

Status: accepted
Date: 2026-10-25

## Context

Phase 5 puts LLM agents in the replay env. CLAUDE.md requires sandboxed MCP tools, tool
outputs that can be recorded for deterministic replay, agents that never write to FPL accounts,
and news and user text treated as data. The harness (budgets, trajectories, failure taxonomy)
comes next; the tools come first because the harness wraps them.

## Decision

- `diffpl.mcp.tools`: seven plain functions over a `ToolContext` (the deadline's `Observation`,
  the squad, the rules and a projection). Because the context holds only what a manager may see,
  the replay env's no-leakage rule carries over to agents.

  | Tool | Returns |
  |------|---------|
  | `squad` | squad, selling prices, bank, free transfers |
  | `search_players` | players by expected points, with filters (30 rows at most) |
  | `get_player` | one player, last five matches, next fixtures |
  | `get_fixtures` | upcoming fixtures, one team or all |
  | `plan_transfers` | the MILP's top plans (ADR-0010), at most five |
  | `check_decision` | dry run of a full decision against the rules; nothing is submitted |
  | `analyze_news` | status, chance, injury, return date from a news string (ADR-0013/0015) |

- `diffpl.mcp.server.build_server(ctx)` registers them on an `MCPServer` (MCP SDK 2.x), every
  tool annotated read-only. There is no tool that submits, writes, or touches an FPL account; a
  test asserts this by name. The agent's decision is the agent loop's return value, validated by
  the harness, not a tool call.
- Inputs are validated by types (pydantic models for decisions, a position enum), outputs are
  capped, and external strings (player names, news) are returned as data. `analyze_news` runs the
  injection guard before reading.
- `python -m diffpl.mcp serve --team <id>` serves the next deadline of a real team over stdio.
  Logs go to stderr because stdout carries the protocol.

## Verification

13 tests cover each tool on a synthetic deadline, that tools leave the context unchanged, and the
protocol itself through an in-memory MCP client (tool list, read-only annotations, structured
results). The live server answered `squad`, `search_players`, `plan_transfers` (12 s for two
plans) and `analyze_news` over real stdio for team 3457155.

## Consequences

- Plans need a projection for every player, so the first `plan_transfers` call of a deadline
  costs seconds; the context caches it.
- Recording and replaying tool calls, step, token and cost budgets, trajectory logs and the
  failure taxonomy are the next step (the harness). Tool outputs are already plain JSON for
  that.
- The live entry point duplicates a few lines of the web API's champion loading; they merge
  when the API branch lands on main.
