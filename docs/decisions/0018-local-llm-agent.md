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

## Hosted free tier: Groq gpt-oss-120b (same 6 GWs, 5 decisions)

`OpenAICompatAgent` (OpenAI-style endpoint, retry on 429, key from env only) with
`openai/gpt-oss-120b` on Groq's free tier (8k tokens per minute, 200k per day):

- Run 1, full history: 2 of 5 valid, 353 points. The 3 others died on HTTP 413 (request over the
  per-minute token cap) and one 400.
- Run 2, only the last 2 tool results kept in the history: 0 of 5 valid, 336 points. The agent
  forgot what it had read, called `squad` again and again, and hit the 8-step limit (4 budget
  overruns). One 400 `tool_use_failed`: the model wrote a malformed tool name.
- About 100k tokens and 120 s per 5 decisions in both runs. Two runs used about the daily cap.

Reading: a free tier fits a short loop, not an 8-step exploration. The agent spends its steps
re-reading data. Next design: give the first message the squad and the planner's best plan, so
a decision takes 1 to 3 steps.
