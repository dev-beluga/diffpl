"""Rank-aware planner: P(beat rival) scoring, league hit rules, and leakage."""

import numpy as np
import pytest
from test_planner import IDS, RULES, flat, market, owned
from test_replay_baselines import Recorder, poison_future, varied_season
from test_replay_run import DEC

from diffpl.leagues.rules import LeagueRules
from diffpl.optim.planner import Plan, PlannerManager, Projector, fixture_horizon, plans
from diffpl.optim.rival import (
    EV_SLACK,
    INELIGIBLE,
    Draws,
    RivalManager,
    RivalView,
    choose,
    gw_points,
    hit_adjustment,
    p_beat,
)
from diffpl.replay.baselines import form_scores
from diffpl.replay.data import Observation
from diffpl.replay.run import run_season
from diffpl.replay.types import Decision

POSITION = market().position


def league(*steps: dict[str, object]) -> LeagueRules:
    return LeagueRules.model_validate(
        {"league_id": 1, "name": "test", "versions": [{"effective_from_gw": 1, "steps": steps}]}
    )


def draws(seed: int = 0) -> Draws:
    rng = np.random.default_rng(seed)
    return Draws(np.array(IDS), rng.poisson(3.0, size=(500, len(IDS))).astype(float))


def test_gw_points_doubles_the_captain_and_skips_unknown_players() -> None:
    d = Draws(np.array([1, 2]), np.array([[1.0, 5.0], [2.0, 0.0]]))
    dec = Decision((1, 2, 99), (), captain=2, vice_captain=1)
    assert gw_points(d, dec).tolist() == [11.0, 2.0]


def test_hits_follow_the_league_rules() -> None:
    official = league({"type": "adjust_hits", "mode": "count_all"}, {"type": "winner"})
    lenient = league(
        {"type": "adjust_hits", "mode": "ignore_up_to", "limit": 8},
        {"type": "eligibility", "max_hit": 8},
        {"type": "winner"},
    )
    assert hit_adjustment(official, 2, 8, 0) == (-8, 0)
    assert hit_adjustment(lenient, 2, 8, 4) == (0, 0)
    assert hit_adjustment(lenient, 2, 12, 0) == (INELIGIBLE, 0)


def test_mirror_rival_is_a_coin_flip_and_a_weaker_rival_is_beaten() -> None:
    xp = flat([2], lambda g, i: float(i % 5))  # one GW: no future moves to favour my side
    lg = league({"type": "adjust_hits", "mode": "count_all"}, {"type": "winner"})
    me = plans(RULES, market(), owned(), xp)[0]
    from diffpl.replay.baselines import best_lineup

    mine = best_lineup(RULES, list(me.squad), xp[2], POSITION)
    mirror = RivalView(2, mine)
    assert p_beat(RULES, lg, 2, draws(), xp, POSITION, _no_moves(me), mirror) == pytest.approx(0.5)
    weak = RivalView(2, DEC)  # DEC has worse players in this projection
    assert p_beat(RULES, lg, 2, draws(), flat([2, 3], lambda g, i: 0.0), POSITION, me, weak) < 1


def _no_moves(p: Plan) -> Plan:
    return Plan(p.squad, (), 0, p.objective, p.first_gw)


def projector() -> Projector:
    return fixture_horizon(form_scores, horizon=2)


def simulate(obs: Observation) -> Draws:
    return draws(obs.gw)


def rival_of(obs: Observation) -> RivalView | None:
    return RivalView(2, DEC) if obs.gw > 1 else None


def test_without_a_rival_it_plays_the_ev_plan() -> None:
    data = varied_season()
    ev = Recorder(PlannerManager("planner", RULES, projector()))
    ra = Recorder(RivalManager("rival", RULES, projector(), simulate, lambda obs: None))
    run_season(data, RULES, ev)
    run_season(data, RULES, ra)
    assert ev.log == ra.log


def test_rival_manager_plays_legal_season_and_records_choices() -> None:
    m = RivalManager("rival", RULES, projector(), simulate, rival_of, n_plans=3)
    r = run_season(varied_season(), RULES, m)
    assert r.violations == []
    assert [c.gw for c in m.choices] == [2, 3]
    for c in m.choices:
        eligible = [
            p for p, o in zip(c.p_beat, c.objective, strict=True) if o >= c.objective[0] - EV_SLACK
        ]
        assert len(c.p_beat) == len(c.objective) and c.p_beat[c.chosen] == max(eligible)
        assert c.objective[c.chosen] >= c.objective[0] - EV_SLACK


@pytest.mark.parametrize("from_gw", [2, 3])
def test_poisoned_future_does_not_change_decisions(from_gw: int) -> None:
    data = varied_season()
    clean = Recorder(RivalManager("rival", RULES, projector(), simulate, rival_of, n_plans=3))
    dirty = Recorder(RivalManager("rival", RULES, projector(), simulate, rival_of, n_plans=3))
    run_season(data, RULES, clean)
    run_season(poison_future(data, from_gw), RULES, dirty)
    assert clean.log[:from_gw] == dirty.log[:from_gw]


def test_choose_stays_within_the_ev_slack() -> None:
    found = [Plan((), (), 0, obj, 0.0) for obj in (50.0, 49.0, 47.0)]
    assert choose(found, (0.4, 0.5, 0.9)) == 1  # plan 3 has the best odds but costs 3 points
    assert choose(found, (0.6, 0.5, 0.9)) == 0
    assert choose(found, (0.5, 0.5, 0.1)) == 0  # ties go to the higher EV plan
    assert choose(found, ()) == 0
