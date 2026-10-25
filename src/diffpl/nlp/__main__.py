"""Score a team-news parser on the golden set (ADR-0013, ADR-0014).

uv run python -m diffpl.nlp eval [--parser rules|hybrid|<ollama model>] [--model M]
    [--show-errors] [--write-champion]

`--parser hybrid` reads with rules and falls back to `--model` (ADR-0015); `--parser qwen2.5:3b`
scores a local Ollama model on its own. `--write-champion` stores the current
scores as the bar every challenger must meet. A challenger prints its F1 change against the
champion; it replaces it only if it wins on `press_blind` without losing on `fpl`.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from diffpl.nlp.llm import HybridParser, OllamaParser
from diffpl.nlp.news import parse_news
from diffpl.nlp.score import CHAMPION, FIELDS, Parser, evaluate, load_golden, to_json


def eval_cmd(
    parser_name: str, model: str, show_errors: bool, write_champion: bool, save: str | None
) -> None:
    items = load_golden()
    hybrid: HybridParser | None = None
    llm: OllamaParser | None
    parse: Parser
    if parser_name == "rules":
        llm, parse = None, parse_news
    elif parser_name == "hybrid":
        llm = OllamaParser(model, strict_quote=True)
        hybrid = HybridParser(llm)
        parse = hybrid
    else:
        llm = OllamaParser(parser_name)
        parse = llm
    scores, wrong = evaluate(items, parse)
    champion = json.loads(CHAMPION.read_text(encoding="utf-8")) if CHAMPION.exists() else {}
    print(f"parser: {parser_name}")
    print(f"{len(items)} items, {len(wrong)} with at least one wrong field")
    for split, fields in scores.items():
        print(f"\n{split}")
        print(f"  {'field':<15}{'precision':>10}{'recall':>8}{'F1':>8}{'n':>5}")
        for f in FIELDS:
            s = fields[f]
            bar = champion.get(split, {}).get(f)
            delta = f"{s.f1 - bar['f1']:+.3f}" if bar and llm else ""
            print(f"  {f:<15}{s.precision:>10.3f}{s.recall:>8.3f}{s.f1:>8.3f}{s.n:>5}  {delta}")
    if hybrid:
        print(f"\nrules read {hybrid.rule_reads} items, the model {hybrid.model_reads}")
    if llm:
        st = llm.stats
        mean = sum(st.seconds) / len(st.seconds) if st.seconds else 0.0
        print(
            f"\n{st.calls} calls, {st.failures} failed, mean {mean:.2f}s, "
            f"{st.prompt_tokens} prompt and {st.output_tokens} output tokens, local, no API cost"
        )
    if show_errors:
        print()
        for it, pred in wrong:
            diff = {f: (it.gold[f], pred[f]) for f in FIELDS if it.gold[f] != pred[f]}
            print(f"#{it.id} [{it.split}] {it.text!r}\n    gold, predicted: {diff}")
    if write_champion:
        CHAMPION.write_text(to_json(scores) + "\n", encoding="utf-8")
        print(f"\nwrote {CHAMPION}")
    if save:
        Path(save).write_text(to_json(scores) + "\n", encoding="utf-8")
        print(f"\nwrote {save}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.nlp")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("eval", help="score the parser on the golden set")
    ev.add_argument(
        "--parser", default="rules", help="rules, hybrid, or an Ollama model name on its own"
    )
    ev.add_argument("--model", default="qwen2.5:3b", help="model the hybrid falls back to")
    ev.add_argument("--show-errors", action="store_true")
    ev.add_argument("--write-champion", action="store_true")
    ev.add_argument("--save", help="write these scores as JSON to this path")
    args = parser.parse_args(argv)
    if args.cmd == "eval":
        eval_cmd(args.parser, args.model, args.show_errors, args.write_champion, args.save)


if __name__ == "__main__":
    main()
