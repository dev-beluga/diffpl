"""A free LLM agent: a local Ollama model that calls the tools in a loop (ADR-0018).

The model sees the tool schemas plus `submit_decision`, whose arguments are a `DecisionIn`.
Tokens come from Ollama's own counts and cost is zero. The harness still checks every decision,
so a weak model costs points through fallbacks, not through illegal squads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from diffpl.agents.harness import Action, Brief, Submit, ToolCall, Usage
from diffpl.mcp import tools

PROMPT = Path(__file__).resolve().parents[3] / "prompts" / "agent_v1.txt"
HOST = "http://localhost:11434"
SEED = 42
MAX_RESULT_CHARS = 6000  # a tool result is cut here so a long list cannot fill the context
SUBMIT = "submit_decision"


def tool_specs() -> list[dict[str, Any]]:
    schemas = tools.input_schemas()
    specs = [
        {
            "type": "function",
            "function": {"name": n, "description": d, "parameters": schemas[n]},
        }
        for n, d in tools.TOOL_NAMES.items()
    ]
    specs.append(
        {
            "type": "function",
            "function": {
                "name": SUBMIT,
                "description": "Submit your final decision for this gameweek. Call it once.",
                "parameters": tools.DecisionIn.model_json_schema(),
            },
        }
    )
    return specs


class OllamaAgent:
    """Tool-calling loop over Ollama's /api/chat. One conversation per decision."""

    def __init__(self, model: str, client: httpx.Client | None = None, host: str = HOST) -> None:
        self.model = model
        self.name = f"ollama_{model.replace(':', '_')}"
        self.client = client or httpx.Client(base_url=host, timeout=300.0)
        self.system = PROMPT.read_text(encoding="utf-8")
        self.specs = tool_specs()
        self.messages: list[dict[str, Any]] = []

    def start(self, brief: Brief) -> None:
        self.messages = [
            {"role": "system", "content": self.system},
            {
                "role": "user",
                "content": f"Gameweek {brief.gw}, deadline {brief.deadline}. "
                f"You have {brief.budget.max_steps} steps.",
            },
        ]

    def next(self, observation: dict[str, Any] | None) -> tuple[Action, Usage]:
        if observation is not None:
            text = json.dumps(observation, default=str)[:MAX_RESULT_CHARS]
            self.messages.append({"role": "tool", "content": text})
        body = {
            "model": self.model,
            "stream": False,
            "tools": self.specs,
            "options": {"temperature": 0, "seed": SEED},
            "messages": self.messages,
        }
        resp = self.client.post("/api/chat", json=body)
        resp.raise_for_status()
        payload = resp.json()
        usage = Usage(payload.get("prompt_eval_count", 0), payload.get("eval_count", 0), 0.0)
        message = payload["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            raise ValueError("model made no tool call")
        self.messages.append(message)
        fn = calls[0]["function"]
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            args = json.loads(args)
        if fn["name"] == SUBMIT:
            return Submit(args), usage
        return ToolCall(fn["name"], args), usage


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def inline_refs(schema: Any, defs: dict[str, Any] | None = None) -> Any:
    """Replace `$ref` with the referenced definition: hosted APIs reject `$defs`."""
    if isinstance(schema, dict):
        defs = {**(defs or {}), **schema.get("$defs", {})}
        if "$ref" in schema:
            return inline_refs(defs[schema["$ref"].rsplit("/", 1)[-1]], defs)
        return {k: inline_refs(v, defs) for k, v in schema.items() if k != "$defs"}
    if isinstance(schema, list):
        return [inline_refs(v, defs) for v in schema]
    return schema


class OpenAICompatAgent:
    """Tool-calling loop over an OpenAI-style /chat/completions endpoint (Gemini's free tier).

    The API key is read by the caller from the environment and goes only into the auth header.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        client: httpx.Client | None = None,
        base_url: str = GEMINI_URL,
    ) -> None:
        self.model = model
        self.name = f"api_{model}"
        self.client = client or httpx.Client(
            base_url=base_url, timeout=120.0, headers={"Authorization": f"Bearer {api_key}"}
        )
        self.system = PROMPT.read_text(encoding="utf-8")
        self.specs = [
            {"type": "function", "function": inline_refs(s["function"])} for s in tool_specs()
        ]
        self.messages: list[dict[str, Any]] = []
        self._call_id = ""

    def start(self, brief: Brief) -> None:
        user = (
            f"Gameweek {brief.gw}, deadline {brief.deadline}. "
            f"You have {brief.budget.max_steps} steps."
        )
        self.messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": user},
        ]

    def next(self, observation: dict[str, Any] | None) -> tuple[Action, Usage]:
        if observation is not None:
            text = json.dumps(observation, default=str)[:MAX_RESULT_CHARS]
            self.messages.append({"role": "tool", "tool_call_id": self._call_id, "content": text})
        body = {
            "model": self.model,
            "tools": self.specs,
            "tool_choice": "required",
            "temperature": 0,
            "messages": self.messages,
        }
        resp = self.client.post("chat/completions", json=body)
        resp.raise_for_status()
        payload = resp.json()
        u = payload.get("usage") or {}
        usage = Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0), 0.0)
        message = payload["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            raise ValueError("model made no tool call")
        self.messages.append(message)
        call = calls[0]
        self._call_id = call.get("id", "")
        fn = call["function"]
        args = json.loads(fn.get("arguments") or "{}")
        if fn["name"] == SUBMIT:
            return Submit(args), usage
        return ToolCall(fn["name"], args), usage
