"""Train and evaluate projection models (ADR-0006, ADR-0008).

uv run python -m diffpl.models train [--model two_part|events] [--no-mlflow]
uv run python -m diffpl.models replay
uv run python -m diffpl.models promote [--version N]

Train on 2021-22 and 2022-23, early-stop on 2023-24, report on 2024-25 and 2025-26.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import polars as pl
from sqlalchemy import Engine, create_engine

from diffpl.features.build import FEATURES, gw_features, season_table
from diffpl.models import calibration
from diffpl.models.evaluate import climatology, rps, summary
from diffpl.models.two_part import N_BINS, TwoPartModel, add_labels
from diffpl.replay.data import Observation, SeasonData, load_season
from diffpl.settings import get_settings

TRAIN = ("2021-22", "2022-23")
VALID = ("2023-24",)
TEST = ("2024-25", "2025-26")
REGISTERED = "projections"
KEYS = ["season", "gw", "element_id"]
log = logging.getLogger("diffpl.models")

Scorer = Callable[[Observation], dict[int, float]]


def dataset_version(df: pl.DataFrame) -> str:
    """Content hash of the feature table, logged with every run."""
    return hashlib.sha256(df.sort("season", "gw", "element_id").write_csv().encode()).hexdigest()[
        :12
    ]


def evaluate(
    dist: np.ndarray,
    expected: np.ndarray,
    p60: np.ndarray,
    train: pl.DataFrame,
    test: pl.DataFrame,
    seed: int,
) -> tuple[pl.DataFrame, dict[str, pl.DataFrame], pl.DataFrame]:
    """Metrics table, calibration tables and per-row RPS (for the promotion gate).

    `dist`, `expected` and `p60` are the model's predictions for the rows of `test`, in order.
    """
    train, test = add_labels(train), add_labels(test)
    pos = test["position"].to_numpy()
    obs = test["bin"].to_numpy()
    pts = test["points"].to_numpy().astype(float)
    clim = climatology(train["bin"].to_numpy(), train["position"].to_numpy(), pos, N_BINS)
    means = train.group_by("bin").agg(pl.col("points").mean())
    bin_values = np.arange(N_BINS, dtype=float)
    bin_values[means["bin"].to_numpy()] = means["points"].to_numpy()
    form = (
        test.select(
            pl.coalesce("points_last6", "points_season_pg", pl.lit(0.0))
            * (pl.col("n_fixtures") > 0)
        )
        .to_series()
        .to_numpy()
    )
    table = summary(
        pos,
        obs,
        pts,
        {
            "model": (dist, expected),
            "position_climatology": (clim, clim @ bin_values),
            "form_last6": (np.empty(0), form),
        },
    )
    calib = calibration.report(dist, obs, p60, (test["mclass"] == 2).to_numpy(), pos, seed=seed)
    scores = test.select(KEYS).with_columns(rps=rps(dist, obs))
    return table, calib, scores


def model_replay(name: str, score: Scorer, engine: Engine) -> dict[str, int]:
    """Total points of the model-driven manager per test season."""
    from diffpl.replay.baselines import GreedyManager
    from diffpl.replay.run import run_season
    from diffpl.rules import load_rules

    out = {}
    for season in TEST:
        data, rules = load_season(engine, season), load_rules(season)
        out[season] = run_season(data, rules, GreedyManager(name, rules, score)).total_points
    return out


def two_part_scorer(model: TwoPartModel) -> Scorer:
    """Expected points per player. Managers use the baselines' greedy policy
    (diffpl.replay.baselines), so a replay difference comes from the projections alone."""

    def score(obs: Observation) -> dict[int, float]:
        feats = gw_features(obs)
        exp = model.expected_points(model.predict_dist(feats))
        return dict(zip(feats["element_id"].to_list(), exp.tolist(), strict=True))

    return score


def two_part(
    data: dict[str, SeasonData],
    train: pl.DataFrame,
    valid: pl.DataFrame,
    test: pl.DataFrame,
    seed: int,
) -> tuple[TwoPartModel, np.ndarray, np.ndarray, np.ndarray, Scorer, dict[str, object]]:
    model = TwoPartModel(seed=seed).fit(train, valid)
    dist = model.predict_dist(test)
    params: dict[str, object] = {f"lgb_{k}": v for k, v in model.params.items()}
    return (
        model,
        dist,
        model.expected_points(dist),
        model.predict_minutes(test)[:, 2],
        two_part_scorer(model),
        params,
    )


def events(
    data: dict[str, SeasonData],
    train: pl.DataFrame,
    valid: pl.DataFrame,
    test: pl.DataFrame,
    seed: int,
) -> tuple[object, np.ndarray, np.ndarray, np.ndarray, Scorer, dict[str, object]]:
    """Fit priors on the training seasons, then predict every test deadline. Each deadline
    refits the team model once; eval and replay share the cached prediction."""
    from diffpl.models import events as ev
    from diffpl.rules import load_rules

    model = ev.EventModel(seed=seed).fit([data[s] for s in TRAIN], [load_rules(s) for s in TRAIN])
    cache: dict[tuple[str, int], ev.Prediction] = {}

    def predict(obs: Observation) -> ev.Prediction:
        key = (obs.season, obs.gw)
        if key not in cache:
            start = int(obs.season[:4]) - 1
            prev = data[f"{start}-{str(start + 1)[2:]}"]
            cache[key] = model.predict(obs, prev, load_rules(obs.season))
            log.info("events %s GW%d", obs.season, obs.gw)
        return cache[key]

    frames, dists, offset = [], [], 0
    for season in TEST:
        for gw in data[season].gameweeks:
            p = predict(data[season].observe(gw))
            n = len(p.element_id)
            frames.append(
                pl.DataFrame(
                    {
                        "season": season,
                        "gw": gw,
                        "element_id": p.element_id,
                        "expected": p.expected,
                        "p60": p.p60,
                        "row": np.arange(offset, offset + n),
                    }
                )
            )
            dists.append(p.dist)
            offset += n
    pred = pl.concat(frames).with_columns(
        pl.col("gw").cast(test["gw"].dtype), pl.col("element_id").cast(test["element_id"].dtype)
    )
    rows = test.select(KEYS).join(pred, on=KEYS, how="left", maintain_order="left")
    if rows["row"].null_count():
        raise ValueError(f"{rows['row'].null_count()} test rows have no event prediction")

    def score(obs: Observation) -> dict[int, float]:
        p = predict(obs)
        return dict(zip(p.element_id.tolist(), p.expected.tolist(), strict=True))

    params: dict[str, object] = {
        k.lower(): getattr(ev, k)
        for k in ("N_SIMS", "N_DRAWS", "SVI_STEPS", "SHARE_PRIOR", "MINUTES_PRIOR", "DECAY")
    }
    params["prev_season_weight"] = ev.PREV_SEASON_WEIGHT
    return (
        model,
        np.concatenate(dists)[rows["row"].to_numpy()],
        rows["expected"].to_numpy(),
        rows["p60"].to_numpy(),
        score,
        params,
    )


MODELS = {"two_part": two_part, "events": events}


def train_cmd(kind: str, use_mlflow: bool) -> None:
    engine = create_engine(get_settings().database_url)
    seed = get_settings().seed
    data = {s: load_season(engine, s) for s in (*TRAIN, *VALID, *TEST)}
    tables = {s: season_table(d) for s, d in data.items()}
    train = pl.concat([tables[s] for s in TRAIN])
    valid = pl.concat([tables[s] for s in VALID])
    test = pl.concat([tables[s] for s in TEST])
    version = dataset_version(pl.concat(list(tables.values())))
    model, dist, expected, p60, score, params = MODELS[kind](data, train, valid, test, seed)
    table, calib, scores = evaluate(dist, expected, p60, train, test, seed)

    pl.Config.set_tbl_rows(40).set_tbl_hide_dataframe_shape(True)
    print(f"{kind}; dataset {version}; train {TRAIN}, valid {VALID}, test {TEST}")
    print(table.with_columns(pl.col(pl.Float64).round(4)))
    print("\nCalibration error (ECE) by event, test seasons:")
    ece = calib["ece"].pivot("event", index="position", values="ece")
    print(ece.with_columns(pl.col(pl.Float64).round(4)))
    print("\nCentral interval coverage (calibrated == level):")
    cov = calib["coverage"].pivot("level", index="position", values="coverage")
    print(cov.with_columns(pl.col(pl.Float64).round(3)))

    if not use_mlflow:
        return
    import mlflow

    replay = model_replay(kind, score, engine)
    print(f"\nreplay total points: {replay}")
    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    mlflow.set_experiment("projections")
    with mlflow.start_run(run_name=kind) as run:
        mlflow.log_params(
            {
                "model": kind,
                "dataset_version": version,
                "train": ",".join(TRAIN),
                "valid": ",".join(VALID),
                "test": ",".join(TEST),
                "features": len(FEATURES),
                "seed": seed,
                **params,
            }
        )
        for r in table.iter_rows(named=True):
            for metric in ("rps", "log_loss", "mae"):
                if r.get(metric) is not None:
                    mlflow.log_metric(f"{r['model']}.{r['position']}.{metric}", r[metric])
        for r in calib["ece"].iter_rows(named=True):
            mlflow.log_metric(f"model.{r['position']}.ece_{r['event']}", r["ece"])
        for r in calib["coverage"].iter_rows(named=True):
            level = int(r["level"] * 100)
            mlflow.log_metric(f"model.{r['position']}.coverage{level}", r["coverage"])
        for season, pts in replay.items():
            mlflow.log_metric(f"replay.{season}.total_points", pts)
        with tempfile.TemporaryDirectory() as tmp:
            model.save(Path(tmp) / "model")  # type: ignore[attr-defined]
            scores.write_parquet(Path(tmp) / "scores.parquet")
            for name, t in calib.items():
                t.write_csv(Path(tmp) / f"calibration_{name}.csv")
            calibration.plot(calib, Path(tmp))
            table.write_csv(Path(tmp) / "metrics.csv")
            mlflow.log_artifacts(tmp)
    v = register(run.info.run_id)
    print(f"\nlogged to MLflow; registered {REGISTERED} v{v}")


def register(run_id: str) -> str:
    """New model version. The first becomes champion, later ones challenger."""
    from mlflow import MlflowClient
    from mlflow.exceptions import MlflowException

    client = MlflowClient()
    try:
        client.get_registered_model(REGISTERED)
    except MlflowException:
        client.create_registered_model(REGISTERED)
    source = f"{client.get_run(run_id).info.artifact_uri}/model"
    version = str(client.create_model_version(REGISTERED, source, run_id).version)
    try:
        client.get_model_version_by_alias(REGISTERED, "champion")
        alias = "challenger"
    except MlflowException:
        alias = "champion"
    client.set_registered_model_alias(REGISTERED, alias, version)
    print(f"{REGISTERED} v{version} is {alias}")
    return version


def promote_cmd(version: str | None) -> None:
    """Gate the challenger (or `version`) against the champion; move the alias if it passes."""
    import mlflow
    from mlflow import MlflowClient

    from diffpl.models.gate import decide

    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    client = MlflowClient()
    champ = client.get_model_version_by_alias(REGISTERED, "champion")
    chal = (
        client.get_model_version(REGISTERED, version)
        if version
        else client.get_model_version_by_alias(REGISTERED, "challenger")
    )
    if chal.version == champ.version:
        raise SystemExit(f"v{chal.version} is already champion")

    def load(run_id: str) -> tuple[pl.DataFrame, dict[str, float]]:
        path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="scores.parquet")
        return pl.read_parquet(path), client.get_run(run_id).data.metrics

    champ_scores, champ_metrics = load(champ.run_id)
    chal_scores, chal_metrics = load(chal.run_id)
    d = decide(champ_scores, chal_scores, champ_metrics, chal_metrics, TEST, get_settings().seed)
    print(f"challenger v{chal.version} vs champion v{champ.version}")
    print("\n".join(d.reasons))
    client.set_model_version_tag(
        REGISTERED, chal.version, "gate", "passed" if d.passed else "failed"
    )
    client.set_model_version_tag(REGISTERED, chal.version, "gate_vs", champ.version)
    client.set_model_version_tag(REGISTERED, chal.version, "gate_reasons", "\n".join(d.reasons))
    if d.passed:
        client.set_registered_model_alias(REGISTERED, "champion", chal.version)
        client.delete_registered_model_alias(REGISTERED, "challenger")
        print(f"promoted v{chal.version} to champion")
    else:
        print(f"v{chal.version} stays challenger")


def replay_cmd() -> None:
    """Replay the test seasons: two-part model manager vs the heuristic baselines."""
    from diffpl.replay.baselines import GreedyManager, make_baseline
    from diffpl.replay.run import run_season
    from diffpl.rules import load_rules

    engine = create_engine(get_settings().database_url)
    train = pl.concat([season_table(load_season(engine, s)) for s in TRAIN])
    valid = pl.concat([season_table(load_season(engine, s)) for s in VALID])
    score = two_part_scorer(TwoPartModel(seed=get_settings().seed).fit(train, valid))
    for season in TEST:
        data, rules = load_season(engine, season), load_rules(season)
        managers = [make_baseline(b, rules) for b in ("template", "form", "fixtures")]
        for m in [GreedyManager("two_part", rules, score), *managers]:
            r = run_season(data, rules, m).summary()
            print(
                f"{season}  {r['manager']:<9} {r['total_points']:>5} pts  "
                f"violations {r['violations']}"
            )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.models")
    sub = parser.add_subparsers(dest="cmd", required=True)
    tr = sub.add_parser("train", help="train a model and evaluate on test seasons")
    tr.add_argument("--model", choices=tuple(MODELS), default="two_part")
    tr.add_argument("--no-mlflow", action="store_true")
    sub.add_parser("replay", help="replay test seasons with the model as a manager")
    pr = sub.add_parser("promote", help="gate the challenger against the champion")
    pr.add_argument("--version", help="model version to gate (default: challenger alias)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.cmd == "train":
        train_cmd(args.model, use_mlflow=not args.no_mlflow)
    elif args.cmd == "replay":
        replay_cmd()
    elif args.cmd == "promote":
        promote_cmd(args.version)


if __name__ == "__main__":
    main()
