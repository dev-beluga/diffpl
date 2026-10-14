# Data sources

| Source | What we take | License / terms | Refresh | Raw table |
|---|---|---|---|---|
| FPL API (`fantasy.premierleague.com/api`) | `bootstrap-static/`, `fixtures/`, `element-summary/{id}/` | Public but unofficial and undocumented. No published license. Personal, non-commercial use; we cache and rate-limit (1 request per second, 1 hour cache). | Daily snapshot (Prefect, Phase 6) | `raw.fpl_api_responses` |
| vaastav/Fantasy-Premier-League | `gws/merged_gw.csv`, `fixtures.csv`, `teams.csv`, `players_raw.csv` per season, 2016-17 onward | MIT license (repo). Data originates from the FPL API. | On demand, pinned to a commit SHA | `raw.vaastav_rows` |

## Timestamps and leakage

- `fetched_at` is when the server answered. A cache hit keeps the original `fetched_at`.
- FPL API snapshots: `as_of = fetched_at`. A snapshot can only feed decisions for deadlines
  after it was taken.
- vaastav rows are reconstructed history. Staging derives `as_of` per row:
  `merged_gw.csv` rows become available after the fixture's `kickoff_time` plus match length,
  and only as of the next deadline for replay purposes.
- `players_raw.csv` is an end-of-season snapshot (final price, totals, news). Never use it for
  a gameweek inside its own season. It is useful only for player ids, names and positions.

## Known gaps

- 2016-17 and 2017-18 have no `fixtures.csv` or `teams.csv`; 2018-19 has no `teams.csv`.
  The loader skips them; staging must derive teams and fixtures from `merged_gw.csv`.
- Older seasons use `First_Last_id` style player names in `merged_gw.csv`.
- Advanced stats (xG, xA) appear in `merged_gw.csv` from 2022-23. No other xG source is used
  until its terms are checked.
- vaastav `fixtures.csv` difficulty ratings are end-of-season values, not point-in-time.
