"""Train and evaluate projection models (ADR-0006).

uv run python -m diffpl.models train [--no-mlflow]

Train on 2021-22 and 2022-23, early-stop on 2023-24, report on 2024-25 and 2025-26.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import tempfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import polars as pl
from sqlalchemy import create_engine

from diffpl.features.build import FEATURES, season_table
from diffpl.models import calibration
from diffpl.models.evaluate import climatology, summary
from diffpl.models.two_part import N_BINS, TwoPartModel, add_labels
from diffpl.replay.data import load_season
from diffpl.settings import get_settings

TRAIN = ("2021-22", "2022-23")
VALID = ("2023-24",)
TEST = ("2024-25", "2025-26")
log = logging.getLogger("diffpl.models")


def dataset_version(df: pl.DataFrame) -> str:
    """Content hash of the feature table, logged with every run."""
    return hashlib.sha256(df.sort("season", "gw", "element_id").write_csv().encode()).hexdigest()[
        :12
    ]


def evaluate(
    model: TwoPartModel, train: pl.DataFrame, test: pl.DataFrame
) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
    train, test = add_labels(train), add_labels(test)
    dist = model.predict_dist(test)
    pos = test["position"].to_numpy()
    obs = test["bin"].to_numpy()
    pts = test["points"].to_numpy().astype(float)
    clim = climatology(train["bin"].to_numpy(), train["position"].to_numpy(), pos, N_BINS)
    clim_exp = model.expected_points(clim)
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
            "two_part": (dist, model.expected_points(dist)),
            "position_climatology": (clim, clim_exp),
            "form_last6": (np.empty(0), form),
        },
    )
    calib = calibration.report(
        dist,
        obs,
        model.predict_minutes(test)[:, 2],
        (test["mclass"] == 2).to_numpy(),
        pos,
        seed=model.seed,
    )
    return table, calib


def train_cmd(use_mlflow: bool) -> None:
    engine = create_engine(get_settings().database_url)
    tables = {s: season_table(load_season(engine, s)) for s in (*TRAIN, *VALID, *TEST)}
    train = pl.concat([tables[s] for s in TRAIN])
    valid = pl.concat([tables[s] for s in VALID])
    test = pl.concat([tables[s] for s in TEST])
    version = dataset_version(pl.concat(list(tables.values())))
    model = TwoPartModel(seed=get_settings().seed).fit(train, valid)
    table, calib = evaluate(model, train, test)

    pl.Config.set_tbl_rows(40).set_tbl_hide_dataframe_shape(True)
    print(f"dataset {version}; train {TRAIN}, valid {VALID}, test {TEST}")
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

    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    mlflow.set_experiment("projections")
    with mlflow.start_run(run_name="two_part"):
        mlflow.log_params(
            {
                "model": "two_part",
                "dataset_version": version,
                "train": ",".join(TRAIN),
                "valid": ",".join(VALID),
                "test": ",".join(TEST),
                "features": len(FEATURES),
                "seed": model.seed,
                **{f"lgb_{k}": v for k, v in model.params.items()},
            }
        )
        for r in table.iter_rows(named=True):
            for metric in ("rps", "log_loss", "mae"):
                if r.get(metric) is not None:
                    mlflow.log_metric(f"{r['model']}.{r['position']}.{metric}", r[metric])
        for r in calib["ece"].iter_rows(named=True):
            mlflow.log_metric(f"two_part.{r['position']}.ece_{r['event']}", r["ece"])
        for r in calib["coverage"].iter_rows(named=True):
            level = int(r["level"] * 100)
            mlflow.log_metric(f"two_part.{r['position']}.coverage{level}", r["coverage"])
        with tempfile.TemporaryDirectory() as tmp:
            assert model.minutes_model is not None
            model.minutes_model.save_model(str(Path(tmp) / "minutes.txt"))
            for c, booster in model.points_models.items():
                booster.save_model(str(Path(tmp) / f"points_m{c}.txt"))
            for name, t in calib.items():
                t.write_csv(Path(tmp) / f"calibration_{name}.csv")
            calibration.plot(calib, Path(tmp))
            table.write_csv(Path(tmp) / "metrics.csv")
            mlflow.log_artifacts(tmp)
    print("\nlogged to MLflow experiment 'projections'")


def replay_cmd() -> None:
    """Replay the test seasons: model-driven manager vs the heuristic baselines."""
    from diffpl.models.manager import model_manager
    from diffpl.replay.baselines import make_baseline
    from diffpl.replay.run import run_season
    from diffpl.rules import load_rules

    engine = create_engine(get_settings().database_url)
    train = pl.concat([season_table(load_season(engine, s)) for s in TRAIN])
    valid = pl.concat([season_table(load_season(engine, s)) for s in VALID])
    model = TwoPartModel(seed=get_settings().seed).fit(train, valid)
    for season in TEST:
        data, rules = load_season(engine, season), load_rules(season)
        managers = [make_baseline(b, rules) for b in ("template", "form", "fixtures")]
        for m in [model_manager("two_part", model, rules), *managers]:
            r = run_season(data, rules, m).summary()
            print(
                f"{season}  {r['manager']:<9} {r['total_points']:>5} pts  "
                f"violations {r['violations']}"
            )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m diffpl.models")
    sub = parser.add_subparsers(dest="cmd", required=True)
    tr = sub.add_parser("train", help="train two-part model and evaluate on test seasons")
    tr.add_argument("--no-mlflow", action="store_true")
    sub.add_parser("replay", help="replay test seasons with the model as a manager")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.cmd == "train":
        train_cmd(use_mlflow=not args.no_mlflow)
    elif args.cmd == "replay":
        replay_cmd()


if __name__ == "__main__":
    main()
