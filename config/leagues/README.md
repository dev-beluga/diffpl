# League rule sets

One file per mini-league, named `<league_id>.yaml`. A league with no file uses official FPL
scoring. Schema and step types: `src/diffpl/leagues/rules.py` (ADR-0005).

```yaml
league_id: 123456
name: Example league
versions:
  - effective_from_gw: 1
    overall: official            # or league_score
    steps:
      - {type: adjust_hits, mode: ignore_up_to, limit: 8}   # count_all | ignore_all | ignore_up_to | cap
      - {type: eligibility, max_hit: 12, excluded_chips: []}
      - {type: winner, tiebreak: [fewer_hits, higher_total, split]}
```

Changing rules mid-season: add a version with a later `effective_from_gw`. Earlier gameweeks
keep the rules they were played under.
