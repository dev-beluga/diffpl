"""MILP planner: legal squads, hits only when they pay, and decisions blind to the future."""

from collections.abc import Callable
from itertools import pairwise

import pytest
from test_replay_baselines import Recorder, poison_future, varied_season
from test_replay_run import POSITIONS, SQUAD

from diffpl.optim.planner import PlannerManager, fixture_horizon, plan
from diffpl.replay.baselines import form_scores
from diffpl.replay.engine import Market, check_squad
from diffpl.replay.run import run_season
from diffpl.replay.types import Pick, SquadState
from diffpl.rules import load_rules

RULES = load_rules("2025-26")
IDS = list(range(1, len(POSITIONS) + 1))


def market(price: Callable[[int], int] = lambda i: 60) -> Market:
    return Market(
        price={i: price(i) for i in IDS},
        team={i: f"T{i}" for i in IDS},
        position=dict(zip(IDS, POSITIONS, strict=True)),  # type: ignore[arg-type]
    )


def flat(gws: list[int], value: Callable[[int, int], float]) -> dict[int, dict[int, float]]:
    return {g: {i: value(g, i) for i in IDS} for g in gws}


def owned(bank: int = 0, free_transfers: int = 1) -> SquadState:
    return SquadState(tuple(Pick(i, 60) for i in SQUAD), bank, free_transfers)


def test_initial_squad_is_legal_and_takes_the_best_within_budget() -> None:
    m = market(lambda i: 80 if i in (3, 9) else 60)  # 15 x 60 = 900 leaves room for both
    p = plan(RULES, m, None, flat([1, 2], lambda g, i: i))
    check_squad(RULES, list(p.squad), m)
    assert sum(m.price[i] for i in p.squad) <= RULES.squad.budget_tenths
    assert p.transfers == () and p.hits == 0
    assert {3, 9, 19} <= set(p.squad)  # top xP at each position it fits


def test_over_budget_star_is_left_out() -> None:
    m = market(lambda i: 200 if i == 19 else 60)  # 14 x 60 + 200 > 1000
    p = plan(RULES, m, None, flat([1], lambda g, i: 50.0 if i == 19 else 1.0))
    assert 19 not in p.squad


def test_hit_taken_only_when_gain_beats_its_cost() -> None:
    # Player 15 (MID, not owned) beats owned MIDs by `gain` per GW over 2 GWs.
    for gain, expect_hit in ((1.0, False), (6.0, True)):
        xp = {g: {i: 2.0 + (gain if i == 15 else 0.0) for i in IDS} for g in (2, 3)}
        p = plan(RULES, market(), owned(free_transfers=0), xp)
        assert (p.hits == RULES.transfers.hit_cost) is expect_hit
        assert (15 in p.squad) is expect_hit


def test_free_transfer_used_for_any_gain() -> None:
    xp = flat([2], lambda g, i: 2.0 + (0.5 if i == 15 else 0.0))
    p = plan(RULES, market(), owned(free_transfers=1), xp)
    assert p.hits == 0 and len(p.transfers) == 1 and p.transfers[0].in_id == 15


def test_banks_transfer_for_a_later_double_move() -> None:
    # Two upgrades only appear in GW3; one FT now, so rolling gives two free moves then.
    def value(g: int, i: int) -> float:
        if i in (15, 19):
            return 7.0 if g == 3 else 0.0
        return 2.0

    p = plan(RULES, market(), owned(free_transfers=1), flat([2, 3], value))
    assert p.transfers == () and p.hits == 0


def projector() -> Callable[..., dict[int, dict[int, float]]]:
    return fixture_horizon(form_scores, horizon=2)


def test_planner_plays_season_without_violations() -> None:
    r = run_season(varied_season(), RULES, PlannerManager("planner", RULES, projector()))
    assert r.violations == []


@pytest.mark.parametrize("from_gw", [2, 3])
def test_poisoned_future_does_not_change_decisions(from_gw: int) -> None:
    data = varied_season()
    clean = Recorder(PlannerManager("planner", RULES, projector()))
    dirty = Recorder(PlannerManager("planner", RULES, projector()))
    run_season(data, RULES, clean)
    run_season(poison_future(data, from_gw), RULES, dirty)
    assert clean.log[:from_gw] == dirty.log[:from_gw]


def test_top_plans_have_distinct_first_gw_squads_best_first() -> None:
    from diffpl.optim.planner import plans

    xp = flat([2, 3], lambda g, i: 2.0 + (0.5 if i in (15, 19) else 0.0))
    found = plans(RULES, market(), owned(free_transfers=1), xp, n=4)
    assert len(found) == 4
    assert len({p.squad for p in found}) == 4
    assert all(a.objective >= b.objective - 1e-6 for a, b in pairwise(found))
    assert found[0].squad == plan(RULES, market(), owned(free_transfers=1), xp).squad
