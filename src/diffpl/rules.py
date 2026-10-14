"""Versioned FPL rules, one YAML file per season in `config/rules/`."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

RULES_DIR = Path(__file__).resolve().parents[2] / "config" / "rules"
Position = Literal["GKP", "DEF", "MID", "FWD"]
POSITIONS: tuple[Position, ...] = ("GKP", "DEF", "MID", "FWD")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PositionLimits(Strict):
    select: int
    min_play: int
    max_play: int


class Squad(Strict):
    size: int
    starting: int
    budget_tenths: int
    max_per_team: int
    positions: dict[Position, PositionLimits]


class Transfers(Strict):
    free_per_gw: int
    max_banked: int
    hit_cost: int
    sell_on_fee: float


class Chip(Strict):
    name: Literal["wildcard", "freehit", "bboost", "3xc"]
    start_gw: int
    end_gw: int


class Minutes(Strict):
    short_play: int
    long_play: int
    long_play_threshold: int


class DefensiveContribution(Strict):
    points: dict[Position, int]
    threshold: dict[Literal["DEF", "MID", "FWD"], int]


class Scoring(Strict):
    minutes: Minutes
    goals_scored: dict[Position, int]
    assists: int
    clean_sheets: dict[Position, int]
    goals_conceded: dict[Position, int]
    goals_conceded_per: int
    saves: int
    saves_per: int
    penalties_saved: int
    penalties_missed: int
    yellow_cards: int
    red_cards: int
    own_goals: int
    bonus_by_rank: list[int]
    defensive_contribution: DefensiveContribution


class Rules(Strict):
    season: str
    squad: Squad
    transfers: Transfers
    chips: list[Chip]
    scoring: Scoring
    bps_changes: dict[str, int] = {}


def load_rules(season: str, rules_dir: Path = RULES_DIR) -> Rules:
    path = rules_dir / f"{season}.yaml"
    rules = Rules.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if rules.season != season:
        raise ValueError(f"{path} declares season {rules.season!r}")
    return rules
