"""Feature leakage tests (ADR-0006): features depend only on pre-deadline data."""

from dataclasses import replace

import polars as pl
from polars.testing import assert_frame_equal
from test_replay_baselines import poison_future, varied_season

from diffpl.features.build import FEATURES, gw_features, season_table
from diffpl.replay.data import SeasonData


def with_xg(data: SeasonData) -> SeasonData:
    pm = data.player_matches.with_columns(
        pl.lit(0.2).alias("expected_goals"),
        pl.lit(0.1).alias("expected_assists"),
        pl.lit(1).alias("starts"),
        pl.lit(0).alias("bonus"),
    )
    pr = data.prices.with_columns(
        pl.lit(10).alias("transfers_in"), pl.lit(4).alias("transfers_out")
    )
    return replace(data, player_matches=pm, prices=pr)


def test_every_feature_column_present() -> None:
    feats = gw_features(with_xg(varied_season()).observe(2))
    assert set(FEATURES) <= set(feats.columns)
    assert feats["games_played"].max() == 1


def test_gw1_has_no_form_but_has_market() -> None:
    feats = gw_features(with_xg(varied_season()).observe(1))
    assert feats["points_last3"].null_count() == feats.height
    assert feats["price_tenths"].null_count() == 0


def test_poisoned_future_leaves_features_unchanged() -> None:
    clean = with_xg(varied_season())
    for gw in (2, 3):
        poisoned = poison_future(clean, gw)
        assert_frame_equal(gw_features(clean.observe(gw)), gw_features(poisoned.observe(gw)))


def test_targets_are_the_gw_actuals() -> None:
    table = season_table(with_xg(varied_season()))
    row = table.filter((pl.col("gw") == 2) & (pl.col("element_id") == 1))
    assert row["points"].to_list() == [(1 * 7 + 2 * 3) % 11]
    assert row["minutes"].to_list() == [90]
