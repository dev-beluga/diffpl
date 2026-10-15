"""Heuristic baseline managers: template, form and fixtures.

All three share one greedy policy and differ only in how they score players:
- build the best squad by score within budget, position and club limits;
- start the best valid 11, captain the top scorer;
- make at most one transfer per GW, only when it raises the squad score, never take a hit;
- play no chips.
They are floors to beat, not strong managers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import polars as pl

from diffpl.replay.data import Observation
from diffpl.replay.engine import Market, selling_price
from diffpl.replay.types import Decision, InitialSquad, ManagerView, Transfer
from diffpl.rules import Position, Rules

Scores = Mapping[int, float]
FORM_WINDOW = 4


def ownership_scores(obs: Observation) -> dict[int, float]:
    latest = (
        obs.prices.sort("as_of", "element_id").group_by("element_id", maintain_order=True).last()
    )
    return dict(zip(latest["element_id"], latest["selected_by"].cast(pl.Float64), strict=True))


def price_scores(obs: Observation) -> dict[int, float]:
    latest = (
        obs.prices.sort("as_of", "element_id").group_by("element_id", maintain_order=True).last()
    )
    return dict(zip(latest["element_id"], latest["price_tenths"].cast(pl.Float64), strict=True))


def form_scores(obs: Observation) -> dict[int, float]:
    """Mean points over each player's last FORM_WINDOW matches. Price/10 before any match."""
    scores = {i: p / 100 for i, p in price_scores(obs).items()}
    if obs.player_matches.is_empty():
        return scores
    recent = (
        obs.player_matches.sort("kickoff_time", "element_id")
        .group_by("element_id", maintain_order=True)
        .agg(pl.col("total_points").tail(FORM_WINDOW).mean().alias("form"))
    )
    scores.update(zip(recent["element_id"], recent["form"], strict=True))
    return scores


def fixture_scores(obs: Observation) -> dict[int, float]:
    """Form times the next opponent's goals conceded per game so far, relative to average."""
    form = form_scores(obs)
    fx = obs.fixtures
    done = fx.filter(pl.col("home_score").is_not_null())
    if done.is_empty() or obs.teams.is_empty():
        return form
    conceded = (
        pl.concat(
            [
                done.select(
                    pl.col("home_team_id").alias("team_id"), pl.col("away_score").alias("ga")
                ),
                done.select(
                    pl.col("away_team_id").alias("team_id"), pl.col("home_score").alias("ga")
                ),
            ]
        )
        .group_by("team_id", maintain_order=True)
        .agg(pl.col("ga").mean())
    )
    avg = conceded["ga"].mean()
    if not isinstance(avg, float) or avg <= 0:
        return form
    ease = {t: g / avg for t, g in zip(conceded["team_id"], conceded["ga"], strict=True)}
    upcoming = fx.filter(pl.col("gw") == obs.gw)
    opp: dict[int, list[int]] = {}  # team_id -> opponents this GW (two in a double GW)
    for h, a in zip(upcoming["home_team_id"], upcoming["away_team_id"], strict=True):
        opp.setdefault(h, []).append(a)
        opp.setdefault(a, []).append(h)
    team_id = dict(zip(obs.teams["team_name"], obs.teams["team_id"], strict=True))
    latest = (
        obs.prices.sort("as_of", "element_id").group_by("element_id", maintain_order=True).last()
    )
    player_team = dict(zip(latest["element_id"], latest["team_name"], strict=True))
    out: dict[int, float] = {}
    for i, f in form.items():
        tid = team_id.get(player_team.get(i, ""))
        opponents = opp.get(tid, []) if tid is not None else []
        out[i] = f * sum(ease.get(o, 1.0) for o in opponents)  # blank GW scores 0
    return out


