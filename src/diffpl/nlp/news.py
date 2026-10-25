"""Rules baseline for team news (ADR-0013).

Turns one news string, such as FPL's player `news` field or a press-conference quote, into a
status, a chance of playing, an injury type and a return date, keeping the matched text as the
source quote. Pure function of (text, as_of): no clock, no network. News is data, never
instructions: nothing here follows or executes what the text says.

Statuses: available, doubtful, injured, suspended, unavailable (left the club or not in the
squad), unknown (text present but no rule matched). `chance` follows FPL's
chance_of_playing_next_round: 0 for injured, suspended and unavailable, the stated percent for
doubtful, None for available and unknown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

Status = Literal["available", "doubtful", "injured", "suspended", "unavailable", "unknown"]

MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
NUMBER_WORDS = {
    w: i
    for i, w in enumerate(
        [
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
        ],
        1,
    )
}
BODY_PARTS = [
    "hamstring",
    "knee",
    "ankle",
    "calf",
    "groin",
    "thigh",
    "foot",
    "achilles",
    "hip",
    "shoulder",
    "shin",
    "head",
    "arm",
    "leg",
    "muscular",
    "muscle",
    "illness",
    "knock",
    "unspecified",
]
TYPE_ALIASES = {"muscle": "muscular", "ill": "illness"}

UNAVAILABLE = re.compile(
    r"\b(has|have)\s+(joined|departed|returned to)\b|\bnot included in (?:the )?squad\b"
    r"|\bleft the club\b",
    re.I,
)
SUSPENDED = re.compile(r"\bsuspen(?:ded|sion)\b|\bbanned\b", re.I)
PERCENT = re.compile(r"(\d{1,3})\s*%\s*chance|\b(\d{2})-\2\b", re.I)
DOUBTFUL = re.compile(r"\bdoubt(?:ful)?\b", re.I)
OUT = re.compile(
    r"\bruled out\b|\bout for\b|\bwill miss\b|\bsidelined\b|\bunknown return date\b"
    r"|\breturn date unknown\b|\bexpected back\b",
    re.I,
)
AVAILABLE = re.compile(
    r"\bfully fit\b|\bavailable for selection\b|\bno new injury concerns\b|\btrained fully\b"
    r"|\bfit and ready\b|\bback in full training\b",
    re.I,
)
INJURY = re.compile(r"\binjur\w*|\bknock\b|\billness\b|\bproblem\b", re.I)
BACK_PROBLEM = re.compile(r"\bback (?:injury|problem)\b", re.I)
DATE_TEXT = re.compile(
    r"\b(?:expected back|until|back on|return(?:s|ing)? on)\s+(\d{1,2})\s+([A-Za-z]{3})[a-z]*\b",
    re.I,
)
DURATION = re.compile(
    r"\b(?:out for|miss(?:ing)?|ruled out for|sidelined for)\s+(?:around |about |another )?"
    r"(\d+|" + "|".join(NUMBER_WORDS) + r")\s+(day|week)s?\b",
    re.I,
)
UNKNOWN_RETURN = re.compile(
    r"\bunknown return date\b|\breturn date unknown\b|\bno return date\b", re.I
)


@dataclass(frozen=True)
class News:
    status: Status
    chance: int | None
    injury_type: str | None
    return_date: date | None
    return_unknown: bool
    quote: str  # the text the status was read from
    as_of: datetime  # when the text was published or fetched


def next_occurrence(day: int, month: int, as_of: date) -> date | None:
    for year in (as_of.year, as_of.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= as_of:
            return d
    return None


def _injury_type(text: str) -> str | None:
    if BACK_PROBLEM.search(text):
        return "back"
    for m in re.finditer(r"[A-Za-z]+", text.lower()):
        word = m.group()
        if word in BODY_PARTS:
            return TYPE_ALIASES.get(word, word)
        if word == "ill":
            return "illness"
    return None


def _return_date(text: str, as_of: datetime) -> date | None:
    m = DATE_TEXT.search(text)
    if m and m.group(2).lower() in MONTHS:
        return next_occurrence(int(m.group(1)), MONTHS[m.group(2).lower()], as_of.date())
    m = DURATION.search(text)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUMBER_WORDS[m.group(1).lower()]
        return as_of.date() + timedelta(days=n * (7 if m.group(2).lower() == "week" else 1))
    return None


def parse_news(text: str | None, as_of: datetime) -> News:
    """Read one news string. Empty text means no news, so the player is available."""
    clean = (text or "").strip()
    if not clean:
        return News("available", None, None, None, False, "", as_of)

    def result(status: Status, chance: int | None, typed: bool, dated: bool) -> News:
        return News(
            status,
            chance,
            _injury_type(clean) if typed else None,
            _return_date(clean, as_of) if dated else None,
            status == "injured" and bool(UNKNOWN_RETURN.search(clean)),
            clean,
            as_of,
        )

    if UNAVAILABLE.search(clean):
        return result("unavailable", 0, False, False)
    if SUSPENDED.search(clean):
        return result("suspended", 0, False, True)
    percent = PERCENT.search(clean)
    if percent:
        chance = int(percent.group(1) or percent.group(2))
        return result("doubtful" if chance < 100 else "available", chance, True, False)
    if OUT.search(clean):
        return result("injured", 0, True, True)
    if DOUBTFUL.search(clean):
        return result("doubtful", None, True, False)
    if AVAILABLE.search(clean):
        return result("available", None, False, False)
    if INJURY.search(clean):
        return result("injured", 0, True, True)
    return News("unknown", None, None, None, False, clean, as_of)
