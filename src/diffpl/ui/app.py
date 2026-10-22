"""DiffPL local dashboard.

uv run streamlit run src/diffpl/ui/app.py
"""

from __future__ import annotations

import polars as pl
import streamlit as st
from sqlalchemy import Engine, create_engine

from diffpl.leagues.projection import METHOD, SEASON_GWS, overall_contributions, project
from diffpl.leagues.report import LeagueData, entry_rows, exposure, load_league, weekly_outcomes
from diffpl.leagues.rules import load_league_rules
from diffpl.replay.baselines import make_baseline
from diffpl.replay.data import load_season
from diffpl.replay.run import run_season
from diffpl.rules import load_rules
from diffpl.settings import get_settings

SEASONS = ("2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
BASELINES = ("template", "form", "fixtures")


@st.cache_resource
def engine() -> Engine:
    return create_engine(get_settings().database_url)


@st.cache_data(ttl=600, show_spinner="Loading league")
def league(league_id: int) -> LeagueData:
    return load_league(engine(), league_id)


@st.cache_data(show_spinner="Replaying season")
def replay(season: str, manager: str) -> pl.DataFrame:
    rules = load_rules(season)
    result = run_season(load_season(engine(), season), rules, make_baseline(manager, rules))
    return pl.DataFrame({"gw": [g.gw for g in result.gws], manager: [g.points for g in result.gws]})


def league_tab() -> None:
    c1, c2 = st.columns(2)
    league_id = c1.number_input("League id", min_value=1, step=1, value=314)
    entry_id = c2.number_input("Your team id (optional)", min_value=0, step=1, value=0)
    try:
        data = league(int(league_id))
    except LookupError as exc:
        st.warning(str(exc))
        return
    rules = load_league_rules(int(league_id))
    names = dict(zip(data.managers["entry_id"], data.managers["entry_name"], strict=True))
    st.caption(f"{data.managers.height} managers imported, up to GW{data.last_gw}")

    st.subheader("Standings")
    st.dataframe(
        data.managers.sort("rank").select(
            "rank",
            "entry_name",
            "total_points",
            (pl.col("value_tenths") / 10).alias("value"),
            (pl.col("bank_tenths") / 10).alias("bank"),
            "hit_cost",
            "transfers",
            "chips_used",
        ),
        hide_index=True,
    )

    outcomes, _ = weekly_outcomes(data, rules)
    st.subheader("Weekly winners (league rules)")
    with st.expander("Rule set in force"):
        st.json(rules.model_dump(mode="json"))
    st.dataframe(
        pl.DataFrame(
            {
                "gw": [o.gw for o in outcomes],
                "winner": [", ".join(names.get(e, str(e)) for e in o.winners) for o in outcomes],
                "why": [o.explanation for o in outcomes],
                "notes": [
                    " | ".join(
                        f"{names.get(s.entry_id, s.entry_id)}: {'; '.join(s.notes)}"
                        for s in o.scores
                        if s.notes
                    )
                    for o in outcomes
                ],
            }
        ),
        hide_index=True,
    )

    gws_left = SEASON_GWS - data.last_gw
    proj = project(overall_contributions(rules, outcomes, entry_rows(data)), gws_left)
    st.subheader("Projected final standings")
    st.caption(f"{gws_left} GWs left. Method: {METHOD}. Treat as a rough guide.")
    odds = pl.DataFrame(
        {
            "manager": [names.get(p.entry_id, str(p.entry_id)) for p in proj],
            "now": [p.current for p in proj],
            "win %": [round(100 * p.p_win, 1) for p in proj],
            "top 3 %": [round(100 * p.p_top3, 1) for p in proj],
        }
    ).sort("win %", descending=True)
    st.bar_chart(odds.to_pandas(), x="manager", y="win %", horizontal=True)
    st.dataframe(odds, hide_index=True)

    gw = data.last_gw
    st.subheader(f"League ownership, GW{gw}")
    top = (
        data.ownership.filter(pl.col("gw") == gw)
        .join(data.names, on="element_id", how="left")
        .sort("effective_ownership", descending=True)
        .select("web_name", "ownership", "effective_ownership", "captains")
        .head(15)
    )
    st.dataframe(top, hide_index=True)

    if entry_id:
        ex = exposure(data, int(entry_id), gw).select(
            "web_name", "mine", "ownership", "effective_ownership", "exposure"
        )
        if ex.filter(pl.col("mine") > 0).is_empty():
            st.info("That team id is not among the imported members of this league.")
            return
        a, b = st.columns(2)
        a.subheader("Your differentials")
        a.dataframe(ex.filter(pl.col("exposure") > 0).head(10), hide_index=True)
        b.subheader("Your threats")
        b.dataframe(ex.filter(pl.col("exposure") < 0).head(10), hide_index=True)


def replay_tab() -> None:
    season = st.selectbox("Season", SEASONS, index=3)
    chosen = st.multiselect("Managers", BASELINES, default=list(BASELINES))
    if not chosen:
        return
    frames = [replay(season, m) for m in chosen]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="gw")
    cumulative = df.with_columns([pl.col(m).cum_sum() for m in chosen])
    st.subheader(f"Cumulative points, {season}")
    st.line_chart(cumulative.to_pandas(), x="gw", y=chosen)
    st.dataframe(
        pl.DataFrame({"manager": chosen, "total": [int(df[m].sum()) for m in chosen]}),
        hide_index=True,
    )