def best_lineup(
    rules: Rules, ids: list[int], scores: Scores, position: Mapping[int, Position]
) -> Decision:
    ranked = sorted(ids, key=lambda i: (-scores.get(i, 0.0), i))
    gks = [i for i in ranked if position[i] == "GKP"]
    lineup = [gks[0]]
    for pos, limits in rules.squad.positions.items():  # meet minimums first
        if pos != "GKP":
            lineup += [i for i in ranked if position[i] == pos][: limits.min_play]
    counts = Counter(position[i] for i in lineup)
    for i in ranked:
        if len(lineup) == rules.squad.starting:
            break
        pos = position[i]
        if i not in lineup and pos != "GKP" and counts[pos] < rules.squad.positions[pos].max_play:
            lineup.append(i)
            counts[pos] += 1
    bench_out = [i for i in ranked if i not in lineup and position[i] != "GKP"]
    bench = (gks[1], *bench_out)
    starters = sorted(lineup, key=lambda i: (-scores.get(i, 0.0), i))
    return Decision(tuple(lineup), bench, captain=starters[0], vice_captain=starters[1])


def build_squad(rules: Rules, scores: Scores, market: Market) -> list[int]:
    """Greedy by score, keeping enough budget to fill the remaining slots at minimum price."""
    need = {pos: lim.select for pos, lim in rules.squad.positions.items()}
    cheapest = {
        pos: sorted(market.price[i] for i in market.price if market.position.get(i) == pos)
        for pos in need
    }
    budget = rules.squad.budget_tenths
    teams: Counter[str] = Counter()
    squad: list[int] = []
    for i in sorted(market.price, key=lambda i: (-scores.get(i, 0.0), i)):
        pos = market.position.get(i)
        if pos is None or need[pos] == 0 or teams[market.team[i]] >= rules.squad.max_per_team:
            continue
        need[pos] -= 1
        reserve = sum(sum(cheapest[p][:n]) for p, n in need.items())
        if market.price[i] + reserve > budget:
            need[pos] += 1
            continue
        squad.append(i)
        budget -= market.price[i]
        teams[market.team[i]] += 1
        if len(squad) == rules.squad.size:
            break
    return squad


@dataclass
class GreedyManager:
    name: str
    rules: Rules
    score: Callable[[Observation], dict[int, float]]
    min_gain: float = 0.5

    def pick_squad(self, view: ManagerView) -> InitialSquad:
        market = Market.at(view.obs.prices, view.obs.players)
        scores = self.score(view.obs)
        squad = build_squad(self.rules, scores, market)
        return InitialSquad(tuple(squad), best_lineup(self.rules, squad, scores, market.position))

    def act(self, view: ManagerView) -> Decision:
        assert view.squad is not None
        market = Market.at(view.obs.prices, view.obs.players)
        scores = self.score(view.obs)
        owned = {p.element_id: p for p in view.squad.picks}
        transfer = (
            self._best_transfer(view, market, scores, owned) if view.squad.free_transfers else None
        )
        ids = list(owned)
        if transfer is not None:
            ids = [transfer.in_id if i == transfer.out_id else i for i in ids]
        d = best_lineup(self.rules, ids, scores, market.position)
        return Decision(
            d.lineup, d.bench, d.captain, d.vice_captain, (transfer,) if transfer else ()
        )

    def _best_transfer(
        self, view: ManagerView, market: Market, scores: Scores, owned: Mapping[int, object]
    ) -> Transfer | None:
        assert view.squad is not None
        teams = Counter(market.team.get(i, "") for i in owned)
        best: tuple[float, Transfer] | None = None
        for p in sorted(view.squad.picks, key=lambda p: p.element_id):
            out = p.element_id
            funds = view.squad.bank + selling_price(
                p.purchase_price,
                market.price.get(out, p.purchase_price),
                self.rules.transfers.sell_on_fee,
            )
            for cand, price in sorted(market.price.items()):
                if (
                    cand in owned
                    or price > funds
                    or market.position.get(cand) != market.position.get(out)
                ):
                    continue
                club = market.team[cand]
                if teams[club] - (club == market.team.get(out)) >= self.rules.squad.max_per_team:
                    continue
                gain = scores.get(cand, 0.0) - scores.get(out, 0.0)
                if gain > self.min_gain and (best is None or gain > best[0]):
                    best = (gain, Transfer(out, cand))
        return best[1] if best else None


def make_baseline(name: str, rules: Rules) -> GreedyManager:
    scorers = {"template": ownership_scores, "form": form_scores, "fixtures": fixture_scores}
    if name not in scorers:
        raise ValueError(f"unknown baseline {name!r}; choose from {sorted(scorers)}")
    return GreedyManager(name, rules, scorers[name])
