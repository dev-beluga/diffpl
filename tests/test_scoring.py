import pytest

from diffpl.rules import load_rules
from diffpl.scoring import MatchStats, player_points

R26 = load_rules("2026-27")
R24 = load_rules("2024-25")


def test_no_minutes_scores_zero() -> None:
    assert player_points(R26, "MID", MatchStats(minutes=0)) == 0


def test_booked_on_the_bench_loses_a_point() -> None:
    assert player_points(R26, "FWD", MatchStats(minutes=0, yellow_cards=1)) == -1


def test_short_appearance_gets_no_clean_sheet() -> None:
    assert player_points(R26, "DEF", MatchStats(minutes=30, clean_sheets=1)) == 1


def test_defender_full_game() -> None:
    stats = MatchStats(minutes=90, goals_scored=1, clean_sheets=1, bonus=3)
    assert player_points(R26, "DEF", stats) == 2 + 6 + 4 + 3


def test_goals_conceded_and_saves_round_down() -> None:
    stats = MatchStats(minutes=90, goals_conceded=3, saves=5)
    assert player_points(R26, "GKP", stats) == 2 - 1 + 1


@pytest.mark.parametrize(
    ("pos", "count", "bonus"), [("DEF", 10, 2), ("DEF", 9, 0), ("MID", 11, 0), ("MID", 12, 2)]
)
def test_defensive_contribution_threshold(pos: str, count: int, bonus: int) -> None:
    stats = MatchStats(minutes=90, defensive_contribution=count)
    assert player_points(R26, pos, stats) == 2 + bonus  # type: ignore[arg-type]


def test_no_defensive_contribution_in_2024_25() -> None:
    assert player_points(R24, "DEF", MatchStats(minutes=90, defensive_contribution=20)) == 2
