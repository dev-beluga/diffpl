"""Multi-GW transfer planner: a MILP over expected points, solved with HiGHS (ADR-0010).

Each deadline the planner solves for squads, starters and captains over the next `horizon`
GWs, then plays only the first GW's transfers (rolling horizon). The model tracks bank, free
transfers carried over and hits. Prices stay fixed at the deadline across the horizon. No chips.

The starting XI, bench order and captain for the GW come from `best_lineup` on the first GW's
projection, which picks the same XI and captain the MILP valued.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import highspy
import polars as pl

from diffpl.replay.baselines import best_lineup
from diffpl.replay.data import Observation
from diffpl.replay.engine import Market, selling_price
from diffpl.replay.types import Decision, InitialSquad, ManagerView, SquadState, Transfer
from diffpl.rules import POSITIONS, Rules

Projection = dict[int, dict[int, float]]  # gw -> element_id -> expected points
Projector = Callable[[Observation], Projection]

log = logging.getLogger(__name__)

HORIZON = 4
DECAY = 0.85  # weight of GW t+1 relative to GW t: later projections are less certain
BENCH_WEIGHT = 0.1  # value of a bench player's points, a stand-in for auto-sub chances
CANDIDATES_PER_POSITION = 25
CHEAPEST_PER_POSITION = 3
# Solves end on MIP_GAP or, deterministically, on a node cap; never on the clock. A wall-clock
# limit returns whatever was found by then, which depends on machine load, and HiGHS counts it
# across every re-solve of one model, so later plans got cut short. Most solves finish at the
# root; the hardest probed (2024-25 GW23) took 117 nodes and 25 s. At the cap the best plan
# found is kept.
MAX_NODES = 500
MIP_GAP = 1e-3


def fixture_horizon(score: Callable[[Observation], dict[int, float]], horizon: int) -> Projector:
    """Spread a next-GW scorer over the horizon: points per match, times each GW's match count.

    A player whose team blanks the next GW keeps his score as the per-match rate.
    """

    def project(obs: Observation) -> Projection:
        base = score(obs)
        gws = sorted(g for g in obs.fixtures["gw"].unique().to_list() if g is not None)
        gws = [g for g in gws if g >= obs.gw][:horizon]
        team_id = dict(zip(obs.teams["team_name"], obs.teams["team_id"], strict=True))
        market = Market.at(obs.prices, obs.players)
        matches: Counter[tuple[int, int]] = Counter()
        for fx in obs.fixtures.filter(pl.col("gw").is_in(gws)).iter_rows(named=True):
            matches[(fx["gw"], fx["home_team_id"])] += 1
            matches[(fx["gw"], fx["away_team_id"])] += 1
        out: Projection = {}
        for g in gws:
            out[g] = {}
            for i, value in base.items():
                tid = team_id.get(market.team.get(i, ""), -1)
                rate = value / max(1, matches[(obs.gw, tid)])
                out[g][i] = rate * matches[(g, tid)]
        return out

    return project


@dataclass(frozen=True)
class Plan:
    squad: tuple[int, ...]  # the first GW's 15
    transfers: tuple[Transfer, ...]  # the first GW's moves
    hits: int  # points deducted in the first GW
    objective: float
    first_gw: float  # the objective's first-GW part: XI, captain and bench points less hits


def candidates(rules: Rules, xp: Projection, market: Market, owned: set[int]) -> list[int]:
    """Owned players, the best by horizon points per position, and the cheapest per position."""
    total: dict[int, float] = {}
    for per_gw in xp.values():
        for i, v in per_gw.items():
            total[i] = total.get(i, 0.0) + v
    keep = set(owned)
    for pos in rules.squad.positions:
        pool = sorted(i for i in market.price if market.position.get(i) == pos)
        keep |= set(sorted(pool, key=lambda i: (-total.get(i, 0.0), i))[:CANDIDATES_PER_POSITION])
        keep |= set(sorted(pool, key=lambda i: (market.price[i], i))[:CHEAPEST_PER_POSITION])
    return sorted(keep)


def plan(
    rules: Rules,
    market: Market,
    squad: SquadState | None,
    xp: Projection,
    special_events: Mapping[str, int] | None = None,
) -> Plan:
    """The best plan by weighted expected points."""
    return plans(rules, market, squad, xp, special_events, n=1)[0]


def plans(
    rules: Rules,
    market: Market,
    squad: SquadState | None,
    xp: Projection,
    special_events: Mapping[str, int] | None = None,
    n: int = 1,
) -> list[Plan]:
    """Solve the horizon MILP, then re-solve with a cut on each found first-GW squad to get
    up to `n` plans with distinct first-GW squads, best first. `squad` None picks an initial
    squad free of transfer rules."""
    events = special_events or {}
    gws = sorted(xp)
    owned = {p.element_id: p for p in squad.picks} if squad else {}
    players = candidates(rules, xp, market, set(owned))
    sell = {
        i: selling_price(owned[i].purchase_price, market.price[i], rules.transfers.sell_on_fee)
        if i in owned
        else market.price[i]
        for i in players
    }

    h = highspy.Highs()  # type: ignore[no-untyped-call]
    h.setOptionValue("output_flag", False)
    h.setOptionValue("mip_rel_gap", MIP_GAP)
    h.setOptionValue("mip_max_nodes", MAX_NODES)
    h.setOptionValue("threads", 1)

    x = {(i, g): h.addBinary() for i in players for g in gws}  # in squad
    s = {(i, g): h.addBinary() for i in players for g in gws}  # starts
    c = {(i, g): h.addBinary() for i in players for g in gws}  # captain
    buy = {(i, g): h.addBinary() for i in players for g in gws}
    out = {(i, g): h.addBinary() for i in players for g in gws}
    bank = {g: h.addVariable(lb=0) for g in gws}
    ft = {g: h.addIntegral(lb=0, ub=rules.transfers.max_banked) for g in gws}
    hits = {g: h.addIntegral(lb=0) for g in gws}
    moves = {g: sum(buy[i, g] for i in players) for g in gws}  # transfers made

    objective = 0.0 * bank[gws[0]]
    clubs = Counter(market.team[i] for i in owned)
    for t, g in enumerate(gws):
        weight = DECAY**t
        for i in players:
            v = xp[g].get(i, 0.0)
            objective += weight * v * (s[i, g] + c[i, g] + BENCH_WEIGHT * (x[i, g] - s[i, g]))
            h.addConstr(s[i, g] <= x[i, g])
            h.addConstr(c[i, g] <= s[i, g])
            h.addConstr(buy[i, g] + out[i, g] <= 1)
        objective -= weight * rules.transfers.hit_cost * hits[g]

        h.addConstr(sum(x[i, g] for i in players) == rules.squad.size)
        h.addConstr(sum(s[i, g] for i in players) == rules.squad.starting)
        h.addConstr(sum(c[i, g] for i in players) == 1)
        for pos, lim in rules.squad.positions.items():
            at = [i for i in players if market.position[i] == pos]
            h.addConstr(sum(x[i, g] for i in at) == lim.select)
            h.addConstr(sum(s[i, g] for i in at) >= lim.min_play)
            h.addConstr(sum(s[i, g] for i in at) <= lim.max_play)
        # Sorted: set order follows string hashing, which changes per process, and constraint
        # order steers which of several near-tied optima HiGHS returns.
        for club in sorted({market.team[i] for i in players}):
            limit = max(rules.squad.max_per_team, clubs[club])  # FPL tolerates moved players
            h.addConstr(sum(x[i, g] for i in players if market.team[i] == club) <= limit)

        if t == 0 and squad is None:  # initial squad: no transfers, bank is the leftover
            h.addConstr(
                bank[g]
                == rules.squad.budget_tenths - sum(market.price[i] * x[i, g] for i in players)
            )
            h.addConstr(moves[g] == 0)
            h.addConstr(hits[g] == 0)
            continue
        prev_bank = squad.bank if t == 0 and squad else bank[gws[t - 1]]
        for i in players:
            prev = (1 if i in owned else 0) if t == 0 else x[i, gws[t - 1]]
            h.addConstr(x[i, g] == prev + buy[i, g] - out[i, g])
        h.addConstr(
            bank[g]
            == prev_bank
            + sum(sell[i] * out[i, g] for i in players)
            - sum(market.price[i] * buy[i, g] for i in players)
        )
        if t == 0:
            assert squad is not None
            h.addConstr(ft[g] == squad.free_transfers)
        elif events.get("topup_free_transfers_gw") == g:
            h.addConstr(ft[g] == rules.transfers.max_banked)
        elif t == 1 and squad is None:
            h.addConstr(ft[g] == rules.transfers.free_per_gw)
        else:
            p = gws[t - 1]
            kept = (
                ft[p] if events.get("unlimited_transfers_gw") == p else ft[p] - moves[p] + hits[p]
            )
            h.addConstr(ft[g] <= kept + rules.transfers.free_per_gw)
        if events.get("unlimited_transfers_gw") == g:
            h.addConstr(hits[g] == 0)
        else:
            h.addConstr(hits[g] >= moves[g] - ft[g])

    g0 = gws[0]
    found: list[Plan] = []
    while len(found) < n:
        h.maximize(objective)
        status = h.getModelStatus()
        if status == highspy.HighsModelStatus.kInfeasible and found:
            break  # fewer distinct squads than asked for
        if status == highspy.HighsModelStatus.kSolutionLimit and h.getInfo().primal_solution_status:
            # Node cap reached with a feasible plan: deterministic, so keep it and say so.
            log.warning("planner stopped at %d nodes, gap %.4f", MAX_NODES, h.getInfo().mip_gap)
        elif status != highspy.HighsModelStatus.kOptimal:
            raise RuntimeError(f"planner MILP failed: {h.modelStatusToString(status)}")
        chosen = tuple(sorted(i for i in players if h.val(x[i, g0]) > 0.5))
        hit = 0 if squad is None else round(h.val(hits[g0])) * rules.transfers.hit_cost
        first = sum(
            xp[g0].get(i, 0.0)
            * (
                h.val(s[i, g0])
                + h.val(c[i, g0])
                + BENCH_WEIGHT * (h.val(x[i, g0]) - h.val(s[i, g0]))
            )
            for i in players
        )

        # Pair each sale with a purchase in the same position, so a transfer reads as a swap.
        def by_position(i: int) -> tuple[int, int]:
            return (POSITIONS.index(market.position[i]), i)

        ins = sorted((i for i in chosen if i not in owned), key=by_position)
        outs = sorted((i for i in owned if i not in chosen), key=by_position)
        found.append(
            Plan(
                squad=chosen,
                transfers=tuple(Transfer(o, i) for o, i in zip(outs, ins, strict=True))
                if squad
                else (),
                hits=hit,
                objective=h.getInfo().objective_function_value,
                first_gw=first - hit,
            )
        )
        h.addConstr(sum(x[i, g0] for i in chosen) <= rules.squad.size - 1)  # no-good cut
    return found


@dataclass
class PlannerManager:
    """Replay manager that plays the first GW of each horizon plan."""

    name: str
    rules: Rules
    project: Projector

    def pick_squad(self, view: ManagerView) -> InitialSquad:
        market = Market.at(view.obs.prices, view.obs.players)
        xp = self.project(view.obs)
        p = plan(self.rules, market, None, xp, self.rules.special_events)
        lineup = best_lineup(self.rules, list(p.squad), xp[view.obs.gw], market.position)
        return InitialSquad(p.squad, lineup)

    def act(self, view: ManagerView) -> Decision:
        assert view.squad is not None
        market = Market.at(view.obs.prices, view.obs.players)
        xp = self.project(view.obs)
        p = plan(self.rules, market, view.squad, xp, self.rules.special_events)
        d = best_lineup(self.rules, list(p.squad), xp[view.obs.gw], market.position)
        return Decision(d.lineup, d.bench, d.captain, d.vice_captain, p.transfers)
