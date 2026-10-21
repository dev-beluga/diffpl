"""This GW's plan for a real FPL team: EV plans ranked by P(beat a rival) (ADR-0011).

Teams come from the league ingest (`diffpl.ingest league`), read-only. Known gaps, all from
what the public API exposes:
- purchase prices are private, so selling prices are taken as current prices (sell-on gains
  are ignored);
- free transfers are rebuilt from the entry's transfer and chip history with the season rules.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import polars as pl
from sqlalchemy import Engine, text

from diffpl.leagues.rules import LeagueRules
from diffpl.optim.planner import Plan, Projector
from diffpl.optim.rival import Draws, RivalView, rank_plans
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
    p_beat: float | None


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


def recommend(
    engine: Engine,
    rules: Rules,
    league: LeagueRules,
    obs: Observation,
    entry_id: int,
    rival_id: int | None,
    project: Projector,
    simulate: Callable[[Observation], Draws],
    n_plans: int,
) -> list[Option]:
    """Plans for the deadline in `obs`, EV order, each with P(beat rival) when one is given."""
    market = Market.at(obs.prices, obs.players)
    me = load_entry(engine, entry_id, rules, market, obs.gw)
    rival = None
    if rival_id is not None:
        r = load_entry(engine, rival_id, rules, market, obs.gw)
        rival = RivalView(rival_id, r.last)
    xp = project(obs)
    found, probs = rank_plans(rules, league, obs, market, me.squad, xp, simulate, rival, n_plans)
    out = []
    for k, p in enumerate(found):
        d = best_lineup(rules, list(p.squad), xp[obs.gw], market.position)
        out.append(Option(p, d, probs[k] if probs else None))
    return out
