"""OllamaAgent: tool-calling loop against a fake Ollama server, and the tool schemas."""

import json
from typing import Any

import httpx
from test_mcp_tools import context, good_decision

from diffpl.agents.harness import LiveTools, run_decision
from diffpl.agents.llm import SUBMIT, OllamaAgent, tool_specs
from diffpl.mcp import tools


def fake(replies: list[dict[str, Any]], seen: list[dict[str, Any]]) -> httpx.Client:
    queue = iter(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=next(queue))

    return httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))


def reply(name: str, args: dict[str, Any] | None = None, **extra: int) -> dict[str, Any]:
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args or {}}}],
    }
    return {"message": msg, "prompt_eval_count": 100, "eval_count": 20, **extra}


def test_schemas_cover_every_tool_and_hide_the_context() -> None:
    schemas = tools.input_schemas()
    assert set(schemas) == set(tools.TOOL_NAMES)
    assert "ctx" not in schemas["search_players"]["properties"]
    assert schemas["get_player"]["required"] == ["player_id"]
    assert [s["function"]["name"] for s in tool_specs()][-1] == SUBMIT


def test_agent_looks_then_submits_and_the_harness_accepts_it() -> None:
    seen: list[dict[str, Any]] = []
    good = good_decision().model_dump()
    client = fake([reply("squad"), reply(SUBMIT, good)], seen)
    ctx = context()
    out = run_decision(OllamaAgent("m", client), LiveTools(ctx), ctx)
    assert out.valid and out.failures == [] and out.usage.tokens == 240
    assert out.usage.cost_usd == 0.0
    roles = [m["role"] for m in seen[1]["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]  # tool result fed back


def test_a_text_only_reply_is_an_agent_error_not_a_crash() -> None:
    bad = {"message": {"role": "assistant", "content": "I think Salah."}}
    ctx = context()
    out = run_decision(OllamaAgent("m", fake([bad], [])), LiveTools(ctx), ctx)
    assert not out.valid and out.kinds() == ["agent_error"]
