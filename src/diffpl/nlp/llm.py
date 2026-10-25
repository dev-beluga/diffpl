"""LLM extraction of team news through a local Ollama model (ADR-0014).

The model reads one string and fills a JSON schema; code does the rest. Dates, durations and
the chance-of-playing semantics are computed here, not by the model: small models are poor at
arithmetic and the rules baseline already fixes what each field means. The text is passed as
user content inside <news> tags, never in the system prompt, and the output is validated
against the schema; a quote the text does not contain is replaced by the whole text.
Temperature 0 and a fixed seed make a run repeatable on the same model and hardware.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from diffpl.nlp.news import (
    BODY_PARTS,
    MONTHS,
    NUMBER_WORDS,
    TYPE_ALIASES,
    News,
    Status,
    next_occurrence,
    parse_news,
    strip_instructions,
)
from diffpl.nlp.score import ROOT

PROMPT = ROOT / "prompts/team_news_v1.txt"
HOST = "http://localhost:11434"
SEED = 42
STOPPED_BY_STATUS: dict[str, int | None] = {"injured": 0, "suspended": 0, "unavailable": 0}


class Extraction(BaseModel):
    status: Literal["available", "doubtful", "injured", "suspended", "unavailable", "unknown"]
    chance: int | None = Field(default=None, ge=0, le=100)
    injury_type: str | None = None
    stated_date: str | None = None
    duration_days: int | None = Field(default=None, ge=0, le=400)
    return_unknown: bool = False
    quote: str = ""


@dataclass
class Stats:
    calls: int = 0
    failures: int = 0
    seconds: list[float] = field(default_factory=list)
    prompt_tokens: int = 0
    output_tokens: int = 0


def _stated_date(text: str, as_of: datetime) -> date | None:
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})", text)
    if m and m.group(2).lower() in MONTHS:
        return next_occurrence(int(m.group(1)), MONTHS[m.group(2).lower()], as_of.date())
    m = re.search(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2})\b", text)
    if m and m.group(1).lower() in MONTHS:
        return next_occurrence(int(m.group(2)), MONTHS[m.group(1).lower()], as_of.date())
    return None


def _injury_type(value: str | None) -> str | None:
    for m in re.finditer(r"[A-Za-z]+", (value or "").lower()):
        word = m.group()
        if word in BODY_PARTS or word == "back":
            return TYPE_ALIASES.get(word, word)
        if word == "ill":
            return "illness"
    return None


LENGTH = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")\s+(day|week|month)s?\b", re.I)
UNIT_DAYS = {"day": 1, "week": 7, "month": 30}


def _stated_date_supported(stated: str | None, text: str) -> bool:
    return bool(stated) and stated.strip().lower() in text.lower()  # type: ignore[union-attr]


def _duration_supported(days: int | None, text: str) -> bool:
    """The model may only turn a length the text gives into days, not invent one."""
    if not days:
        return False
    for m in LENGTH.finditer(text):
        n = int(m.group(1)) if m.group(1).isdigit() else NUMBER_WORDS[m.group(1).lower()]
        if days == n * UNIT_DAYS[m.group(2).lower()]:
            return True
    return False


def to_news(e: Extraction, text: str, as_of: datetime, strict_quote: bool = False) -> News:
    """Apply the field contract (same as the rules baseline) to the model's extraction."""
    status: Status = e.status
    chance = STOPPED_BY_STATUS.get(status, e.chance if status == "doubtful" else None)
    typed = status in ("injured", "doubtful")
    return_date = None
    if status in ("injured", "suspended"):
        if _stated_date_supported(e.stated_date, text) and e.stated_date:
            return_date = _stated_date(e.stated_date, as_of)
        if return_date is None and _duration_supported(e.duration_days, text) and e.duration_days:
            return_date = as_of.date() + timedelta(days=e.duration_days)
    supported = bool(e.quote) and e.quote.lower() in text.lower()
    if strict_quote and status != "unknown" and not supported:
        return News("unknown", None, None, None, False, text, as_of)  # claim without evidence
    quote = e.quote if supported else text
    return News(
        status,
        chance,
        _injury_type(e.injury_type) if typed else None,
        return_date,
        status == "injured" and e.return_unknown,
        quote,
        as_of,
    )


class OllamaParser:
    """Callable with the same signature as `parse_news`, so the eval can score either."""

    def __init__(
        self,
        model: str,
        client: httpx.Client | None = None,
        host: str = HOST,
        strict_quote: bool = False,
    ) -> None:
        self.model = model
        self.strict_quote = strict_quote
        self.client = client or httpx.Client(base_url=host, timeout=120.0)
        self.system = PROMPT.read_text(encoding="utf-8")
        self.schema = Extraction.model_json_schema()
        self.stats = Stats()

    def __call__(self, text: str, as_of: datetime) -> News:
        raw = (text or "").strip()
        if not raw:
            return News("available", None, None, None, False, "", as_of)
        clean, flagged = strip_instructions(raw)
        flags = ("injection",) if flagged else ()
        if not clean:  # nothing but instructions: no call, no claim about the player
            return News("unknown", None, None, None, False, raw, as_of, flags)
        self.stats.calls += 1
        body = {
            "model": self.model,
            "stream": False,
            "format": self.schema,
            "options": {"temperature": 0, "seed": SEED},
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": f"<news>{clean}</news>"},
            ],
        }
        started = time.perf_counter()
        try:
            resp = self.client.post("/api/chat", json=body)
            resp.raise_for_status()
            payload = resp.json()
            extraction = Extraction.model_validate(json.loads(payload["message"]["content"]))
        except (httpx.HTTPError, KeyError, ValueError, ValidationError):
            self.stats.failures += 1
            return News("unknown", None, None, None, False, clean, as_of, flags)
        self.stats.seconds.append(time.perf_counter() - started)
        self.stats.prompt_tokens += int(payload.get("prompt_eval_count") or 0)
        self.stats.output_tokens += int(payload.get("eval_count") or 0)
        return replace(to_news(extraction, clean, as_of, self.strict_quote), flags=flags)


class HybridParser:
    """Rules first; the model only reads what the rules could not (status `unknown`).

    FPL's own news is templated and the rules read it exactly, so the model never sees it.
    The model's claims need a verbatim quote, and instruction-like sentences are removed
    before either side reads the text (ADR-0015)."""

    def __init__(self, llm: OllamaParser) -> None:
        self.llm = llm
        self.rule_reads = 0
        self.model_reads = 0

    def __call__(self, text: str, as_of: datetime) -> News:
        news = parse_news(text, as_of)
        if news.status != "unknown":
            self.rule_reads += 1
            return news
        self.model_reads += 1
        return self.llm(text, as_of)
