"""Champion candidate A (ADR-0006): minutes classifier times points-given-minutes classifier.

P(points bin) = sum over minutes class c of P(c) * P(bin | c). Class 0 (did not play) uses
the training frequencies, since a benched player can still be booked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

from diffpl.features.build import FEATURES

# Points bins: <=0, 1, 2, ..., 14, 15+.
N_BINS = 16
MINUTES_CLASSES = 3  # 0, 1-59, 60+


def points_bin(points: pl.Expr) -> pl.Expr:
    return points.clip(0, N_BINS - 1).cast(pl.Int64)


def minutes_class(minutes: pl.Expr) -> pl.Expr:
    return pl.when(minutes <= 0).then(0).when(minutes < 60).then(1).otherwise(2).cast(pl.Int64)


def add_labels(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        points_bin(pl.col("points")).alias("bin"), minutes_class(pl.col("minutes")).alias("mclass")
    )


def matrix(df: pl.DataFrame) -> np.ndarray:
    return df.select([pl.col(c).cast(pl.Float64) for c in FEATURES]).to_numpy()


@dataclass
class TwoPartModel:
    seed: int = 42
    params: dict[str, object] = field(
        default_factory=lambda: {
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_data_in_leaf": 50,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.9,
            "bagging_freq": 1,
            "lambda_l2": 1.0,
            "verbose": -1,
        }
    )
    max_rounds: int = 1000
    minutes_model: lgb.Booster | None = None
    points_models: dict[int, lgb.Booster] = field(default_factory=dict)
    benched_dist: np.ndarray | None = None
    bin_values: np.ndarray | None = None  # mean points per bin, for expected points

    def _train(
        self, x: np.ndarray, y: np.ndarray, xv: np.ndarray, yv: np.ndarray, n_class: int
    ) -> lgb.Booster:
        params = {**self.params, "objective": "multiclass", "num_class": n_class, "seed": self.seed}
        return lgb.train(
            params,
            lgb.Dataset(x, y),
            num_boost_round=self.max_rounds,
            valid_sets=[lgb.Dataset(xv, yv)],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )

    def fit(self, train: pl.DataFrame, valid: pl.DataFrame) -> TwoPartModel:
        train, valid = add_labels(train), add_labels(valid)
        self.minutes_model = self._train(
            matrix(train),
            train["mclass"].to_numpy(),
            matrix(valid),
            valid["mclass"].to_numpy(),
            MINUTES_CLASSES,
        )
        for c in (1, 2):
            t, v = train.filter(pl.col("mclass") == c), valid.filter(pl.col("mclass") == c)
            self.points_models[c] = self._train(
                matrix(t), t["bin"].to_numpy(), matrix(v), v["bin"].to_numpy(), N_BINS
            )
        benched = train.filter(pl.col("mclass") == 0)["bin"].to_numpy()
        self.benched_dist = np.bincount(benched, minlength=N_BINS) / max(len(benched), 1)
        means = train.group_by("bin").agg(pl.col("points").mean()).sort("bin")
        values = np.arange(N_BINS, dtype=float)
        values[means["bin"].to_numpy()] = means["points"].to_numpy()
        self.bin_values = values
        return self

    def predict_dist(self, df: pl.DataFrame) -> np.ndarray:
        """Rows x N_BINS probabilities."""
        assert self.minutes_model is not None and self.benched_dist is not None
        x = matrix(df)
        pm = np.asarray(self.minutes_model.predict(x))
        out = pm[:, [0]] * self.benched_dist[None, :]
        for c in (1, 2):
            out += pm[:, [c]] * np.asarray(self.points_models[c].predict(x))
        return np.asarray(out / out.sum(axis=1, keepdims=True))

    def predict_minutes(self, df: pl.DataFrame) -> np.ndarray:
        assert self.minutes_model is not None
        return np.asarray(self.minutes_model.predict(matrix(df)))

    def expected_points(self, dist: np.ndarray) -> np.ndarray:
        assert self.bin_values is not None
        return np.asarray(dist @ self.bin_values)

    def save(self, path: Path) -> None:
        """Write boosters and fitted arrays to a directory (the MLflow `model` artifact)."""
        assert self.minutes_model is not None
        assert self.benched_dist is not None and self.bin_values is not None
        path.mkdir(parents=True, exist_ok=True)
        self.minutes_model.save_model(str(path / "minutes.txt"))
        for c, booster in self.points_models.items():
            booster.save_model(str(path / f"points_m{c}.txt"))
        np.save(path / "benched_dist.npy", self.benched_dist)
        np.save(path / "bin_values.npy", self.bin_values)
        (path / "meta.json").write_text(json.dumps({"seed": self.seed, "params": self.params}))

    @classmethod
    def load(cls, path: Path) -> TwoPartModel:
        meta = json.loads((path / "meta.json").read_text())
        return cls(
            seed=meta["seed"],
            params=meta["params"],
            minutes_model=lgb.Booster(model_file=str(path / "minutes.txt")),
            points_models={
                c: lgb.Booster(model_file=str(path / f"points_m{c}.txt")) for c in (1, 2)
            },
            benched_dist=np.load(path / "benched_dist.npy"),
            bin_values=np.load(path / "bin_values.npy"),
        )
