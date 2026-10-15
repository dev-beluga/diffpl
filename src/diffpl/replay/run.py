"""Play one manager through one season and record what happened."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import polars as pl

from diffpl.replay.data import SeasonData
from diffpl.replay.engine import (
    InvalidDecision,
    Market,
    apply_transfers,
    check_lineup,
    check_squad,
    next_free_transfers,
    score_gw,
)
from diffpl.replay.types import Decision, GwResult, Manager, ManagerView, Pick, SquadState
from diffpl.rules import Rules


@dataclass
class RunResult:
    season: str
    manager: str
    gws: list[GwResult] = field(default_factory=list)
    violations: list[tuple[int, str]] = field(default_factory=list)  # (gw, reason)

    @property
    def total_points(self) -> int:
        return sum(g.points for g in self.gws)

    @property
    def hit_cost(self) -> int:
        return sum(g.hit_cost for g in self.gws)

    def summary(self) -> dict[str, object]:
        return {
            "season": self.season,
            "manager": self.manager,
            "total_points": self.total_points,
            "hit_cost": self.hit_cost,
            "transfers": sum(g.transfers for g in self.gws),
            "chips": [(g.chip, g.gw) for g in self.gws if g.chip],
            "violations": len(self.violations),
        }


def gw_totals(data: SeasonData, gw: int) -> tuple[dict[int, int], dict[int, int]]:
    """Points and minutes per player summed over the GW's matches. Env side only."""
    rows = (
        data.player_matches.filter(pl.col("gw") == gw)
        .group_by("element_id", maintain_order=True)
        .agg(pl.col("total_points").sum(), pl.col("minutes").sum())
    )
    ids = rows["element_id"].to_list()
    return (
        dict(zip(ids, rows["total_points"].to_list(), strict=True)),
        dict(zip(ids, rows["minutes"].to_list(), strict=True)),
    )


def initial_state(rules: Rules, picks: tuple[int, ...], market: Market) -> SquadState:
    check_squad(rules, list(picks), market)
    cost = sum(market.price[i] for i in picks)
    if cost > rules.squad.budget_tenths:
        raise InvalidDecision(f"initial squad costs {cost}, budget {rules.squad.budget_tenths}")
    return SquadState(
        picks=tuple(Pick(i, market.price[i]) for i in picks),
        bank=rules.squad.budget_tenths - cost,
        free_transfers=0,  # GW1 is free; GW2 starts with one
    )


def squad_ids(state: SquadState) -> set[int]:
    return {p.element_id for p in state.picks}


def fallback(previous: Decision) -> Decision:
    """Used when a decision is invalid: last GW's lineup, no transfers, no chip."""
    return replace(previous, transfers=(), chip=None)


def run_season(data: SeasonData, rules: Rules, manager: Manager) -> RunResult:
    result = RunResult(data.season, manager.name)
    state: SquadState | None = None
    previous: Decision | None = None
    for gw in data.gameweeks:
        obs = data.observe(gw)
        market = Market.at(obs.prices, obs.players)
        unlimited = rules.special_events.get("unlimited_transfers_gw") == gw

        if state is None:
            init = manager.pick_squad(ManagerView(obs, None))
            state = initial_state(rules, init.picks, market)  # GW1 errors are fatal
            decision = replace(init.decision, transfers=())
        else:
            if rules.special_events.get("topup_free_transfers_gw") == gw:
                state = replace(state, free_transfers=rules.transfers.max_banked)
            decision = manager.act(ManagerView(obs, state))

        try:
            applied = apply_transfers(rules, state, decision, market, gw, unlimited)
            check_lineup(rules, squad_ids(applied.state), decision, market.position)
        except InvalidDecision as exc:
            if previous is None:
                raise
            result.violations.append((gw, str(exc)))
            decision = fallback(previous)
            applied = apply_transfers(rules, state, decision, market, gw, unlimited)
            check_lineup(rules, squad_ids(applied.state), decision, market.position)

        points, minutes = gw_totals(data, gw)
        scored = score_gw(rules, decision, market.position, points, minutes)
        result.gws.append(
            GwResult(
                gw=gw,
                points=scored.points - applied.hits,
                hit_cost=applied.hits,
                transfers=applied.n_transfers,
                chip=decision.chip,
                captain=scored.armband or decision.captain,
                auto_subs=scored.auto_subs,
            )
        )

        ft = next_free_transfers(
            rules, state.free_transfers, applied.n_transfers, decision.chip, unlimited
        )
        if decision.chip == "freehit":  # squad reverts; the chip stays used
            state = replace(state, free_transfers=ft, chips_used=applied.state.chips_used)
        else:
            state = replace(applied.state, free_transfers=ft)
            previous = decision
    return result
