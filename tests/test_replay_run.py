from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from diffpl.replay.data import SeasonData
from diffpl.replay.engine import InvalidDecision
from diffpl.replay.run import run_season
from diffpl.replay.types import Decision, InitialSquad, ManagerView, Transfer
from diffpl.rules import load_rules

RULES = load_rules("2025-26")
T0 = datetime(2025, 8, 15, 17, 30, tzinfo=UTC)
GWS = (1, 2, 3)
POSITIONS = ["GKP"] * 3 + ["DEF"] * 6 + ["MID"] * 6 + ["FWD"] * 4  # ids 1-19
LINEUP = (1, 4, 5, 6, 7, 10, 11, 12, 13, 16, 17)
BENCH = (2, 14, 8, 18)
SQUAD = (*LINEUP, *BENCH)
DEC = Decision(LINEUP, BENCH, captain=16, vice_captain=10)


def deadline(gw: int) -> datetime:
    return T0 + timedelta(days=7 * (gw - 1))


def make_season() -> SeasonData:
    ids = list(range(1, len(POSITIONS) + 1))
    rows = [(i, gw) for gw in GWS for i in ids]
    kick = [deadline(gw) + timedelta(hours=2) for _, gw in rows]
    return SeasonData(
        season="2025-26",
        deadlines=pl.DataFrame({"gw": list(GWS), "deadline_time": [deadline(g) for g in GWS]}),
        player_matches=pl.DataFrame(
            {
                "element_id": [i for i, _ in rows],
                "gw": [gw for _, gw in rows],
                "total_points": [2] * len(rows),
                "minutes": [90] * len(rows),
                "as_of": [k + timedelta(hours=3) for k in kick],
            }
        ),
        prices=pl.DataFrame(
            {
                "gw": [gw for _, gw in rows],
                "element_id": [i for i, _ in rows],
                "team_name": [f"T{i}" for i, _ in rows],
                "price_tenths": [60] * len(rows),
                "as_of": [deadline(gw) - timedelta(minutes=1) for _, gw in rows],
            }
        ),
        fixtures=pl.DataFrame(
            {
                "fixture_id": list(GWS),
                "gw": list(GWS),
                "home_score": [1, 1, 1],
                "away_score": [0, 0, 0],
                "finished": [True] * 3,
                "result_as_of": [deadline(g) + timedelta(hours=5) for g in GWS],
            }
        ),
        players=pl.DataFrame(
            {"element_id": ids, "player_name": [str(i) for i in ids], "position": POSITIONS}
        ),
    )


@dataclass
class Scripted:
    """Plays a fixed squad and returns pre-set decisions per GW."""

    name: str = "scripted"
    by_gw: dict[int, Decision] = field(default_factory=dict)
    seen_squads: list[int] = field(default_factory=list)

    def pick_squad(self, view: ManagerView) -> InitialSquad:
        return InitialSquad(picks=SQUAD, decision=DEC)

    def act(self, view: ManagerView) -> Decision:
        assert view.squad is not None
        self.seen_squads.append(len(view.squad.picks))
        return self.by_gw.get(view.obs.gw, DEC)


def test_hold_all_season_scores_every_gw() -> None:
    result = run_season(make_season(), RULES, Scripted())
    # 11 starters x 2 + captain 2 = 24 per GW
    assert [g.points for g in result.gws] == [24, 24, 24]
    assert result.summary()["violations"] == 0


def test_second_transfer_in_gw2_costs_a_hit() -> None:
    two = replace(DEC, transfers=(Transfer(17, 19), Transfer(14, 15)))
    two = replace(two, lineup=(1, 4, 5, 6, 7, 10, 11, 12, 13, 16, 19), bench=(2, 15, 8, 18))
    result = run_season(make_season(), RULES, Scripted(by_gw={2: two}))
    assert result.gws[1].hit_cost == 4
    assert result.gws[1].points == 20


def test_invalid_decision_falls_back_and_is_logged() -> None:
    bad = replace(DEC, transfers=(Transfer(99, 19),))
    result = run_season(make_season(), RULES, Scripted(by_gw={2: bad}))
    assert result.violations and result.violations[0][0] == 2
    assert result.gws[1].points == 24


def test_free_hit_reverts_squad() -> None:
    fh = replace(
        DEC,
        chip="freehit",
        transfers=(Transfer(17, 19),),
        lineup=(1, 4, 5, 6, 7, 10, 11, 12, 13, 16, 19),
    )
    result = run_season(make_season(), RULES, Scripted(by_gw={2: fh}))
    assert result.gws[1].chip == "freehit"
    assert result.gws[1].hit_cost == 0
    assert result.violations == []  # GW3 uses the original lineup with player 17 back


def test_over_budget_initial_squad_is_fatal() -> None:
    data = make_season()
    data = replace(data, prices=data.prices.with_columns(pl.lit(100).alias("price_tenths")))
    with pytest.raises(InvalidDecision, match="budget"):
        run_season(data, RULES, Scripted())