POSITIONS = ("ALL", "GKP", "DEF", "MID", "FWD")
EVENTS = ("p60", "pts_ge1", "pts_ge2", "pts_ge6", "pts_ge10")


@st.cache_data(ttl=60, show_spinner="Reading MLflow")
def registry() -> pl.DataFrame:
    """One row per registered `projections` version with its run's headline metrics."""
    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    client = MlflowClient()
    aliases: dict[str, str] = {}
    for alias, version in client.get_registered_model("projections").aliases.items():
        aliases[version] = alias
    rows = []
    for v in client.search_model_versions("name='projections'"):
        run = client.get_run(v.run_id).data
        m = run.metrics
        ece = [m[k] for k in (f"model.ALL.ece_{e}" for e in EVENTS) if k in m]
        rows.append(
            {
                "version": int(v.version),
                "alias": aliases.get(v.version, ""),
                "model": run.params.get("model", ""),
                "gate": v.tags.get("gate", ""),
                "rps": m.get("model.ALL.rps", m.get("two_part.ALL.rps")),
                "worst_ece": max(ece) if ece else None,
                "cov50": m.get("model.ALL.coverage50"),
                "cov80": m.get("model.ALL.coverage80"),
                "replay_2024_25": m.get("replay.2024-25.total_points"),
                "replay_2025_26": m.get("replay.2025-26.total_points"),
                "run_id": v.run_id,
                "gate_reasons": v.tags.get("gate_reasons", ""),
            }
        )
    return pl.DataFrame(rows).sort("version", descending=True)


@st.cache_data(show_spinner="Downloading plot")
def artifact(run_id: str, path: str) -> str | None:
    import mlflow
    from mlflow.exceptions import MlflowException

    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    try:
        return str(mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=path))
    except (MlflowException, OSError):
        return None


@st.cache_data(ttl=60)
def sim_eval() -> pl.DataFrame:
    """Latest joint-simulation eval: team-total CRPS and coverage per joint model."""
    import mlflow

    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    from mlflow import MlflowClient

    client = MlflowClient()
    runs = client.search_runs(
        [e.experiment_id for e in client.search_experiments()],
        filter_string="attributes.run_name = 'sim_eval'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not runs:
        return pl.DataFrame()
    m = runs[0].data.metrics
    return pl.DataFrame(
        [
            {
                "joint model": method,
                "crps": m[f"sim.{method}.crps"],
                "cov50": m[f"sim.{method}.cov50"],
                "cov80": m[f"sim.{method}.cov80"],
            }
            for method in ("events", "hybrid", "independent")
        ]
    ).sort("crps")


def models_tab() -> None:
    try:
        reg = registry()
    except Exception as exc:  # MLflow down or no registered model yet
        st.warning(f"MLflow not reachable or empty: {exc}")
        return
    st.subheader("Model registry (test seasons 2024-25, 2025-26)")
    st.caption("RPS: lower is better. Coverage: calibrated means 0.50 and 0.80. Gate: ADR-0007.")
    st.dataframe(reg.drop("run_id", "gate_reasons"), hide_index=True)

    gated = reg.filter(pl.col("gate_reasons") != "")
    if gated.height:
        st.subheader("Promotion gate")
        v = st.selectbox("Version", gated["version"].to_list())
        reasons = gated.filter(pl.col("version") == v)["gate_reasons"][0]
        st.dataframe(
            pl.DataFrame(
                {
                    "result": [r.split(" ", 1)[0] for r in reasons.splitlines()],
                    "check": [r.split(" ", 1)[-1] for r in reasons.splitlines()],
                }
            ),
            hide_index=True,
        )

    st.subheader("Calibration")
    c1, c2 = st.columns(2)
    v = c1.selectbox("Model version", reg["version"].to_list(), key="calib_version")
    pos = c2.selectbox("Position", POSITIONS)
    run_id = reg.filter(pl.col("version") == v)["run_id"][0]
    path = artifact(run_id, f"calibration_{pos}.png")
    if path:
        st.image(path)
    else:
        st.info("No calibration plots for this run (logged before the calibration report).")

    sim = sim_eval()
    if sim.height:
        st.subheader("Joint simulation: team totals per GW")
        st.caption("Sample CRPS of each team's GW total (lower is better). ADR-0009.")
        st.dataframe(sim.with_columns(pl.col(pl.Float64).round(3)), hide_index=True)


def main() -> None:
    st.set_page_config(page_title="DiffPL", page_icon=":soccer:", layout="wide")
    st.title("DiffPL")
    st.caption("FPL decisions under uncertainty, with leakage-free backtests.")
    league_t, replay_t, models_t = st.tabs(["League", "Replay", "Models"])
    with league_t:
        league_tab()
    with replay_t:
        replay_tab()
    with models_t:
        models_tab()


main()
