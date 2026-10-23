"""Score a team-news parser against the golden set: precision, recall and F1 per field.

A field value is "empty" when it is None or False. A prediction is a true positive when it is
non-empty and equals the gold value, a false positive when it is non-empty and differs, and
a false negative when the gold value is non-empty and the prediction differs. `status` is never
empty, so its precision and recall both equal accuracy.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from diffpl.nlp.news import News, parse_news

FIELDS = ("status", "chance", "injury_type", "return_date", "return_unknown")
ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "evals/team_news/golden.jsonl"
CHAMPION = ROOT / "evals/team_news/champion.json"

Parser = Callable[[str, datetime], News]


@dataclass(frozen=True)
class Item:
    id: int
    split: str
    as_of: datetime
    text: str
    gold: dict[str, object]


@dataclass(frozen=True)
class FieldScore:
    precision: float
    recall: float
    f1: float
    n: int  # items with a non-empty gold value


def load_golden(path: Path = GOLDEN) -> list[Item]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            items.append(
                Item(
                    r["id"],
                    r["split"],
                    datetime.fromisoformat(r["as_of"].replace("Z", "+00:00")),
                    r["text"],
                    r["gold"],
                )
            )
    return items


def predicted(news: News) -> dict[str, object]:
    return {
        "status": news.status,
        "chance": news.chance,
        "injury_type": news.injury_type,
        "return_date": news.return_date.isoformat() if news.return_date else None,
        "return_unknown": news.return_unknown,
    }


def _empty(v: object) -> bool:
    return v is None or v is False


def score_field(pairs: Iterable[tuple[object, object]]) -> FieldScore:
    """`pairs` are (gold, predicted) values of one field."""
    tp = fp = fn = n = 0
    for gold, pred in pairs:
        n += not _empty(gold)
        if not _empty(pred):
            tp += pred == gold
            fp += pred != gold
        if not _empty(gold) and pred != gold:
            fn += 1
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return FieldScore(round(p, 4), round(r, 4), round(f1, 4), n)


def evaluate(
    items: list[Item], parser: Parser = parse_news
) -> tuple[dict[str, dict[str, FieldScore]], list[tuple[Item, dict[str, object]]]]:
    """Per-split, per-field scores, and the items with at least one wrong field."""
    preds = [(it, predicted(parser(it.text, it.as_of))) for it in items]
    scores: dict[str, dict[str, FieldScore]] = {}
    for split in sorted({it.split for it in items}):
        rows = [(it, p) for it, p in preds if it.split == split]
        scores[split] = {f: score_field((it.gold[f], p[f]) for it, p in rows) for f in FIELDS}
    wrong = [(it, p) for it, p in preds if any(it.gold[f] != p[f] for f in FIELDS)]
    return scores, wrong


def to_json(scores: dict[str, dict[str, FieldScore]]) -> str:
    return json.dumps(
        {s: {f: asdict(v) for f, v in fs.items()} for s, fs in scores.items()}, indent=2
    )
