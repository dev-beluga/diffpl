"""Per-league house rules as an ordered list of validated steps (ADR-0005).

A rule set turns each manager's official gameweek figures into a league score, an
eligibility flag and the gameweek winner(s). Every step records what it changed, so a result
can be explained. Rule sets come from league admins and are untrusted: they are plain data,
validated against a closed schema, and never executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

LEAGUES_DIR = Path(__file__).resolve().parents[3] / "config" / "leagues"
ChipName = Literal["wildcard", "freehit", "bboost", "3xc", "manager"]
Tiebreak = Literal["fewer_hits", "higher_total", "fewer_transfers", "split"]


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdjustHits(Step):
    """How transfer hits count towards the league's gameweek score.

    count_all: deduct every hit (official FPL). ignore_all: deduct none.
    ignore_up_to: the first `limit` points of hits are free. cap: deduct at most `limit`.
    """

    type: Literal["adjust_hits"]
    mode: Literal["count_all", "ignore_all", "ignore_up_to", "cap"]
    limit: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _limit_needed(self) -> AdjustHits:
        if self.mode in ("ignore_up_to", "cap") and self.limit == 0:
            raise ValueError(f"{self.mode} needs a positive limit")
        return self


class Eligibility(Step):
    """Who may win the gameweek. Ineligible managers still score; they cannot win."""

    type: Literal["eligibility"]
    max_hit: int | None = Field(default=None, ge=0)
    excluded_chips: tuple[ChipName, ...] = ()


class Winner(Step):
    """Highest league score among eligible managers wins. Ties go through `tiebreak` in
    order; `split` (or running out of tiebreaks) shares the gameweek."""

    type: Literal["winner"]
    tiebreak: tuple[Tiebreak, ...] = ("split",)


AnyStep = Annotated[AdjustHits | Eligibility | Winner, Field(discriminator="type")]


class RuleVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    effective_from_gw: int = Field(ge=1, le=38)
    steps: tuple[AnyStep, ...]
    overall: Literal["official", "league_score"] = "official"

    @model_validator(mode="after")
    def _shape(self) -> RuleVersion:
        kinds = [s.type for s in self.steps]
        if kinds.count("winner") != 1 or kinds[-1] != "winner":
            raise ValueError("a rule set needs exactly one winner step, last")
        if kinds.count("adjust_hits") > 1:
            raise ValueError("at most one adjust_hits step")
        return self


class LeagueRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    league_id: int
    name: str = Field(max_length=100)
    versions: tuple[RuleVersion, ...]

    @model_validator(mode="after")
    def _ordered(self) -> LeagueRules:
        starts = [v.effective_from_gw for v in self.versions]
        if not starts or starts[0] != 1 or starts != sorted(set(starts)):
            raise ValueError("versions must start at GW1 and have increasing effective_from_gw")
        return self

    def for_gw(self, gw: int) -> RuleVersion:
        return [v for v in self.versions if v.effective_from_gw <= gw][-1]


OFFICIAL = RuleVersion(
    effective_from_gw=1,
    steps=(AdjustHits(type="adjust_hits", mode="count_all"), Winner(type="winner")),
)


def default_rules(league_id: int, name: str = "") -> LeagueRules:
    return LeagueRules(league_id=league_id, name=name, versions=(OFFICIAL,))


def load_league_rules(league_id: int, leagues_dir: Path = LEAGUES_DIR) -> LeagueRules:
    path = leagues_dir / f"{league_id}.yaml"
    if not path.exists():
        return default_rules(league_id)
    rules = LeagueRules.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if rules.league_id != league_id:
        raise ValueError(f"{path} declares league {rules.league_id}")
    return rules


@dataclass(frozen=True)
class EntryGw:
    """Official FPL figures for one manager in one gameweek."""

    entry_id: int
    gw: int
    points: int  # before hits
    hit_cost: int
    transfers: int = 0
    chip: ChipName | None = None
    total_points: int = 0  # official season total after this GW


@dataclass
class LeagueGw:
    entry_id: int
    gw: int
    score: int
    eligible: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class GwOutcome:
    gw: int
    scores: list[LeagueGw]
    winners: list[int]
    explanation: str


def _adjust(step: AdjustHits, row: EntryGw, out: LeagueGw) -> None:
    hit = row.hit_cost
    deducted = {
        "count_all": hit,
        "ignore_all": 0,
        "ignore_up_to": max(0, hit - step.limit),
        "cap": min(hit, step.limit),
    }[step.mode]
    out.score = row.points - deducted
    if deducted != hit:
        out.notes.append(f"hit -{hit} counted as -{deducted} ({step.mode} {step.limit})")


def _eligibility(step: Eligibility, row: EntryGw, out: LeagueGw) -> None:
    if step.max_hit is not None and row.hit_cost > step.max_hit:
        out.eligible = False
        out.notes.append(f"ineligible: hit -{row.hit_cost} over -{step.max_hit}")
    if row.chip is not None and row.chip in step.excluded_chips:
        out.eligible = False
        out.notes.append(f"ineligible: played {row.chip}")


def _tiebreak_key(rule: Tiebreak, row: EntryGw) -> int:
    return {
        "fewer_hits": -row.hit_cost,
        "higher_total": row.total_points,
        "fewer_transfers": -row.transfers,
        "split": 0,
    }[rule]


def _winners(
    step: Winner, rows: dict[int, EntryGw], scores: list[LeagueGw]
) -> tuple[list[int], str]:
    pool = [s for s in scores if s.eligible]
    if not pool:
        return [], "no eligible managers"
    best = max(s.score for s in pool)
    tied = [s.entry_id for s in pool if s.score == best]
    reason = f"top league score {best}"
    for rule in step.tiebreak:
        if len(tied) == 1 or rule == "split":
            break
        top = max(_tiebreak_key(rule, rows[e]) for e in tied)
        tied = [e for e in tied if _tiebreak_key(rule, rows[e]) == top]
        reason += f", tie broken by {rule}"
    if len(tied) > 1:
        reason += ", shared"
    return sorted(tied), reason


def score_gameweek(rules: LeagueRules, rows: list[EntryGw]) -> GwOutcome:
    """Apply the league's rule version for this GW to every manager's official figures."""
    gws = {r.gw for r in rows}
    if len(gws) != 1:
        raise ValueError("score_gameweek takes rows from a single gameweek")
    gw = gws.pop()
    version = rules.for_gw(gw)
    by_entry = {r.entry_id: r for r in rows}
    scores = [LeagueGw(r.entry_id, gw, r.points - r.hit_cost) for r in rows]
    winners: list[int] = []
    explanation = ""
    for step in version.steps:
        if isinstance(step, AdjustHits):
            for s in scores:
                _adjust(step, by_entry[s.entry_id], s)
        elif isinstance(step, Eligibility):
            for s in scores:
                _eligibility(step, by_entry[s.entry_id], s)
        else:
            winners, explanation = _winners(step, by_entry, scores)
    return GwOutcome(gw, scores, winners, explanation)


def overall_table(
    rules: LeagueRules, outcomes: list[GwOutcome], rows: list[EntryGw]
) -> dict[int, int]:
    """Season standings. Each GW uses its rule version's `overall` setting: official FPL
    points after hits, or the league score."""
    official = {(r.entry_id, r.gw): r.points - r.hit_cost for r in rows}
    totals: dict[int, int] = {}
    for o in outcomes:
        use_league = rules.for_gw(o.gw).overall == "league_score"
        for s in o.scores:
            pts = s.score if use_league else official[(s.entry_id, s.gw)]
            totals[s.entry_id] = totals.get(s.entry_id, 0) + pts
    return totals
