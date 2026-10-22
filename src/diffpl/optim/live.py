"""This GW's plans for a real FPL team: the top plans by expected points (ADR-0010).

Teams come from the league ingest (`diffpl.ingest league`), read-only. Known gaps, all from
what the public API exposes:
- purchase prices are private, so selling prices are taken as current prices (sell-on gains
  are ignored);
- free transfers are rebuilt from the entry's transfer and chip history with the season rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl
from sqlalchemy import Engine, text

from diffpl.optim.planner import Plan, Projector, plans
from diffpl.replay.baselines import best_lineup
from diffpl.replay.data import Observation
from diffpl.replay.engine import Market, next_free_transfers
from diffpl.replay.types import ChipName, Decision, Pick, SquadState
from diffpl.rules import Rules

CHIP_NAMES: dict[str, ChipName] = {
    "wildcard": "wildcard",
    "freehit": "freehit",
    "bboost": "bboost",
    "3xc": "3xc",
}


@dataclass(frozen=True)
class Entry:
    entry_id: int
    squad: SquadState  # going into the next deadline
    last: Decision  # lineup and captain at the last deadline


@dataclass(frozen=True)
class Option:
    plan: Plan
    decision: Decision  # XI, bench and captain for this GW


def _query(engine: Engine, sql: str, entry_id: int) -> pl.DataFrame:
    with engine.connect() as conn:
        return pl.read_database(text(sql), conn, execute_options={"parameters": {"e": entry_id}})


def free_transfers(
    rules: Rules, history: Sequence[tuple[int, int, ChipName | None]], next_gw: int
) -> int:
    """Free transfers going into `next_gw`, replaying (gw, transfers, chip) from GW1 the way
    the replay env does: GW1 is free, then the season's rollover and special events."""
    ft = 0
    by_gw = {gw: (n, chip) for gw, n, chip in history}
    for gw in range(1, next_gw):
        if rules.special_events.get("topup_free_transfers_gw") == gw:
            ft = rules.transfers.max_banked
        n, chip = by_gw.get(gw, (0, None))
        unlimited = gw == 1 or rules.special_events.get("unlimited_transfers_gw") == gw
        ft = next_free_transfers(rules, ft, n, chip, unlimited)
    if rules.special_events.get("topup_free_transfers_gw") == next_gw:
        ft = rules.transfers.max_banked
    return ft


def load_entry(engine: Engine, entry_id: int, rules: Rules, market: Market, next_gw: int) -> Entry:
    picks = _query(
        engine,
        """
        select gw, element_id, slot, is_captain, is_vice_captain, active_chip
        from staging.stg_fpl__entry_picks where entry_id = :e order by gw, slot
        """,
        entry_id,
    )
    if picks.is_empty():
        raise LookupError(f"no picks for team {entry_id}; run `diffpl.ingest league` first")
    last_gw = int(picks["gw"].max())  # type: ignore[arg-type]
    last = picks.filter(pl.col("gw") == last_gw)
    held = last
    if last["active_chip"][0] == "freehit":  # the squad reverts after a free hit
        held = picks.filter(pl.col("gw") == last_gw - 1)
    gws = _query(
        engine,
        "select gw, transfers, bank_tenths from staging.stg_fpl__entry_gameweeks "
        "where entry_id = :e order by gw",
        entry_id,
    )
    chips = _query(
        engine, "select gw, chip from staging.stg_fpl__entry_chips where entry_id = :e", entry_id
    )
    chip_at = {g: CHIP_NAMES.get(c) for g, c in zip(chips["gw"], chips["chip"], strict=True)}
    history = [(g, n, chip_at.get(g)) for g, n in zip(gws["gw"], gws["transfers"], strict=True)]
    bank = gws.filter(pl.col("gw") == last_gw)["bank_tenths"]
    ids = held["element_id"].to_list()
    squad = SquadState(
        picks=tuple(Pick(i, market.price[i]) for i in ids),
        bank=int(bank[0]) if len(bank) else 0,
        free_transfers=free_transfers(rules, history, next_gw),
        chips_used=tuple((c, g) for g, c in chip_at.items() if c is not None),
    )
    slots = last.sort("slot")["element_id"].to_list()
    captain = int(last.filter(pl.col("is_captain"))["element_id"][0])
    vice = int(last.filter(pl.col("is_vice_captain"))["element_id"][0])
    return Entry(entry_id, squad, Decision(tuple(slots[:11]), tuple(slots[11:]), captain, vice))


@dataclass(frozen=True)
class Recommendation:
    entry: Entry
    xp: dict[int, float]  # expected points this GW per player
    xp_horizon: dict[int, float]  # summed over the planning horizon, undiscounted
    options: list[Option]  # best EV first


def recommend(
    engine: Engine,
    rules: Rules,
    obs: Observation,
    entry_id: int,
    project: Projector,
    n_plans: int,
) -> Recommendation:
    """Up to `n_plans` plans with distinct squads for the deadline in `obs`, best EV first."""
    market = Market.at(obs.prices, obs.players)
    me = load_entry(engine, entry_id, rules, market, obs.gw)
    xp = project(obs)
    found = plans(rules, market, me.squad, xp, rules.special_events, n=n_plans)
    options = [
        Option(p, best_lineup(rules, list(p.squad), xp[obs.gw], market.position)) for p in found
    ]
    horizon: dict[int, float] = {}
    for per_gw in xp.values():
        for i, v in per_gw.items():
            horizon[i] = horizon.get(i, 0.0) + v
    return Recommendation(me, dict(xp[obs.gw]), horizon, options)
