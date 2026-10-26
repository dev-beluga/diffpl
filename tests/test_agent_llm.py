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


def test_inline_refs_removes_defs_for_hosted_apis() -> None:
    from diffpl.agents.llm import inline_refs

    spec = next(s for s in tool_specs() if s["function"]["name"] == SUBMIT)["function"]
    flat = inline_refs(spec)
    assert "$ref" not in json.dumps(flat) and "$defs" not in json.dumps(flat)


def test_openai_compat_agent_round_trip_sends_tool_call_ids() -> None:
    from diffpl.agents.llm import OpenAICompatAgent

    def msg(name: str, args: dict[str, Any]) -> dict[str, Any]:
        call = {
            "id": "c1",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }
        return {
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }

    seen: list[dict[str, Any]] = []
    queue = iter([msg("squad", {}), msg(SUBMIT, good_decision().model_dump())])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=next(queue))

    client = httpx.Client(base_url="http://x/", transport=httpx.MockTransport(handler))
    ctx = context()
    out = run_decision(OpenAICompatAgent("m", "k", client), LiveTools(ctx), ctx)
    assert out.valid and out.usage.tokens == 120
    assert seen[1]["messages"][-1]["tool_call_id"] == "c1"


def test_rate_limit_is_retried_then_succeeds(monkeypatch: Any) -> None:
    from diffpl.agents import llm

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    call = {"id": "c", "type": "function", "function": {"name": "squad", "arguments": "{}"}}
    ok = {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}}]}
    replies = iter(
        [httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200, json=ok)]
    )
    client = httpx.Client(
        base_url="http://x/", transport=httpx.MockTransport(lambda r: next(replies))
    )
    agent = llm.OpenAICompatAgent("m", "k", client)
    agent.start(
        __import__("diffpl.agents.harness", fromlist=["Brief"]).Brief(
            2, "d", {}, __import__("diffpl.agents.harness", fromlist=["Budget"]).Budget()
        )
    )
    action, _ = agent.next(None)
    assert action.name == "squad" and sleeps == [3.0]  # type: ignore[union-attr]
