from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from diffpl.leagues.rules import (
    EntryGw,
    LeagueRules,
    default_rules,
    load_league_rules,
    overall_table,
    score_gameweek,
)


def rules(*versions: Mapping[str, object]) -> LeagueRules:
    return LeagueRules.model_validate({"league_id": 1, "name": "t", "versions": list(versions)})


def version(
    *steps: Mapping[str, object], from_gw: int = 1, overall: str = "official"
) -> Mapping[str, object]:
    return {"effective_from_gw": from_gw, "steps": list(steps), "overall": overall}


WIN: Mapping[str, object] = {"type": "winner", "tiebreak": ["fewer_hits", "split"]}
# A: 70 before a -8 hit. B: 65 clean. C: 72 before a -12 hit.
ROWS = [
    EntryGw(1, 5, points=70, hit_cost=8, transfers=3, total_points=300),
    EntryGw(2, 5, points=65, hit_cost=0, transfers=1, total_points=310),
    EntryGw(3, 5, points=72, hit_cost=12, transfers=4, total_points=290),
]


def test_default_is_official_fpl() -> None:
    out = score_gameweek(default_rules(1), ROWS)
    assert [s.score for s in out.scores] == [62, 65, 60]
    assert out.winners == [2]


def test_hits_up_to_eight_are_free_for_the_weekly_prize() -> None:
    r = rules(version({"type": "adjust_hits", "mode": "ignore_up_to", "limit": 8}, WIN))
    out = score_gameweek(r, ROWS)
    assert [s.score for s in out.scores] == [70, 65, 68]  # C still loses the 4 past -8
    assert out.winners == [1]
    assert "counted as -0" in out.scores[0].notes[0]


def test_eligibility_blocks_big_hits_from_winning() -> None:
    r = rules(
        version(
            {"type": "adjust_hits", "mode": "ignore_all"},
            {"type": "eligibility", "max_hit": 8},
            WIN,
        )
    )
    out = score_gameweek(r, ROWS)
    assert out.scores[2].score == 72 and not out.scores[2].eligible
    assert out.winners == [1]


def test_cap_mode() -> None:
    r = rules(version({"type": "adjust_hits", "mode": "cap", "limit": 4}, WIN))
    assert [s.score for s in score_gameweek(r, ROWS).scores] == [66, 65, 68]


def test_chip_exclusion() -> None:
    rows = [EntryGw(1, 5, 90, 0, chip="bboost"), EntryGw(2, 5, 60, 0)]
    r = rules(version({"type": "eligibility", "excluded_chips": ["bboost"]}, WIN))
    assert score_gameweek(r, rows).winners == [2]


def test_tiebreaks_then_split() -> None:
    rows = [EntryGw(1, 5, 64, 4, total_points=200), EntryGw(2, 5, 60, 0, total_points=210)]
    r = rules(
        version(
            {"type": "adjust_hits", "mode": "ignore_all"},
            {"type": "winner", "tiebreak": ["higher_total"]},
        )
    )
    tied = [EntryGw(1, 5, 60, 0, total_points=200), EntryGw(2, 5, 60, 0, total_points=210)]
    assert score_gameweek(r, tied).winners == [2]
    split = rules(version({"type": "winner", "tiebreak": ["split"]}))
    assert score_gameweek(split, tied).winners == [1, 2]
    assert "shared" in score_gameweek(split, tied).explanation
    assert score_gameweek(r, rows).winners == [1]  # 64 beats 60 once hits are ignored


def test_rule_change_applies_from_its_gw_only() -> None:
    r = rules(
        version(WIN),
        version({"type": "adjust_hits", "mode": "ignore_all"}, WIN, from_gw=10),
    )
    early = [EntryGw(1, 5, 70, 8), EntryGw(2, 5, 65, 0)]
    late = [EntryGw(1, 12, 70, 8), EntryGw(2, 12, 65, 0)]
    assert score_gameweek(r, early).winners == [2]
    assert score_gameweek(r, late).winners == [1]


def test_overall_official_vs_league_score() -> None:
    rows = [EntryGw(1, 1, 70, 8), EntryGw(2, 1, 65, 0)]
    steps = ({"type": "adjust_hits", "mode": "ignore_all"}, WIN)
    official = rules(version(*steps))
    league = rules(version(*steps, overall="league_score"))
    assert overall_table(official, [score_gameweek(official, rows)], rows) == {1: 62, 2: 65}
    assert overall_table(league, [score_gameweek(league, rows)], rows) == {1: 70, 2: 65}


@pytest.mark.parametrize(
    "bad",
    [
        version({"type": "adjust_hits", "mode": "ignore_up_to"}, WIN),  # no limit
        version({"type": "adjust_hits", "mode": "count_all"}),  # no winner
        version(WIN, {"type": "adjust_hits", "mode": "count_all"}),  # winner not last
        version({"type": "run_python", "code": "import os"}, WIN),  # unknown step
        version({"type": "eligibility", "max_hit": -4}, WIN),  # negative
    ],
)
def test_invalid_rule_sets_rejected(bad: Mapping[str, object]) -> None:
    with pytest.raises(ValidationError):
        rules(bad)


def test_versions_must_start_at_gw1() -> None:
    with pytest.raises(ValidationError):
        rules(version(WIN, from_gw=3))


def test_load_from_yaml_and_default(tmp_path: Path) -> None:
    (tmp_path / "42.yaml").write_text(
        "league_id: 42\nname: Work\nversions:\n"
        "  - effective_from_gw: 1\n    steps:\n"
        "      - {type: adjust_hits, mode: ignore_up_to, limit: 8}\n"
        "      - {type: winner, tiebreak: [fewer_hits, split]}\n",
        encoding="utf-8",
    )
    loaded = load_league_rules(42, tmp_path)
    assert loaded.name == "Work"
    assert load_league_rules(7, tmp_path).for_gw(1).steps[0].type == "adjust_hits"
