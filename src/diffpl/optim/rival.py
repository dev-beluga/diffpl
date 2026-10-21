"""Rank-aware planner: choose among the top EV plans by P(beat a rival) (ADR-0011).

The MILP (ADR-0010) proposes up to N_PLANS plans with distinct first-GW squads. Each is scored
on joint simulator draws (ADR-0009) against one rival:

- first GW: points per draw for my XI and captain, and for the rival's, with hits adjusted by
  the league's own rules (ADR-0005);
- later GWs: each side's weighted expected points, mine from the plan, the rival's from their
  current squad held unchanged;
- P(beat) is the share of draws where my horizon total is higher (ties count half).

The plan with the highest P(beat) is played. With no rival known, the EV-best plan is played.
Simplifications: only the first GW is random, the rival makes no transfers, no auto-subs in
the draws.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np

from diffpl.leagues.rules import EntryGw, LeagueRules, default_rules, score_gameweek
from diffpl.optim.planner import BENCH_WEIGHT, DECAY, Plan, Projection, Projector, plans
from diffpl.replay.baselines import best_lineup
from diffpl.replay.data import Observation
from diffpl.replay.engine import Market
from diffpl.replay.types import Decision, InitialSquad, ManagerView, SquadState
from diffpl.rules import Position, Rules

N_PLANS = 10
ME, RIVAL = 0, 1  # entry ids inside the league scoring call


@dataclass(frozen=True)
class Draws:
    element_id: np.ndarray
    points: np.ndarray  # draws x players, joint


@dataclass(frozen=True)
class RivalView:
    """What the manager knows about the rival at the deadline: their last lineup and captain."""

    entry_id: int
    decision: Decision


@dataclass(frozen=True)
class Choice:
    """One deadline's comparison, kept for the eval report and the UI."""

    gw: int
    p_beat: tuple[float, ...]  # per plan, EV order
    objective: tuple[float, ...]
    chosen: int  # index into the plans
    transfers: tuple[tuple[int, int], ...]  # chosen plan's (out, in)


def gw_points(draws: Draws, d: Decision) -> np.ndarray:
    """Per-draw points of an XI with the captain doubled. Players without draws score 0."""
    col = {e: i for i, e in enumerate(draws.element_id.tolist())}
    total = np.zeros(draws.points.shape[0])
    for e in (*d.lineup, d.captain):
        if e in col:
            total += draws.points[:, col[e]]
    return total


def squad_value(
    rules: Rules, squad: list[int], xp: Mapping[int, float], position: Mapping[int, Position]
) -> float:
    """Expected points of a squad's best XI, captain and bench, as the MILP values it."""
    d = best_lineup(rules, squad, xp, position)
    return (
        sum(xp.get(i, 0.0) for i in d.lineup)
        + xp.get(d.captain, 0.0)
        + BENCH_WEIGHT * sum(xp.get(i, 0.0) for i in d.bench)
    )


INELIGIBLE = -10_000  # a side the league rules bar from the GW cannot come out ahead


def hit_adjustment(league: LeagueRules, gw: int, my_hits: int, rival_hits: int) -> tuple[int, int]:
    """League score offsets from hits under the league's rules: (mine, the rival's)."""
    out = score_gameweek(league, [EntryGw(ME, gw, 0, my_hits), EntryGw(RIVAL, gw, 0, rival_hits)])
    by = {s.entry_id: s.score if s.eligible else INELIGIBLE for s in out.scores}
    return by[ME], by[RIVAL]


def p_beat(
    rules: Rules,
    league: LeagueRules,
    gw: int,
    draws: Draws,
    xp: Projection,
    position: Mapping[int, Position],
    plan: Plan,
    rival: RivalView,
) -> float:
    mine = best_lineup(rules, list(plan.squad), xp[gw], position)
    later = [g for g in sorted(xp) if g > gw]
    rival_squad = [*rival.decision.lineup, *rival.decision.bench]
    rival_future = sum(
        DECAY ** (t + 1) * squad_value(rules, rival_squad, xp[g], position)
        for t, g in enumerate(later)
    )
    my_adj, rival_adj = hit_adjustment(league, gw, plan.hits, 0)
    margin = (
        gw_points(draws, mine)
        + my_adj
        + (plan.objective - plan.first_gw)
        - gw_points(draws, rival.decision)
        - rival_adj
        - rival_future
    )
    return float((margin > 0).mean() + 0.5 * (margin == 0).mean())


@dataclass
class RivalManager:
    """Plays the plan with the best P(beat rival) among the top EV plans."""

    name: str
    rules: Rules
    project: Projector
    simulate: Callable[[Observation], Draws]
    rival: Callable[[Observation], RivalView | None]
    league: LeagueRules = field(default_factory=lambda: default_rules(0))
    n_plans: int = N_PLANS
    choices: list[Choice] = field(default_factory=list)

    def pick_squad(self, view: ManagerView) -> InitialSquad:
        market = Market.at(view.obs.prices, view.obs.players)
        xp = self.project(view.obs)
        p = plans(self.rules, market, None, xp, self.rules.special_events)[0]
        return InitialSquad(
            p.squad, best_lineup(self.rules, list(p.squad), xp[view.obs.gw], market.position)
        )

    def act(self, view: ManagerView) -> Decision:
        assert view.squad is not None
        obs = view.obs
        market = Market.at(obs.prices, obs.players)
        xp = self.project(obs)
        rival = self.rival(obs)
        found, probs = rank_plans(
            self.rules, self.league, obs, market, view.squad, xp, self.simulate, rival, self.n_plans
        )
        best = int(np.argmax(probs)) if probs else 0  # first maximum: ties go to higher EV
        chosen = found[best]
        self.choices.append(
            Choice(
                obs.gw,
                probs,
                tuple(p.objective for p in found),
                best,
                tuple((t.out_id, t.in_id) for t in chosen.transfers),
            )
        )
        d = best_lineup(self.rules, list(chosen.squad), xp[obs.gw], market.position)
        return Decision(d.lineup, d.bench, d.captain, d.vice_captain, chosen.transfers)


def rank_plans(
    rules: Rules,
    league: LeagueRules,
    obs: Observation,
    market: Market,
    squad: SquadState,
    xp: Projection,
    simulate: Callable[[Observation], Draws],
    rival: RivalView | None,
    n_plans: int = N_PLANS,
) -> tuple[list[Plan], tuple[float, ...]]:
    """Top EV plans, best first, and each one's P(beat rival). No rival: the EV plan alone
    and no probabilities."""
    found = plans(rules, market, squad, xp, rules.special_events, n=n_plans if rival else 1)
    if rival is None:
        return found, ()
    draws = simulate(obs)
    return found, tuple(
        p_beat(rules, league, obs.gw, draws, xp, market.position, p, rival) for p in found
    )
