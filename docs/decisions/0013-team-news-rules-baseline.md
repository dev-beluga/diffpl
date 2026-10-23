# ADR-0013: Team news, rules baseline first

Status: accepted
Date: 2026-10-23

## Context

Phase 4 extracts availability from team news: status, chance of playing, injury type, return
date, with the source quote. CLAUDE.md asks for a hand-labeled golden set, precision, recall
and F1 per field, and a champion every challenger must beat. Options considered: A rules,
B a local small LLM, C an API LLM. Chosen: A first, with B and C compared on the same golden
set later.

## Decision

- `diffpl.nlp.news.parse_news(text, as_of)` is a pure function of text and `as_of`: a regex
  cascade (unavailable, suspended, stated chance, out, doubtful, available, injury words,
  else `unknown`). It returns the status, chance, injury type, return date, a return-unknown
  flag, the matched quote and `as_of`. Years for dates like "2 Jan" come from `as_of`, never
  the clock. News is data: the parser never acts on what the text says.
- `chance` follows FPL's `chance_of_playing_next_round`: 0 for injured, suspended and
  unavailable, the stated percent for doubtful, None otherwise.
- Golden set `evals/team_news/golden.jsonl`, 63 items in three splits:
  - `fpl` (32): real strings from the FPL `news` field. Status and chance come from the API's
    own `status` and `chance_of_playing_next_round`; injury type and return date are my drafts.
  - `press_dev` (16): synthetic press-conference lines written while writing the rules. Not an
    independent test.
  - `press_blind` (15): synthetic lines written without looking at the rules. The honest
    measure of free text.
- `python -m diffpl.nlp eval` prints per-split, per-field precision, recall and F1.
  `evals/team_news/champion.json` stores the bar; a pytest fails if any field's F1 drops below
  it, so CI blocks regressions.

## Results (rules-v1)

| Split       | status F1 | chance F1 | injury type F1 | return date F1 |
|-------------|-----------|-----------|----------------|----------------|
| fpl         | 1.000     | 1.000     | 1.000          | 1.000          |
| press_dev   | 1.000     | 1.000     | 1.000          | 1.000          |
| press_blind | 0.533     | 0.667     | 0.909          | 1.000          |

FPL's own news is templated, so rules read it exactly. Free text is where rules fail:
"75 percent chance", "tear" without an injury word, "not in the squad", "everyone is available".
That gap is what options B and C must close; they replace the champion only if they win on
`press_blind` without losing `fpl`.

## Limits

- All labels are drafts for the author to review; `press_*` items are synthetic because
  press-conference transcripts need a source whose terms allow use (not yet researched).
  The set is small: one wrong item moves `press_blind` by about 7 points.
- Only two bootstrap snapshots exist, so news cannot yet be backtested as a feature. The join
  to the replay env (news `as_of` before the GW deadline) and its leakage test come with the
  feature step.
- `news_added` (when FPL published the text) is not in staging; `as_of` is the fetch time.

## Consequences

- Real FPL news needs no model; an LLM earns its place only on free text.
- Prompt-injection tests exist for the parser now (`tests/test_news.py`) and become
  mandatory for B and C.
