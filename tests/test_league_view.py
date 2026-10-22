"""League page: standings gaps, exposure split, template and differential targets."""

import polars as pl

from diffpl.api.league import league_view
from diffpl.api.stats import PlayerRow
from diffpl.leagues.report import LeagueData
from diffpl.rules import Position

GW = 7


def player(i: int, pos: Position = "MID") -> PlayerRow:
    return PlayerRow(
        element_id=i, name=f"P{i}", team="ARS", position=pos, price=6.0, ownership=10.0,
        minutes=500, points=40, form=5.0, xg90=0.2, xa90=0.1, xgi90=0.3,
    )  # fmt: skip


def league(owned: dict[int, list[int]], captain: dict[int, int]) -> LeagueData:
    """`owned` maps entry id to its players at GW; ownership is computed from it."""
    entries = sorted(owned)
    picks = pl.DataFrame(
        [
            {
                "entry_id": e,
                "gw": GW,
                "element_id": i,
                "multiplier": 2 if captain.get(e) == i else 1,
            }
            for e in entries
            for i in owned[e]
        ]
    )
    own = (
        picks.group_by("element_id")
        .agg(
            (pl.len() / len(entries)).alias("ownership"),
            (pl.col("multiplier").sum() / len(entries)).alias("effective_ownership"),
        )
        .with_columns(pl.lit(GW).alias("gw"))
    )
    managers = pl.DataFrame(
        {
            "rank": list(range(1, len(entries) + 1)),
            "entry_id": entries,
            "entry_name": [f"Team {e}" for e in entries],
            "player_name": [f"Manager {e}" for e in entries],
            "total_points": [500 - 10 * k for k in range(len(entries))],
        }
    )
    names = pl.DataFrame(
        {"element_id": list(range(1, 11)), "web_name": [f"P{i}" for i in range(1, 11)]}
    )
    return LeagueData(1, managers, own, pl.DataFrame(), picks, names)


def test_standings_gap_exposure_and_targets() -> None:
    mini = league({1: [1, 2, 3], 2: [1, 4], 3: [1, 4]}, captain={2: 1, 3: 1})
    top = league({10: [5, 6], 11: [5, 7], 12: [5, 3]}, captain={})
    players = {i: player(i) for i in range(1, 9)}
    xp = {i: float(i) for i in range(1, 9)}  # higher id, more expected points
    v = league_view(mini, 1, top, "overall top 100", players, xp)

    assert [s.gap for s in v.standings] == [0, 10, 20]
    assert {r.element_id for r in v.differentials} == {2, 3}  # owned only by entry 1
    assert {r.element_id for r in v.threats} >= {4}  # owned by the rest, not entry 1
    threat_1 = next(r for r in v.threats if r.element_id == 1)  # captained by the others
    assert threat_1.mine == 1 and threat_1.exposure < 0

    template = [t.element_id for t in v.template_targets]
    assert template[0] == 5 and 3 not in template  # 3 is already owned
    assert v.template_targets[0].reference_ownership == 100.0
    diffs = [t.element_id for t in v.differential_targets]
    assert diffs[0] == 8 and 4 not in diffs and 1 not in diffs  # 4 and 1 are league template


def test_without_a_team_there_is_no_exposure() -> None:
    mini = league({1: [1], 2: [2]}, captain={})
    v = league_view(mini, None, mini, "this league", {1: player(1), 2: player(2)}, {1: 1.0, 2: 2.0})
    assert v.differentials == [] and v.threats == [] and len(v.standings) == 2


def test_compare_splits_squads_and_flags_captain_and_bench() -> None:
    from diffpl.api.league import compare

    mini = league({1: [1, 2, 3], 2: [1, 4]}, captain={1: 2, 2: 1})
    mini = LeagueData(
        mini.league_id,
        mini.managers,
        mini.ownership,
        pl.DataFrame(
            {
                "entry_id": [1, 2],
                "gw": [GW, GW],
                "points": [60, 50],
                "hit_cost": [4, 0],
                "chip": [None, "bboost"],
                "value_tenths": [1000, 1010],
                "bank_tenths": [5, 0],
            }
        ),
        mini.picks.with_columns(pl.lit(1).alias("slot")),
        mini.names,
    )
    c = compare(mini, 1, 2, {i: player(i) for i in range(1, 5)}, {i: float(i) for i in range(1, 5)})
    assert [p.element_id for p in c.shared] == [1]
    assert c.shared[0].mult_a == 1 and c.shared[0].mult_b == 2  # entry 2 captains player 1
    assert {p.element_id for p in c.only_a} == {2, 3} and [p.element_id for p in c.only_b] == [4]
    assert c.a.gw_points == 60 and c.a.hits == 4 and c.b.chip == "bboost" and c.b.value == 101.0
