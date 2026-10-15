# ADR-0005: Mini-leagues define their own rules as composable steps

Status: accepted
Date: 2026-10-15

## Context

Managers compete in mini-leagues with house rules on top of FPL scoring, for example "a
manager may take hits up to -8 and still win the gameweek prize". Any league using DiffPL must
be able to define its own rules for gameweek points and the gameweek winner. Rule definitions
come from league admins, so they are untrusted input.

## Decision

- A league rule set is an ordered list of steps. Each step has a type from a fixed registry and
  validated parameters, for example
  `[{adjust_hits: {ignore_up_to: 8}}, {eligibility: {max_hit: 12}}, {winner: {tiebreak: [fewer_hits]}}]`.
- Steps transform a per-manager gameweek table (official points, hits, chips, picks) into a
  league score, an eligibility flag and a winner. Each step records what it changed, so a
  result can be explained ("X won GW12: 71 points after ignoring -8").
- Rule sets are versioned per league with an `effective_from_gw`. Changing rules never rewrites
  past gameweeks.
- Leagues and members are imported read-only from the public FPL API by league id. DiffPL never
  writes to FPL accounts.
- League stats (ownership, effective ownership, differentials, team value, chips, hits) do not
  depend on the rule set. Projected standings use the league's rule set.

## Alternatives considered

- Fixed settings form: simplest, but every new house rule needs code and a schema change.
- Formula language typed by admins: most flexible, but needs a sandboxed evaluator for
  untrusted input and is hard to explain.

## Consequences

- New rule types are small, tested additions to the step registry.
- Large public leagues need a member cap on import; the FPL API pages standings 50 at a time.
