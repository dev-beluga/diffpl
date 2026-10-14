"""The 2026-27 rules file must match the scoring config the FPL API published."""

import json
from pathlib import Path
from typing import Any

import pytest

from diffpl.rules import POSITIONS, load_rules

API = json.loads(
    (Path(__file__).parent / "fixtures/fpl_api/game-config-2026-27.json").read_text("utf-8")
)
RULES = load_rules("2026-27")
SCORING: dict[str, Any] = API["game_config"]["scoring"]
API_RULES: dict[str, Any] = API["game_config"]["rules"]


@pytest.mark.parametrize("key", ["goals_scored", "clean_sheets", "goals_conceded"])
def test_positional_points_match_api(key: str) -> None:
    assert getattr(RULES.scoring, key) == SCORING[key]


@pytest.mark.parametrize(
    "key",
    [
        "assists",
        "saves",
        "penalties_saved",
        "penalties_missed",
        "yellow_cards",
        "red_cards",
        "own_goals",
    ],
)
def test_flat_points_match_api(key: str) -> None:
    assert getattr(RULES.scoring, key) == SCORING[key]


def test_minutes_and_defcon_match_api() -> None:
    assert RULES.scoring.minutes.short_play == SCORING["short_play"]
    assert RULES.scoring.minutes.long_play == SCORING["long_play"]
    assert RULES.scoring.defensive_contribution.points == SCORING["defensive_contribution"]


def test_assistant_manager_scoring_is_off() -> None:
    mng = {k: v for k, v in SCORING.items() if k.startswith("mng_")}
    assert mng
    for value in mng.values():
        assert value == 0 or all(v == 0 for v in value.values())


def test_squad_matches_api() -> None:
    squad = RULES.squad
    assert squad.size == API_RULES["squad_squadsize"]
    assert squad.starting == API_RULES["squad_squadplay"]
    assert squad.budget_tenths == API_RULES["squad_total_spend"]
    assert squad.max_per_team == API_RULES["squad_team_limit"]
    for et in API["element_types"]:
        limits = squad.positions[et["singular_name_short"]]
        assert (limits.select, limits.min_play, limits.max_play) == (
            et["squad_select"],
            et["squad_min_play"],
            et["squad_max_play"],
        )
    assert sum(p.select for p in squad.positions.values()) == squad.size


def test_transfers_match_api() -> None:
    assert RULES.transfers.max_banked == API_RULES["max_extra_free_transfers"] + 1
    assert RULES.transfers.sell_on_fee == API_RULES["transfers_sell_on_fee"]


def test_chips_match_api() -> None:
    api_chips = sorted((c["name"], c["start_event"], c["stop_event"]) for c in API["chips"])
    ours = sorted((c.name, c.start_gw, c.end_gw) for c in RULES.chips)
    assert ours == api_chips


def test_every_position_scored() -> None:
    for table in (RULES.scoring.goals_scored, RULES.scoring.clean_sheets):
        assert set(table) == set(POSITIONS)


def test_season_mismatch_rejected(tmp_path: Path) -> None:
    text = (Path(__file__).parents[1] / "config/rules/2026-27.yaml").read_text("utf-8")
    (tmp_path / "2025-26.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="declares season"):
        load_rules("2025-26", tmp_path)
