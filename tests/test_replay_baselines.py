"""Baselines play legal seasons, and their decisions ignore the future (poisoned-future test)."""

from dataclasses import dataclass, field, replace

import polars as pl
import pytest
from test_replay_run import make_season

from diffpl.replay.baselines import make_baseline
from diffpl.replay.data import SeasonData
from diffpl.replay.run import run_season
from diffpl.replay.types import Decision, InitialSquad, Manager, ManagerView
from diffpl.rules import load_rules

RULES = load_rules("2025-26")


@dataclass
class Recorder:
    """Wraps a manager and records every decision it makes."""

    inner: Manager
    log: list[object] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.inner.name

    def pick_squad(self, view: ManagerView) -> InitialSquad:
        out = self.inner.pick_squad(view)
        self.log.append(out)
        return out

    def act(self, view: ManagerView) -> Decision:
        out = self.inner.act(view)
        self.log.append(out)
        return out


def varied_season() -> SeasonData:
    """The synthetic season with points that differ by player, so baselines make choices."""
    data = make_season()
    pm = data.player_matches.with_columns(
        ((pl.col("element_id") * 7 + pl.col("gw") * 3) % 11).alias("total_points")
    )
    return replace(data, player_matches=pm)


def poison_future(data: SeasonData, gw: int) -> SeasonData:
    """Rewrite every match at or after `gw` to an absurd haul."""
    pm = data.player_matches.with_columns(
        pl.when(pl.col("gw") >= gw).then(99).otherwise(pl.col("total_points")).alias("total_points")
    )
    fx = data.fixtures.with_columns(
        pl.when(pl.col("gw") >= gw).then(9).otherwise(pl.col("home_score")).alias("home_score")
    )
    return replace(data, player_matches=pm, fixtures=fx)


@pytest.mark.parametrize("name", ["template", "form", "fixtures"])
def test_baselines_play_without_violations(name: str) -> None:
    result = run_season(varied_season(), RULES, make_baseline(name, RULES))
    assert len(result.gws) == 3
    assert result.violations == []


@pytest.mark.parametrize("name", ["template", "form", "fixtures"])
@pytest.mark.parametrize("from_gw", [2, 3])
def test_poisoned_future_does_not_change_decisions(name: str, from_gw: int) -> None:
    clean, poisoned = Recorder(make_baseline(name, RULES)), Recorder(make_baseline(name, RULES))
    run_season(varied_season(), RULES, clean)
    run_season(poison_future(varied_season(), from_gw), RULES, poisoned)
    # Decisions up to and including from_gw were made before the poisoned matches happened.
    assert clean.log[:from_gw] == poisoned.log[:from_gw]
