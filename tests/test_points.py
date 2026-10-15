"""2025-26 scoring values reproduce FPL's own total_points on real gameweek rows."""

import csv
from pathlib import Path
from typing import cast

import pytest

from diffpl.rules import Position, load_rules, points_for

SAMPLE = Path(__file__).parent / "fixtures/vaastav_2025-26_points_sample.csv"
ROWS = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
RULES = load_rules("2025-26")


@pytest.mark.parametrize("row", ROWS, ids=[f"{r['name']}-gw{r['GW']}" for r in ROWS])
def test_points_match_fpl_total(row: dict[str, str]) -> None:
    position = cast(Position, "GKP" if row["position"] == "GK" else row["position"])
    stats = {k: int(v) for k, v in row.items() if k not in ("name", "position", "GW")}
    assert points_for(RULES, position, stats) == stats["total_points"]


def test_sample_covers_each_rule() -> None:
    def any_row(key: str) -> bool:
        return any(int(r[key]) > 0 for r in ROWS)

    assert all(
        any_row(k)
        for k in ("defensive_contribution", "saves", "clean_sheets", "goals_conceded", "own_goals")
    )
    assert any_row("penalties_missed") or any_row("penalties_saved")
    assert {r["position"] for r in ROWS} >= {"GK", "DEF", "MID", "FWD"}


def test_seasons_share_point_values() -> None:
    assert load_rules("2025-26").scoring == load_rules("2026-27").scoring
