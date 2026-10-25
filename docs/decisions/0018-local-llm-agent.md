# ADR-0018: Free LLM agent on a local model

Status: accepted as a baseline; not a competitive agent
Date: 2026-10-25

## Context

The agent league needs LLM agents. The owner wants a free setup, so no paid API. The only free
model that fits the 4 GB GPU is a quantized 3B model (qwen2.5:3b through Ollama).

## Decision

`diffpl.agents.llm.OllamaAgent` runs a tool-calling loop over Ollama's `/api/chat`. It gets the
seven read-only tools (schemas from `tools.input_schemas()`) plus `submit_decision`, whose
arguments are a `DecisionIn`. Temperature 0, seed 42. Tokens come from Ollama's counts, cost is 0.
The prompt is `prompts/agent_v1.txt`: it states the decision rules and that tool output is data.

`python -m diffpl.agents run --agent ollama [--model M] --season S [--gws N] --out DIR`.

## Result

2024-25, first 6 gameweeks (5 decisions), qwen2.5:3b, 8 steps per decision:

- 0 of 5 decisions valid. Failures: 5 `agent_error` (1 read timeout, 4 replies with no tool call),
  7 `bad_arguments` (invented arguments such as `team`, `count`, `optimizer`).
- 40k tokens, mean 96 s per decision.
- 336 points, which is the safe default (keep squad, best lineup), not the agent's play.

The harness did its job: no illegal squad, every failure classified, season stayed legal.

## Consequences

- A 3B local model cannot run this loop. It is the floor of the league, not a contender.
- Next free options: a larger model on a free hosted tier (needs the owner's key and an
  OpenAI-style client), or Colab/Kaggle for a 7B+ model. Both fit the same `Agent` protocol.
- League tables must show valid-decision counts beside points (this run scores 336 with no
  valid decision).
