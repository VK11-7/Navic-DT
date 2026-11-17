from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import DATA_PATH, O1_DIR, O2_DIR, SAMPLE_SECONDS, LOOKBACK, HORIZON
from src.data import load_data
from src.o1 import load_predictor, forecast
from src.o2 import load_model, predict, inject
from src.integrity import decide
from components.cesium_view import render_india_view
from components.railway_map import render_railway_gis

st.set_page_config(
    page_title="NavIC Railway Signal Integrity Digital Twin",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------- Theme / styling -----------------------------
st.markdown("""
<style>
    .block-container {padding-top: 1.35rem; padding-bottom: 2.2rem; max-width: 1600px;}
    [data-testid="stMetric"] {background: linear-gradient(135deg, rgba(30,41,59,.72), rgba(15,23,42,.55));
      border: 1px solid rgba(148,163,184,.18); padding: 13px 16px; border-radius: 12px;}
    [data-testid="stMetricLabel"] p {font-size: .82rem;}
    .section-note {color: #9ca3af; font-size: .86rem;}
    .status-pill {padding: .35rem .7rem; border-radius: 999px; font-weight: 650; display: inline-block;}
    .stTabs [data-baseweb="tab"] {height: 46px;}
    div[data-testid="stAlert"] {border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

STATION_COORDS = {
    "IISC00IND": {"lat": 13.021, "lon": 77.570, "label": "IISC · Bengaluru"},
    "LCK400IND": {"lat": 26.846, "lon": 80.946, "label": "LCK4 · Lucknow"},
    "JDPR00IND": {"lat": 26.238, "lon": 73.024, "label": "JDPR · Jodhpur"},
}
CLASS_NAMES = ["Genuine", "Multipath", "Spoofing"]
CLASS_COLORS = {"Genuine": "#22c55e", "Multipath": "#f59e0b", "Spoofing": "#ef4444"}

# ------------------------------- Load assets -------------------------------
@st.cache_data(show_spinner="Loading the processed RINEX dataset…")
def get_data(path_string: str):
    return load_data(Path(path_string))

@st.cache_resource(show_spinner="Loading trained DeepAR and LightGBM models…")
def get_models(o1_path: str, o2_path: str):
    return load_predictor(Path(o1_path)), load_model(Path(o2_path))


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def fmt_num(x, digits=3):
    try:
        return f"{float(x):,.{digits}f}"
    except Exception:
        return "—"



def make_scenario_frame(
    df: pd.DataFrame,
    station: str,
    sv: str,
    scenario: str,
    seed: int = 17
):
    """
    Create a temporary scenario-specific observation stream.

    Genuine:
        Original observations.

    Multipath:
        Uses the same Multipath injection equations as O2 training.

    Spoofing:
        Uses the same Spoofing injection equations as O2 training.

    The source dataframe is never modified.
    """

    if scenario == "Genuine":
        return df

    class_mapping = {
        "Multipath": 1,
        "Spoofing": 2
    }

    if scenario not in class_mapping:
        raise ValueError(
            f"Unsupported O2 scenario: {scenario}"
        )

    class_id = class_mapping[scenario]

    out = df.copy()

    mask = (
        (out.station.astype(str) == str(station)) &
        (out.sv.astype(str) == str(sv))
    )

    selected = (
        out.loc[mask]
        .sort_values("time")
        .tail(200)
        .copy()
    )

    if len(selected) < 50:
        raise ValueError(
            "At least 50 observations are required for scenario testing."
        )

    # Use the same deterministic random seed for reproducible tests.
    rng = np.random.default_rng(seed)

    # Apply the shared O2 injection function.
    modified = inject(
        selected,
        rng,
        class_id,
        placement="latest"
    )

    # Copy only the modified signal observables back into
    # the temporary dataframe.
    columns_to_update = [
        "C5A",
        "L5A",
        "S5A",
        "doppler_proxy_hz"
    ]

    for col in columns_to_update:

        if col in modified.columns:
            if col not in out.columns:
                out[col] = np.nan

            out.loc[modified.index, col] = modified[col]

    return out


def build_forecast_figure(history: pd.DataFrame, forecast_result: dict):
    hist = history.tail(120).copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.time, y=hist.sigma_phi_proxy, mode="lines", name="Observed σφ proxy",
                             line=dict(color="#60a5fa", width=1.8)))
    future_times = pd.date_range(hist.time.iloc[-1] + pd.Timedelta(seconds=SAMPLE_SECONDS),
                                 periods=HORIZON, freq=f"{SAMPLE_SECONDS}s")
    vals = np.asarray(forecast_result["series"], dtype=float)
    fig.add_trace(go.Scatter(x=future_times, y=vals, mode="lines+markers", name="DeepAR forecast",
                             line=dict(color="#f59e0b", width=2.2, dash="dash"), marker=dict(size=5)))
    fig.add_vline(x=hist.time.iloc[-1], line_dash="dot", line_color="#94a3b8")
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=25, b=10),
                      legend=dict(orientation="h", y=1.12), xaxis_title="Time", yaxis_title="σφ proxy",
                      template="plotly_dark", hovermode="x unified")
    return fig


def probability_figure(probabilities: dict):
    vals = [float(probabilities.get(c, 0.0)) for c in CLASS_NAMES]
    fig = go.Figure(go.Bar(x=CLASS_NAMES, y=vals, marker_color=[CLASS_COLORS[c] for c in CLASS_NAMES],
                           text=[f"{v:.1%}" for v in vals], textposition="outside"))
    fig.update_yaxes(range=[0, 1.12], tickformat=".0%", title="Predicted probability")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), template="plotly_dark",
                      showlegend=False)
    return fig


def severity_label(value: float):
    # Display-only bands; these are not universal GNSS scintillation standards.
    if value >= 0.5:
        return "Elevated proxy", "🟠"
    return "Lower proxy", "🟢"

# --------------------------------- Header -----------------------------------
st.title("🛰️ NavIC Railway Corridor — AI Signal Integrity Digital Twin")
st.caption("Integrated O1 DeepAR scintillation-proxy forecasting + O2 LightGBM multi-class signal-threat classification")

if not (O1_DIR / "predictor" / "gluonts-config.json").exists():
    st.error("DeepAR predictor is missing. Run `python scripts/train_models.py` first.")
    st.stop()
if not (O2_DIR / "lightgbm_classifier.joblib").exists():
    st.error("LightGBM model is missing. Run `python scripts/train_models.py` first.")
    st.stop()

try:
    df = get_data(str(DATA_PATH))
    deepar, (lightgbm_model, o2_features, o2_medians) = get_models(str(O1_DIR), str(O2_DIR))
except Exception as exc:
    st.exception(exc)
    st.stop()

# -------------------------------- Sidebar ----------------------------------
st.sidebar.header("Digital Twin Controls")
st.sidebar.caption("Select the receiver observation stream")
stations = sorted(df.station.astype(str).unique())
default_station = stations.index("JDPR00IND") if "JDPR00IND" in stations else 0
station = st.sidebar.selectbox("Reference station", stations, index=default_station)
svs = sorted(df.loc[df.station.astype(str) == station, "sv"].astype(str).unique())
sv = st.sidebar.selectbox("NavIC satellite", svs)
scenario = st.sidebar.selectbox("O2 scenario test", ["Observed data (no injection)", "Genuine", "Multipath", "Spoofing"],
                                help="Scenario tests apply temporary synthetic perturbations to a copy of the selected observation window. The source Parquet is never modified.")
run_clicked = st.sidebar.button("▶ Run integrity assessment", type="primary", use_container_width=True)
st.sidebar.divider()
st.sidebar.subheader("Display settings")
history_points = st.sidebar.slider("Signal history points", 60, 600, 240, 30)
show_all_stations = st.sidebar.checkbox("Show all reference stations on map", value=True)
st.sidebar.caption("Geographical layers load automatically from data/geography/. No frontend GeoJSON upload is required.")
st.sidebar.caption("Models are loaded from the saved artifacts. This dashboard does not retrain them.")

# Run once on click, retain the output while navigating tabs.
if run_clicked or "assessment" not in st.session_state or st.session_state.get("active_station") != station or st.session_state.get("active_sv") != sv or st.session_state.get("active_scenario") != scenario:
    try:
        with st.spinner("Running DeepAR forecast and LightGBM classification…"):
            base_history = df[(df.station.astype(str) == station) & (df.sv.astype(str) == sv)].sort_values("time").tail(max(history_points, 200)).copy()
            if len(base_history) < max(LOOKBACK, 25):
                raise ValueError(f"Only {len(base_history)} observations available; at least {max(LOOKBACK,25)} are required.")
            o1_result = forecast(deepar, df, station, sv)
            scenario_name = "Genuine" if scenario == "Observed data (no injection)" else scenario
            infer_df = make_scenario_frame(df, station, sv, scenario_name) if scenario_name != "Genuine" else df
            o2_result = predict(lightgbm_model, o2_features, o2_medians, infer_df, station, sv)
            decision = decide(o1_result, o2_result)
            st.session_state["assessment"] = {
                "o1": o1_result, "o2": o2_result, "decision": decision,
                "history": base_history, "station": station, "sv": sv,
                "scenario": scenario, "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
            st.session_state["active_station"] = station
            st.session_state["active_sv"] = sv
            st.session_state["active_scenario"] = scenario
            event = {"time": datetime.now().strftime("%H:%M:%S"), "station": station, "satellite": sv,
                     "scenario": scenario, "class": o2_result["class_name"], "confidence": o2_result["confidence"]}
            log = st.session_state.get("event_log", [])
            st.session_state["event_log"] = ([event] + log)[:30]
    except Exception as exc:
        st.error(f"Assessment could not be completed: {exc}")
        st.stop()

r = st.session_state["assessment"]
o1r, o2r, decision = r["o1"], r["o2"], r["decision"]

# Top-level status strip
forecast_status, forecast_icon = severity_label(o1r["forecast"])
threat_color = CLASS_COLORS.get(o2r["class_name"], "#94a3b8")
col1, col2, col3, col4 = st.columns(4)
col1.metric("10-minute σφ proxy forecast", fmt_num(o1r["forecast"], 4), help="DeepAR mean forecast at the 20th future 30-second step.")
col2.metric("O2 detected class", o2r["class_name"], help="LightGBM's highest-probability class.")
col3.metric("Classifier confidence", f"{o2r['confidence']:.2%}")
col4.metric("Integrity action", decision["action"].replace("_", " ").title())
st.markdown(f"**Selected stream:** `{station}` · `{sv}` &nbsp;&nbsp; **Scenario:** `{scenario}` &nbsp;&nbsp; **Proxy band:** {forecast_icon} {forecast_status}")
if scenario in ("Multipath", "Spoofing"):
    st.warning("Scenario laboratory is applying a synthetic perturbation to a temporary copy of the latest observations. This is a demonstration input, not a real detected attack.")

# --------------------------------- Tabs -------------------------------------
tabs = st.tabs(["Overview", "3D Digital Twin", "Signal Analytics", "Threat Intelligence", "Railway Integrity", "Data & Model Info", "Railway GIS Map"])

# Overview
with tabs[0]:
    st.subheader("System situation overview")
    a, b = st.columns([1.35, 1])
    with a:
        st.plotly_chart(probability_figure(o2r["probabilities"]), use_container_width=True, key="overview_probs")
    with b:
        st.markdown("#### Integrated assessment")
        st.markdown(f"**Detected threat:** {o2r['class_name']}")
        st.markdown(f"**Recommended demonstration action:** `{decision['action']}`")
        st.write(decision["note"])
        st.markdown("#### Model outputs")
        st.write(f"- DeepAR forecast horizon: **{HORIZON} steps / {HORIZON*SAMPLE_SECONDS//60} minutes**")
        st.write(f"- O2 classes: **Genuine, Multipath, Spoofing**")
        st.write(f"- Forecast context: **{LOOKBACK} observations / {LOOKBACK*SAMPLE_SECONDS//60} minutes**")
    st.markdown("#### Recent signal behaviour and forecast")
    st.plotly_chart(build_forecast_figure(r["history"], o1r), use_container_width=True, key="overview_forecast")
    st.caption("The forecast is for sigma_phi_proxy. Its magnitude is dataset/model-scale dependent and should not be interpreted as conventional S4 or a calibrated scintillation index without validation.")

# 3D digital twin
with tabs[1]:
    st.subheader("CesiumJS — Indian reference-station view")
    st.caption("Cesium ion-hosted hybrid satellite imagery with map labels. Reference stations are GNSS observation sites; satellite marker and signal path remain schematic until live NavIC ephemeris is integrated.")
    # Cesium ion token is read server-side from Streamlit secrets or environment.
    # It is passed to the browser component because CesiumJS requests imagery client-side.
    try:
        cesium_ion_token = st.secrets.get("CESIUM_ION_TOKEN", "")
    except Exception:
        cesium_ion_token = ""
    cesium_ion_token = cesium_ion_token or os.getenv("CESIUM_ION_TOKEN", "")
    if not cesium_ion_token:
        st.warning("Cesium ion is not configured yet. Add CESIUM_ION_TOKEN to .streamlit/secrets.toml; see .streamlit/secrets.toml.example.")
    map_info = render_india_view(
        station, sv, o2r["class_name"], o2r["confidence"], o1r["forecast"],
        show_all_stations,
        ion_token=cesium_ion_token,
        scenario=scenario,
    )
    st.markdown("#### Map legend")
    l1,l2,l3,l4 = st.columns(4)
    l1.markdown("🟢 **Genuine / reference station**")
    l2.markdown("🟠 **Multipath classification**")
    l3.markdown("🔴 **Spoofing classification**")
    l4.markdown("🔵 **Illustrative satellite**")
    if map_info["route_loaded"]:
        st.success(f"Loaded the locally configured railway corridor ({map_info['route_vertices']} vertices).")
    else:
        st.info("No project-specific railway corridor file is configured yet. The street basemap shows OpenStreetMap railway-network context. To highlight your selected corridor, place its verified GeoJSON once at data/geography/railway_corridor.geojson; it will load automatically on every run. No route has been fabricated.")

# Signal analytics
with tabs[2]:
    st.subheader("Observation-stream analytics")
    h = r["history"].tail(history_points).copy()
    h["time"] = pd.to_datetime(h.time)
    k1,k2,k3 = st.columns(3)
    k1.metric("Observations in view", f"{len(h):,}")
    k2.metric("Latest σφ proxy", fmt_num(h.sigma_phi_proxy.iloc[-1], 4))
    k3.metric("Latest S5A / C/N₀ field", fmt_num(h.S5A.iloc[-1], 2))
    st.plotly_chart(build_forecast_figure(h, o1r), use_container_width=True, key="signal_forecast")
    raw_cols = [c for c in ["S5A", "C5A", "L5A"] if c in h.columns]
    if raw_cols:
        fig = go.Figure()
        for col in raw_cols:
            fig.add_trace(go.Scatter(x=h.time, y=h[col], mode="lines", name=col))
        fig.update_layout(template="plotly_dark", height=340, margin=dict(l=10,r=10,t=20,b=10),
                          xaxis_title="Time", yaxis_title="Raw observable value", legend=dict(orientation="h",y=1.12))
        st.plotly_chart(fig, use_container_width=True, key="raw_observables")
    st.markdown("#### Recent observation records")
    st.dataframe(h[[c for c in ["time","station","sv","C5A","L5A","S5A","sigma_phi_proxy"] if c in h.columns]].tail(30),
                 use_container_width=True, hide_index=True)

# Threat intelligence
with tabs[3]:
    st.subheader("LightGBM threat classification")
    t1,t2 = st.columns([1,1.25])
    with t1:
        st.plotly_chart(probability_figure(o2r["probabilities"]), use_container_width=True, key="threat_probs")
    with t2:
        st.markdown("#### Classification interpretation")
        st.metric("Predicted class", o2r["class_name"])
        st.metric("Maximum class probability", f"{o2r['confidence']:.2%}")
        st.write("The model compares engineered code, carrier-phase, C/N₀ and carrier-phase-derived Doppler-proxy consistency features.")
        st.warning("O2 was trained and validated using synthetically injected multipath/spoofing episodes on RINEX-derived observations. This is not evidence of field-validated attack detection.")
    st.markdown("#### Session assessment history")
    events = st.session_state.get("event_log", [])
    if events:
        st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
    else:
        st.info("No assessment history yet.")
    st.markdown("#### Scenario laboratory")
    st.write("Choose Multipath or Spoofing in the sidebar and run the assessment to test the classifier with a controlled temporary perturbation. Compare its class probabilities with the observed-data run.")

# Railway integrity
with tabs[4]:
    st.subheader("Railway positioning integrity — decision-support prototype")
    st.warning("This prototype does not calculate certified HPL/VPL, ARAIM protection levels, HAL/VAL compliance, or Kavach safety decisions. Those require validated ranging-error models, satellite geometry, fault probabilities, integrity risk allocation and corridor-specific requirements.")
    q1,q2,q3 = st.columns(3)
    q1.metric("Signal threat state", o2r["class_name"])
    q2.metric("Forecast proxy", fmt_num(o1r["forecast"],4))
    q3.metric("Prototype action", decision["action"].replace("_"," "))
    st.markdown("#### Prototype decision logic")
    st.write("- **Spoofing with confidence ≥ 70%:** simulated signal exclusion recommendation.")
    st.write("- **Multipath with confidence ≥ 70%:** simulated signal down-weighting recommendation.")
    st.write("- **Elevated σφ proxy:** monitor and adapt selection recommendation.")
    st.write("- **Otherwise:** retain with monitoring.")
    st.code(json.dumps(decision, indent=2), language="json")
    st.markdown("#### Required inputs for operational HPL/VPL")
    st.write("Satellite ephemerides and geometry · pseudorange uncertainty model · fault-mode probabilities · integrity risk allocation · alert limits · validated ionospheric error mapping · receiver installation and railway corridor geometry.")

# Data and model info
with tabs[5]:
    st.subheader("Dataset and trained-model provenance")
    d1,d2,d3 = st.columns(3)
    d1.metric("Rows loaded", f"{len(df):,}")
    d2.metric("Reference stations", str(df.station.nunique()))
    d3.metric("NavIC satellite IDs", str(df.sv.nunique()))
    st.write(f"**Time coverage:** {df.time.min()} to {df.time.max()}")
    st.write(f"**Columns:** {len(df.columns)}")
    with st.expander("Station coverage", expanded=False):
        st.dataframe(df.groupby(df.station.astype(str)).agg(rows=("time","size"), satellites=("sv","nunique"), start=("time","min"), end=("time","max")).reset_index(names="station"), use_container_width=True, hide_index=True)
    o1_meta = read_json(O1_DIR / "metadata.json")
    o2_meta = read_json(O2_DIR / "training_report.json")
    m1,m2 = st.columns(2)
    with m1:
        st.markdown("#### O1 · DeepAR")
        st.write(f"- Target: `{o1_meta.get('target','sigma_phi_proxy')}`")
        st.write(f"- Context: {o1_meta.get('lookback_steps',LOOKBACK)} steps")
        st.write(f"- Horizon: {o1_meta.get('horizon_steps',HORIZON)} steps")
        st.write(f"- Sampling: {o1_meta.get('sampling_seconds',SAMPLE_SECONDS)} seconds")
        st.write(f"- Series used in training: {o1_meta.get('series_count','metadata unavailable')}")
        st.caption(o1_meta.get("selection_note", "DeepAR selection note not found."))
    with m2:
        st.markdown("#### O2 · LightGBM")
        st.write(f"- Features: {o2_meta.get('features',len(o2_features))}")
        st.write(f"- Training rows: {o2_meta.get('training_rows','metadata unavailable')}")
        st.write(f"- Validation rows: {o2_meta.get('validation_rows','metadata unavailable')}")
        if "validation_accuracy" in o2_meta:
            st.write(f"- Validation accuracy: {o2_meta['validation_accuracy']:.3%}")
        if "validation_macro_f1" in o2_meta:
            st.write(f"- Validation Macro-F1: {o2_meta['validation_macro_f1']:.3%}")
        st.caption(o2_meta.get("caveat", "Synthetic attack labels; interpret validation metrics accordingly."))
    st.info("D5A was not present in the checked observation files. The Doppler-related O2 feature is a carrier-phase-derived proxy, not a directly measured Doppler observable.")

st.divider()
st.caption("Research prototype for M.Tech project demonstration · Not a certified railway safety or GNSS integrity system")


# Independent 2D railway GIS map (Leaflet). This remains usable even if Cesium ion
# imagery or the CesiumJS CDN is unavailable.
with tabs[6]:
    st.subheader("Interactive railway GIS — street and satellite layers")
    st.caption("2D GIS view using Leaflet, OpenStreetMap and Esri imagery. The map shares the selected station, threat classification and GeoJSON corridor with the CesiumJS view.")
    gis_info = render_railway_gis(
        station=station,
        sv=sv,
        threat=o2r["class_name"],
        confidence=o2r["confidence"],
        forecast=o1r["forecast"],
        show_all=show_all_stations,
        scenario=r.get("scenario", scenario),
    )
    if gis_info["geojson_loaded"]:
        st.success(f"Loaded GeoJSON: {gis_info['feature_count']} features.")
    else:
        st.info("No project corridor GeoJSON found. The basemap and GNSS reference stations are still displayed. Add data/geography/railway_corridor.geojson to show your railway corridor.")
