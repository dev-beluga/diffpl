"""Rules engine: validate and apply a decision, then score the gameweek.

Pure functions over plain data. The env (not the manager) calls these with the full season,
so scoring may use the GW's real match rows; managers never see them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace

import polars as pl

from diffpl.replay.types import ChipName, Decision, Pick, SquadState
from diffpl.rules import Position, Rules

FREE_TRANSFER_CHIPS: tuple[ChipName, ...] = ("wildcard", "freehit")


class InvalidDecision(ValueError):
    pass


@dataclass(frozen=True)
class Market:
    """Price, team and position of every player at one deadline."""

    price: Mapping[int, int]
    team: Mapping[int, str]
    position: Mapping[int, Position]

    @classmethod
    def at(cls, prices: pl.DataFrame, players: pl.DataFrame) -> Market:
        """Latest known row per player. `prices` must already be filtered to the deadline."""
        latest = (
            prices.sort("as_of", "element_id").group_by("element_id", maintain_order=True).last()
        )
        return cls(
            price=dict(zip(latest["element_id"], latest["price_tenths"], strict=True)),
            team=dict(zip(latest["element_id"], latest["team_name"], strict=True)),
            position=dict(zip(players["element_id"], players["position"], strict=True)),
        )


def selling_price(purchase: int, current: int, sell_on_fee: float) -> int:
    """FPL keeps a share of any rise, rounded down to 0.1m. Drops pass through in full."""
    if current <= purchase:
        return current
    return purchase + int((current - purchase) * sell_on_fee)


def chip_available(
    rules: Rules, used: tuple[tuple[ChipName, int], ...], chip: ChipName, gw: int
) -> bool:
    """A chip is playable if no chip was played this GW and an unused slot covers this GW."""
    if any(g == gw for _, g in used):
        return False
    free = [c for c in rules.chips if c.name == chip]
    for g in sorted(g for name, g in used if name == chip):
        slot = next((s for s in free if s.start_gw <= g <= s.end_gw), None)
        if slot is not None:
            free.remove(slot)
    return any(s.start_gw <= gw <= s.end_gw for s in free)


def valid_formation(rules: Rules, positions: list[Position]) -> bool:
    counts = Counter(positions)
    return all(
        limits.min_play <= counts[pos] <= limits.max_play
        for pos, limits in rules.squad.positions.items()
    )


def check_squad(
    rules: Rules, ids: list[int], market: Market, clubs: set[str] | None = None
) -> None:
    """Validate squad shape. `clubs` limits the club check to those clubs: a player moving club
    mid-season can leave a squad over the limit, which FPL allows until a transfer adds to it."""
    if len(ids) != rules.squad.size or len(set(ids)) != len(ids):
        raise InvalidDecision(f"squad must be {rules.squad.size} distinct players")
    missing = [i for i in ids if i not in market.price]
    if missing:
        raise InvalidDecision(f"players not available: {missing}")
    by_pos = Counter(market.position[i] for i in ids)
    for pos, limits in rules.squad.positions.items():
        if by_pos[pos] != limits.select:
            raise InvalidDecision(f"need {limits.select} {pos}, got {by_pos[pos]}")
    by_team = Counter(market.team[i] for i in ids)
    over = [
        t
        for t, n in by_team.items()
        if n > rules.squad.max_per_team and (clubs is None or t in clubs)
    ]
    if over:
        raise InvalidDecision(f"more than {rules.squad.max_per_team} players from {over}")


def check_lineup(
    rules: Rules, squad_ids: set[int], d: Decision, position: Mapping[int, Position]
) -> None:
    n_bench = rules.squad.size - rules.squad.starting
    if len(d.lineup) != rules.squad.starting or len(d.bench) != n_bench:
        raise InvalidDecision(f"need {rules.squad.starting} starters and {n_bench} on the bench")
    if set(d.lineup) | set(d.bench) != squad_ids or set(d.lineup) & set(d.bench):
        raise InvalidDecision("lineup and bench must partition the squad")
    if not valid_formation(rules, [position[i] for i in d.lineup]):
        raise InvalidDecision("invalid formation")
    if position[d.bench[0]] != "GKP":
        raise InvalidDecision("first bench slot must be the reserve goalkeeper")
    if d.captain == d.vice_captain or not {d.captain, d.vice_captain} <= set(d.lineup):
        raise InvalidDecision("captain and vice-captain must be two different starters")


@dataclass(frozen=True)
class Applied:
    state: SquadState  # the squad that plays this GW
    hits: int  # points deducted
    n_transfers: int


def apply_transfers(
    rules: Rules, state: SquadState, d: Decision, market: Market, gw: int, unlimited: bool
) -> Applied:
    """Apply chip and transfers. `unlimited` marks a GW where all transfers are free."""
    if d.chip is not None and not chip_available(rules, state.chips_used, d.chip, gw):
        raise InvalidDecision(f"chip {d.chip} not available in GW{gw}")
    outs = [t.out_id for t in d.transfers]
    ins = [t.in_id for t in d.transfers]
    if len(set(outs)) != len(outs) or len(set(ins)) != len(ins):
        raise InvalidDecision("duplicate transfer")
    picks = {p.element_id: p for p in state.picks}
    for t in d.transfers:
        if t.out_id not in picks:
            raise InvalidDecision(f"does not own {t.out_id}")
        if t.in_id in picks and t.in_id not in outs:
            raise InvalidDecision(f"already owns {t.in_id}")
        if t.in_id not in market.price:
            raise InvalidDecision(f"player {t.in_id} not available")
    bank = state.bank
    for t in d.transfers:
        out = picks.pop(t.out_id)
        bank += selling_price(
            out.purchase_price, market.price[t.out_id], rules.transfers.sell_on_fee
        )
    for t in d.transfers:
        bank -= market.price[t.in_id]
        picks[t.in_id] = Pick(t.in_id, market.price[t.in_id])
    if bank < 0:
        raise InvalidDecision(f"over budget by {-bank} tenths")
    check_squad(rules, list(picks), market, clubs={market.team[i] for i in ins})

    free = d.chip in FREE_TRANSFER_CHIPS or unlimited
    paid = 0 if free else max(0, len(d.transfers) - state.free_transfers)
    chips_used = (*state.chips_used, (d.chip, gw)) if d.chip else state.chips_used
    new_state = replace(state, picks=tuple(picks.values()), bank=bank, chips_used=chips_used)
    return Applied(new_state, paid * rules.transfers.hit_cost, len(d.transfers))


def next_free_transfers(
    rules: Rules, free_transfers: int, n_transfers: int, chip: ChipName | None, unlimited: bool
) -> int:
    """Free transfers carried into the next GW. Wildcard and free hit keep the bank."""
    if chip in FREE_TRANSFER_CHIPS or unlimited:
        left = free_transfers
    else:
        left = max(0, free_transfers - n_transfers)
    return min(rules.transfers.max_banked, left + rules.transfers.free_per_gw)


@dataclass(frozen=True)
class Scored:
    points: int  # before hits
    auto_subs: list[tuple[int, int]]  # (starter out, bench player in)
    armband: int | None  # who got the captain multiplier


def score_gw(
    rules: Rules,
    d: Decision,
    position: Mapping[int, Position],
    points: Mapping[int, int],
    minutes: Mapping[int, int],
) -> Scored:
    """Score a GW from per-player totals summed over the GW's matches (double GWs add up).

    A player missing from `minutes` had no match this GW and counts as not playing. Points
    are scored even with 0 minutes, since a benched player can still be booked.
    """
    played = {i for i, m in minutes.items() if m > 0}
    subs: list[tuple[int, int]] = []
    if d.chip == "bboost":
        scorers = [*d.lineup, *d.bench]
    else:
        scorers = list(d.lineup)
        bench = list(d.bench)
        for starter in d.lineup:
            if starter in played:
                continue
            for b in bench:
                if b not in played or (position[starter] == "GKP") != (position[b] == "GKP"):
                    continue
                trial = [x for x in scorers if x != starter] + [b]
                if valid_formation(rules, [position[x] for x in trial]):
                    scorers = trial
                    subs.append((starter, b))
                    bench.remove(b)
                    break
    total = sum(points.get(i, 0) for i in scorers)
    armband = next((c for c in (d.captain, d.vice_captain) if c in played), None)
    if armband is not None:
        total += (2 if d.chip == "3xc" else 1) * points.get(armband, 0)
    return Scored(total, subs, armband)
