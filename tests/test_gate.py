import numpy as np
import polars as pl

from diffpl.models import gate

SEASONS = ("2024-25",)


def scores(rps: np.ndarray) -> pl.DataFrame:
    n = len(rps)
    return pl.DataFrame(
        {"season": "2024-25", "gw": np.arange(n) % 38 + 1, "element_id": np.arange(n), "rps": rps}
    )


def metrics(rps: float, ece: float = 0.01, cov: float = 0.0, replay: float = 2000) -> dict:
    m: dict[str, float] = {"replay.2024-25.total_points": replay}
    for pos in gate.POSITIONS:
        m[f"model.{pos}.rps"] = rps
        for e in gate.EVENTS:
            m[f"model.{pos}.ece_{e}"] = ece
        for level in gate.LEVELS:
            m[f"model.{pos}.coverage{level}"] = level / 100 + cov
    return m


def test_better_challenger_passes() -> None:
    rng = np.random.default_rng(0)
    base = rng.random(4000) + 1
    d = gate.decide(scores(base), scores(base - 0.05), metrics(1.0), metrics(0.95), SEASONS, seed=0)
    assert d.passed, d.reasons


def test_noise_level_gain_fails_the_bootstrap() -> None:
    rng = np.random.default_rng(0)
    base = rng.random(4000) + 1
    noisy = base + rng.normal(0, 0.5, 4000)
    _, lo, hi = gate.paired_bootstrap(scores(base), scores(noisy), seed=0)
    assert lo < 0 < hi
    d = gate.decide(scores(base), scores(noisy), metrics(1.0), metrics(1.0), SEASONS, seed=0)
    assert not d.passed


def test_guards_block_miscalibrated_or_worse_replay_challenger() -> None:
    base = np.full(4000, 1.0)
    better = scores(base - 0.05)
    for bad in (metrics(0.95, ece=0.05), metrics(0.95, cov=0.05), metrics(0.95, replay=1950)):
        d = gate.decide(scores(base), better, metrics(1.0), bad, SEASONS, seed=0)
        assert not d.passed
        assert any(r.startswith("FAIL") for r in d.reasons)
