"""Challenger B (ADR-0008): team goals first, then split among players.

At each deadline, from data in the `Observation` (plus the whole previous season):
1. Team goals: Poisson, log rate = mu + home + attack[team] - defence[opponent], fitted with
   NumPyro SVI. Posterior draws carry parameter uncertainty into the simulation.
2. Player shares: each player's share of team goals and of team assists while on the pitch.
   Gamma-Poisson posterior mean, with a prior per position and price band.
3. Minutes: class 0, 1-59 or 60+, Dirichlet-multinomial on recent matches (decayed), prior per
   position and price band.
4. Simulation per fixture: sample both teams' goals, give each goal to a scorer and an assister
   in proportion to share times time on the pitch (an "other" slot covers the rest). Clean
   sheets and goals conceded come from the opponent's simulated goals. Points from
   `diffpl.scoring`. Double GWs sum their fixtures.
5. Residual points (bonus, cards, saves, penalties, DefCon) are sampled from the training
   distribution of actual minus modelled points, by position, minutes class and whether the
   player scored or assisted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

from diffpl.models.two_part import N_BINS, minutes_class
from diffpl.replay.data import Observation, SeasonData
from diffpl.rules import POSITIONS, Rules
from diffpl.scoring import MatchStats, player_points

CLASS_MINUTES = (0, 30, 90)  # representative minutes per minutes class
PITCH_SHARE = np.array([0.0, 1 / 3, 1.0])  # share of the match on the pitch per class
MAX_EVENTS = 6  # goals, assists and goals conceded are clipped here for the points table
N_BANDS = 4  # price quartiles within position
SHARE_PRIOR = 10.0  # prior strength in team goals of pseudo-exposure
MINUTES_PRIOR = 5.0  # prior strength in pseudo-matches
DECAY = 0.85  # minutes weight per match back in time
PREV_SEASON_WEIGHT = 0.5  # team model weight of last season's results
N_SIMS = 2000
N_DRAWS = 200  # posterior draws of team strengths
SVI_STEPS = 1500
MAX_TEAMS = 48  # padded sizes keep one compiled SVI program
MAX_MATCHES = 1200
RESIDUAL_SAMPLE = 5000


def base_points(rules: Rules) -> dict[str, np.ndarray]:
    """Points from minutes, goals, assists and goals conceded, via `player_points`.

    Indexed [minutes class, goals, assists, goals conceded] per position.
    """
    out: dict[str, np.ndarray] = {}
    n = MAX_EVENTS + 1
    for pos in POSITIONS:
        t = np.zeros((3, n, n, n), dtype=np.int64)
        for c, minutes in enumerate(CLASS_MINUTES):
            for g in range(n):
                for a in range(n):
                    for gc in range(n):
                        stats = MatchStats(
                            minutes=minutes,
                            goals_scored=g if minutes else 0,
                            assists=a if minutes else 0,
                            clean_sheets=int(minutes > 0 and gc == 0),
                            goals_conceded=gc if minutes else 0,
                        )
                        t[c, g, a, gc] = player_points(rules, pos, stats)
        out[pos] = t
    return out


def _team_goals(pm: pl.DataFrame, fixtures: pl.DataFrame) -> pl.DataFrame:
    """Player match rows with the team's goals in that match and exposure = goals x share on
    the pitch."""
    return (
        pm.join(fixtures.select("fixture_id", "home_score", "away_score"), on="fixture_id")
        .filter(pl.col("home_score").is_not_null())
        .with_columns(
            team_goals=pl.when(pl.col("was_home"))
            .then(pl.col("home_score"))
            .otherwise(pl.col("away_score"))
            .cast(pl.Float64),
            mclass=minutes_class(pl.col("minutes")),
        )
        .with_columns(exposure=pl.col("team_goals") * pl.col("minutes").clip(0, 90) / 90)
    )


def _market(prices: pl.DataFrame, players: pl.DataFrame) -> pl.DataFrame:
    """Latest team and price per player."""
    return (
        prices.sort("as_of", "element_id")
        .group_by("element_id", maintain_order=True)
        .last()
        .select("element_id", "team_name", "price_tenths")
        .join(players.select("element_id", "position"), on="element_id")
    )


def _band(df: pl.DataFrame, edges: dict[str, list[float]]) -> pl.DataFrame:
    bands = [
        int(np.searchsorted(edges[p], price, side="right")) if price is not None else 1
        for p, price in zip(df["position"], df["price_tenths"], strict=True)
    ]
    return df.with_columns(band=pl.Series(bands, dtype=pl.Int64))


def _team_model(n_teams: int):  # type: ignore[no-untyped-def]
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    def model(home, away, hg, ag, w):  # type: ignore[no-untyped-def]
        mu = numpyro.sample("mu", dist.Normal(0.3, 0.3))
        hadv = numpyro.sample("home", dist.Normal(0.2, 0.2))
        with numpyro.plate("teams", n_teams):
            att = numpyro.sample("att", dist.Normal(0.0, 0.3))
            dfn = numpyro.sample("dfn", dist.Normal(0.0, 0.3))
        lh = jnp.exp(mu + hadv + att[home] - dfn[away])
        la = jnp.exp(mu + att[away] - dfn[home])
        ll = dist.Poisson(lh).log_prob(hg) + dist.Poisson(la).log_prob(ag)
        numpyro.factor("ll", (w * ll).sum())

    return model


def fit_teams(matches: pl.DataFrame, seed: int) -> tuple[dict[str, int], dict[str, np.ndarray]]:
    """SVI fit on columns home, away (team names), hg, ag, weight. Returns the team index and
    N_DRAWS posterior draws of mu, home, att, dfn."""
    import jax
    from numpyro.infer import SVI, Trace_ELBO, autoguide
    from numpyro.optim import Adam

    names = sorted(set(matches["home"]) | set(matches["away"]))
    if len(names) > MAX_TEAMS or matches.height > MAX_MATCHES:
        raise ValueError(f"{len(names)} teams, {matches.height} matches exceed padded sizes")
    idx = {n: i for i, n in enumerate(names)}

    def pad(values: list[float] | list[int], dtype: type) -> np.ndarray:
        out: np.ndarray = np.zeros(MAX_MATCHES, dtype=dtype)
        out[: len(values)] = values
        return out

    args = (
        pad([idx[n] for n in matches["home"]], np.int32),
        pad([idx[n] for n in matches["away"]], np.int32),
        pad(matches["hg"].to_list(), np.float32),
        pad(matches["ag"].to_list(), np.float32),
        pad(matches["weight"].to_list(), np.float32),
    )
    model = _team_model(MAX_TEAMS)
    guide = autoguide.AutoNormal(model)
    svi = SVI(model, guide, Adam(0.05), Trace_ELBO())
    res = svi.run(jax.random.PRNGKey(seed), SVI_STEPS, *args, progress_bar=False)
    draws = guide.sample_posterior(
        jax.random.PRNGKey(seed + 1), res.params, *args, sample_shape=(N_DRAWS,)
    )
    return idx, {k: np.asarray(v) for k, v in draws.items() if k in ("mu", "home", "att", "dfn")}


def _results(data_fixtures: pl.DataFrame, teams: pl.DataFrame, weight: float) -> pl.DataFrame:
    name = dict(zip(teams["team_id"], teams["team_name"], strict=True))
    done = data_fixtures.filter(pl.col("home_score").is_not_null())
    return pl.DataFrame(
        {
            "home": [name[t] for t in done["home_team_id"]],
            "away": [name[t] for t in done["away_team_id"]],
            "hg": done["home_score"].cast(pl.Float64),
            "ag": done["away_score"].cast(pl.Float64),
            "weight": [weight] * done.height,
        },
        schema={
            "home": pl.String,
            "away": pl.String,
            "hg": pl.Float64,
            "ag": pl.Float64,
            "weight": pl.Float64,
        },
    )


@dataclass
class Prediction:
    element_id: np.ndarray
    dist: np.ndarray  # rows x N_BINS
    expected: np.ndarray
    p60: np.ndarray


@dataclass
class EventModel:
    seed: int = 42
    band_edges: dict[str, list[float]] = field(default_factory=dict)
    # (position, band) -> prior mean share of team goals / assists, minutes class probs
    goal_prior: dict[str, float] = field(default_factory=dict)
    assist_prior: dict[str, float] = field(default_factory=dict)
    minutes_prior: dict[str, list[float]] = field(default_factory=dict)
    # "position|class|involved" -> residual points sample
    residuals: dict[str, list[int]] = field(default_factory=dict)

    def fit(self, seasons: list[SeasonData], rules: list[Rules]) -> EventModel:
        """Priors and residuals from whole training seasons."""
        rng = np.random.default_rng(self.seed)
        rows = []
        for data, season_rules in zip(seasons, rules, strict=True):
            table = base_points(season_rules)
            pm = _team_goals(data.player_matches, data.fixtures)
            price = data.prices.group_by("element_id").agg(pl.col("price_tenths").mean())
            pm = pm.join(data.players.select("element_id", "position"), on="element_id").join(
                price, on="element_id", how="left"
            )
            mc = pm["mclass"].to_numpy()
            g, a, gc = (
                pm[c].fill_null(0).clip(0, MAX_EVENTS).to_numpy()
                for c in ("goals_scored", "assists", "goals_conceded")
            )
            pos = pm["position"].to_numpy()
            base = np.zeros(pm.height, dtype=np.int64)
            for p in POSITIONS:
                m = pos == p
                base[m] = table[p][mc[m], g[m], a[m], gc[m]]
            rows.append(pm.with_columns(residual=pm["total_points"] - pl.Series(base)))
        pm = pl.concat(rows, how="diagonal_relaxed")

        player = pm.group_by("element_id", "position", "price_tenths").agg(pl.len())
        self.band_edges = {
            p: np.quantile(
                player.filter(pl.col("position") == p)["price_tenths"].drop_nulls().to_numpy(),
                np.linspace(0, 1, N_BANDS + 1)[1:-1],
            ).tolist()
            for p in POSITIONS
        }
        pm = _band(pm, self.band_edges)
        groups = pm.group_by("position", "band").agg(
            (pl.col("goals_scored").sum() / pl.col("exposure").sum()).alias("g"),
            (pl.col("assists").sum() / pl.col("exposure").sum()).alias("a"),
            *[(pl.col("mclass") == c).mean().alias(f"m{c}") for c in range(3)],
        )
        for r in groups.iter_rows(named=True):
            key = f"{r['position']}|{r['band']}"
            self.goal_prior[key] = float(r["g"])
            self.assist_prior[key] = float(r["a"])
            self.minutes_prior[key] = [float(r[f"m{c}"]) for c in range(3)]
        pm = pm.with_columns(involved=((pl.col("goals_scored") + pl.col("assists")) > 0))
        for (pos, mc, inv), grp in pm.group_by("position", "mclass", "involved"):
            vals = grp["residual"].to_numpy()
            if len(vals) > RESIDUAL_SAMPLE:
                vals = rng.choice(vals, RESIDUAL_SAMPLE, replace=False)
            self.residuals[f"{pos}|{mc}|{int(inv)}"] = vals.astype(int).tolist()
        return self

    def player_params(self, obs: Observation) -> pl.DataFrame:
        """Per player at the deadline: team, position, goal and assist share, minutes probs."""
        market = _band(_market(obs.prices, obs.players), self.band_edges)
        pm = _team_goals(obs.player_matches, obs.fixtures)
        hist = pm.group_by("element_id").agg(
            pl.col("goals_scored").sum().alias("k_g"),
            pl.col("assists").sum().alias("k_a"),
            pl.col("exposure").sum().alias("n"),
        )
        recent = (
            obs.player_matches.sort("element_id", "kickoff_time", descending=[False, True])
            .with_columns(
                age=pl.int_range(pl.len()).over("element_id"),
                mclass=minutes_class(pl.col("minutes")),
            )
            .with_columns(w=pl.lit(DECAY) ** pl.col("age"))
            .group_by("element_id")
            .agg(*[(pl.col("w") * (pl.col("mclass") == c)).sum().alias(f"c{c}") for c in range(3)])
        )
        df = market.join(hist, on="element_id", how="left").join(
            recent, on="element_id", how="left"
        )
        df = df.with_columns(pl.col("k_g", "k_a", "n", "c0", "c1", "c2").fill_null(0.0))
        keys = [f"{p}|{b}" for p, b in zip(df["position"], df["band"], strict=True)]
        prior_g = np.array([self.goal_prior[k] for k in keys])
        prior_a = np.array([self.assist_prior[k] for k in keys])
        prior_m = np.array([self.minutes_prior[k] for k in keys])
        n = df["n"].to_numpy()
        counts = df.select("c0", "c1", "c2").to_numpy()
        probs = (prior_m * MINUTES_PRIOR + counts) / (MINUTES_PRIOR + counts.sum(axis=1))[:, None]
        return df.with_columns(
            share_g=(prior_g * SHARE_PRIOR + df["k_g"].to_numpy()) / (SHARE_PRIOR + n),
            share_a=(prior_a * SHARE_PRIOR + df["k_a"].to_numpy()) / (SHARE_PRIOR + n),
            p0=probs[:, 0],
            p1=probs[:, 1],
            p2=probs[:, 2],
        )

    def predict(self, obs: Observation, prev: SeasonData | None, rules: Rules) -> Prediction:
        rng = np.random.default_rng([self.seed, obs.gw])
        players = self.player_params(obs)
        results = [_results(obs.fixtures, obs.teams, 1.0)]
        if prev is not None:
            results.append(_results(prev.fixtures, prev.teams, PREV_SEASON_WEIGHT))
        idx, draws = fit_teams(pl.concat(results), self.seed + obs.gw)
        team_name = dict(zip(obs.teams["team_id"], obs.teams["team_name"], strict=True))
        table = base_points(rules)

        n = players.height
        points = np.zeros((N_SIMS, n))
        minutes = np.zeros((N_SIMS, n))
        row = {e: i for i, e in enumerate(players["element_id"])}
        d = np.arange(N_SIMS) % N_DRAWS

        def strength(team: str, key: str) -> np.ndarray:
            # Teams without results (promoted, no matches yet) sit at the prior mean, 0.
            return draws[key][:, idx[team]] if team in idx else np.zeros(N_DRAWS)

        for fx in obs.fixtures.filter(pl.col("gw") == obs.gw).iter_rows(named=True):
            h, a = team_name[fx["home_team_id"]], team_name[fx["away_team_id"]]
            lam_h = np.exp(draws["mu"] + draws["home"] + strength(h, "att") - strength(a, "dfn"))
            lam_a = np.exp(draws["mu"] + strength(a, "att") - strength(h, "dfn"))
            goals = {h: rng.poisson(lam_h[d]), a: rng.poisson(lam_a[d])}
            for team, opp in ((h, a), (a, h)):
                squad = players.filter(pl.col("team_name") == team)
                if squad.is_empty():
                    continue
                cols = np.array([row[e] for e in squad["element_id"]])
                mc = _sample_classes(squad.select("p0", "p1", "p2").to_numpy(), rng)
                pitch = PITCH_SHARE[mc]
                g = _allocate(goals[team], squad["share_g"].to_numpy() * pitch, rng)
                ast = _allocate(goals[team], squad["share_a"].to_numpy() * pitch, rng)
                gc = np.where(mc == 2, goals[opp][:, None], 0)
                involved = (g + ast) > 0
                for j, pos in enumerate(squad["position"]):
                    base = table[pos][
                        mc[:, j],
                        np.minimum(g[:, j], MAX_EVENTS),
                        np.minimum(ast[:, j], MAX_EVENTS),
                        np.minimum(gc[:, j], MAX_EVENTS),
                    ]
                    points[:, cols[j]] += base + self._residual(pos, mc[:, j], involved[:, j], rng)
                minutes[:, cols] += np.array(CLASS_MINUTES)[mc]

        bins = np.clip(points, 0, N_BINS - 1).astype(int)
        dist = np.stack([(bins == b).mean(axis=0) for b in range(N_BINS)], axis=1)
        return Prediction(
            element_id=players["element_id"].to_numpy(),
            dist=dist,
            expected=points.mean(axis=0),
            p60=(minutes >= 60).mean(axis=0),
        )

    def _residual(
        self, pos: str, mc: np.ndarray, involved: np.ndarray, rng: np.random.Generator
    ) -> np.ndarray:
        out = np.zeros(len(mc))
        for c in range(3):
            for inv in (0, 1):
                m = (mc == c) & (involved == inv)
                vals = self.residuals.get(f"{pos}|{c}|{inv}")
                if m.any() and vals:
                    out[m] = rng.choice(vals, m.sum())
        return out

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        fields = ("seed", "band_edges", "goal_prior", "assist_prior", "minutes_prior", "residuals")
        (path / "events.json").write_text(json.dumps({f: getattr(self, f) for f in fields}))

    @classmethod
    def load(cls, path: Path) -> EventModel:
        return cls(**json.loads((path / "events.json").read_text()))


def _sample_classes(probs: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """N_SIMS x players minutes classes from per-player class probabilities."""
    u = rng.random((N_SIMS, len(probs)))
    cdf = np.cumsum(probs, axis=1)
    return (u[:, :, None] > cdf[None, :, :2]).sum(axis=2)


def _allocate(goals: np.ndarray, weights: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Give each of `goals[s]` events to a player with prob. weights[s, j], else to "other".

    weights is sims x players; rows summing above 1 are normalized.
    """
    total = weights.sum(axis=1, keepdims=True)
    p = np.where(total > 1, weights / np.maximum(total, 1e-12), weights)
    cdf = np.cumsum(p, axis=1)
    out = np.zeros(weights.shape, dtype=np.int64)
    for k in range(int(goals.max(initial=0))):
        active = goals > k
        u = rng.random(len(goals))
        j = (u[:, None] > cdf).sum(axis=1)  # == players means "other"
        hit = active & (j < weights.shape[1])
        out[np.nonzero(hit)[0], j[hit]] += 1
    return out
