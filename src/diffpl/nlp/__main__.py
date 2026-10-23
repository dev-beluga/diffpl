"""Score the team-news parser on the golden set (ADR-0013).

uv run python -m diffpl.nlp eval [--show-errors] [--write-champion]

`--write-champion` stores the current scores as the bar every challenger must meet.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from diffpl.nlp.score import CHAMPION, FIELDS, evaluate, load_golden, to_json


def eval_cmd(show_errors: bool, write_champion: bool) -> None:
    items = load_golden()
    scores, wrong = evaluate(items)
    print(f"{len(items)} items, {len(wrong)} with at least one wrong field")
    for split, fields in scores.items():
        print(f"\n{split}")
        print(f"  {'field':<15}{'precision':>10}{'recall':>8}{'F1':>8}{'n':>5}")
        for f in FIELDS:
            s = fields[f]
            print(f"  {f:<15}{s.precision:>10.3f}{s.recall:>8.3f}{s.f1:>8.3f}{s.n:>5}")
    if show_errors:
        print()
        for it, pred in wrong:
            diff = {f: (it.gold[f], pred[f]) for f in FIELDS if it.gold[f] != pred[f]}
            print(f"#{it.id} [{it.split}] {it.text!r}\n    gold, predicted: {diff}")
    if write_champion:
        CHAMPION.write_text(to_json(scores) + "\n", encoding="utf-8")
        print(f"\nwrote {CHAMPION}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.nlp")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("eval", help="score the parser on the golden set")
    ev.add_argument("--show-errors", action="store_true")
    ev.add_argument("--write-champion", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "eval":
        eval_cmd(args.show_errors, args.write_champion)


if __name__ == "__main__":
    main()
