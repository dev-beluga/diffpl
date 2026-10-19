# ADR-0008: Challenger B, team goals split among players

Status: accepted
Date: 2026-10-19

## Context

ADR-0006 named a Bayesian event model as challenger B. The Phase 3 simulator needs outcomes
that are consistent across teammates and opponents (one goal has one scorer; a clean sheet
for a defender means the opponent scored 0). Three structures were considered.

## Decision

Team goals first, then split among players (`diffpl.models.events`). At each deadline:

1. Team goals: Poisson with log rate mu + home + attack[team] - defence[opponent], fitted with
   NumPyro SVI (AutoNormal) on the current season's results so far plus last season's at
   weight 0.5. Teams are matched across seasons by name. 200 posterior draws carry parameter
   uncertainty into the simulation. Inputs are padded to fixed sizes so JAX compiles once.
2. Player shares of team goals and assists while on the pitch: Gamma-Poisson posterior mean,
   prior per position and price quartile from the training seasons.
3. Minutes class (0, 1-59, 60+): Dirichlet-multinomial on the player's matches, decayed by
   0.85 per match, prior per position and price quartile.
4. 2000 simulations per fixture: sample both teams' goals, give each goal to a scorer and an
   assister in proportion to share times time on the pitch, with an "other" slot. Clean
   sheets and goals conceded come from the opponent's goals. Points come from
   `diffpl.scoring` through a lookup table. Double GWs sum.
5. Residual points (bonus, cards, saves, penalties, DefCon): sampled from the training
   distribution of actual minus modelled points, by position, minutes class and whether the
   player scored or assisted.

B runs through the same `models train` path as A (`--model events`) and is gated by ADR-0007.

## Alternatives considered

- Independent Poisson rates per player: simpler, but teammates' outcomes are independent, so
  two players can share one goal. Unusable for the Phase 3 simulator.
- Conjugate empirical Bayes only: fast, but the same independence problem, and no NumPyro.

## Consequences

- Only the team model uses NumPyro. Shares and minutes are conjugate, so each deadline costs
  about 2 seconds on CPU after the first compile.
- Player ids change between seasons in the source data, so player history starts empty each
  season. GW1 predictions rest on the position and price priors.
- Promoted teams have no results at GW1 and start at the prior mean strength.
- An assister can be the same player as the scorer in a simulation. This is rare and is not
  corrected.
- Bonus is not modelled from BPS. The residual keeps its link to goals and assists only
  through the "involved" split.
- `defensive_contribution` is not in the pipeline, so DefCon points live in the residual.
