"""
Rolling-origin evaluation for the saved O1 DeepAR model.

Run from the project root:
    python scripts/evaluate_o1.py

This evaluates the existing model; it does not retrain O1 or O2.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from config import DATA_PATH, O1_DIR, SAMPLE_SECONDS, LOOKBACK, HORIZON
from src.data import ensure_data_file
from src.o1 import load_predictor, make_series_frame, _make_pandas_dataset


def metric_pack(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    valid = np.isfinite(actual) & np.isfinite(predicted)
    actual, predicted = actual[valid], predicted[valid]
    if len(actual) == 0:
        return {"n": 0, "rmse": None, "mae": None, "r2": None}
    return {
        "n": int(len(actual)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "mae": float(mean_absolute_error(actual, predicted)),
        "r2": float(r2_score(actual, predicted)) if len(actual) >= 2 else None,
    }


def evaluate_series(predictor, group, station, sv, stride):
    # Match src/o1.py: calculate the 85% boundary before regular-grid reindexing.
    g = group.copy()
    g["time"] = pd.to_datetime(g["time"], errors="coerce")
    g = (g.dropna(subset=["time"]).sort_values("time")
          .drop_duplicates(subset=["time"], keep="first"))
    if len(g) < LOOKBACK + HORIZON + 20:
        return []

    cutoff_time = pd.Timestamp(g.iloc[int(len(g) * 0.85)]["time"])
    frame = make_series_frame(g)
    if len(frame) <= LOOKBACK + HORIZON:
        return []

    test_start = int(np.searchsorted(
        frame["timestamp"].to_numpy(dtype="datetime64[ns]"),
        np.datetime64(cutoff_time),
        side="left",
    ))

    records = []
    last_origin = len(frame) - HORIZON - 1
    for origin_idx in range(test_start, last_origin + 1, stride):
        context = frame.iloc[max(0, origin_idx - LOOKBACK + 1):origin_idx + 1].copy()
        if len(context) < LOOKBACK:
            continue

        observed = context["target"].dropna()
        if len(observed) < max(10, LOOKBACK // 2):
            continue

        target_row = frame.iloc[origin_idx + HORIZON]
        actual = pd.to_numeric(target_row["target"], errors="coerce")
        if not np.isfinite(actual):
            continue

        prediction_ds = _make_pandas_dataset({
            f"{station}__{sv}": context.reset_index(drop=True)
        })
        forecast_obj = next(iter(predictor.predict(prediction_ds)))
        forecast_values = np.asarray(forecast_obj.mean, dtype=float)
        if len(forecast_values) < HORIZON:
            continue

        deepar_prediction = float(forecast_values[HORIZON - 1])
        if not np.isfinite(deepar_prediction):
            continue

        records.append({
            "station": str(station),
            "sv": str(sv),
            "origin_time": pd.Timestamp(frame.iloc[origin_idx]["timestamp"]).isoformat(),
            "target_time": pd.Timestamp(target_row["timestamp"]).isoformat(),
            "actual_sigma_phi_proxy": float(actual),
            "deepar_prediction": deepar_prediction,
            "persistence_prediction": float(observed.iloc[-1]),
            "context_observations": int(len(observed)),
            "horizon_steps": int(HORIZON),
            "horizon_seconds": int(HORIZON * SAMPLE_SECONDS),
        })
    return records


def summarize(part):
    if part.empty:
        return {
            "DeepAR": metric_pack([], []),
            "Persistence": metric_pack([], []),
        }
    actual = part["actual_sigma_phi_proxy"].to_numpy(dtype=float)
    return {
        "DeepAR": metric_pack(actual, part["deepar_prediction"].to_numpy(dtype=float)),
        "Persistence": metric_pack(actual, part["persistence_prediction"].to_numpy(dtype=float)),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Rolling-origin held-out evaluation of O1 DeepAR."
    )
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--model-dir", type=Path, default=O1_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/o1_validation"))
    parser.add_argument(
        "--stride", type=int, default=HORIZON,
        help="Forecast-origin spacing in 30-second steps. Default 20 = every 10 minutes; use 1 for every 30 seconds.",
    )
    args = parser.parse_args()
    if args.stride < 1:
        raise ValueError("--stride must be >= 1.")
    ensure_data_file(args.data)

    required = ["station", "sv", "time", "sigma_phi_proxy"]
    df = pd.read_parquet(args.data, columns=required)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["sigma_phi_proxy"] = pd.to_numeric(df["sigma_phi_proxy"], errors="coerce")
    df = df.dropna(subset=["station", "sv", "time"])

    print(f"Loaded {len(df):,} rows")
    print(
        f"Lookback: {LOOKBACK} steps ({LOOKBACK*SAMPLE_SECONDS/60:.1f} min) | "
        f"Horizon: {HORIZON} steps ({HORIZON*SAMPLE_SECONDS/60:.1f} min) | "
        f"Stride: {args.stride} steps"
    )
    print("Loading saved DeepAR predictor; no retraining will occur...")
    predictor = load_predictor(args.model_dir)

    groups = list(df.groupby(["station", "sv"], sort=True))
    all_records = []
    for i, ((station, sv), group) in enumerate(groups, start=1):
        records = evaluate_series(predictor, group, station, sv, args.stride)
        all_records.extend(records)
        print(f"[{i}/{len(groups)}] {station}/{sv}: {len(records):,} forecasts")

    predictions = pd.DataFrame(all_records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = args.output_dir / "o1_rolling_test_predictions.csv"
    summary_path = args.output_dir / "o1_rolling_test_metrics.json"
    predictions.to_csv(predictions_path, index=False)

    overall = summarize(predictions)
    per_series = {}
    if not predictions.empty:
        for (station, sv), part in predictions.groupby(["station", "sv"]):
            per_series[f"{station}__{sv}"] = summarize(part)

    report = {
        "model": "DeepAR",
        "target": "sigma_phi_proxy",
        "sampling_seconds": int(SAMPLE_SECONDS),
        "lookback_steps": int(LOOKBACK),
        "lookback_seconds": int(LOOKBACK * SAMPLE_SECONDS),
        "horizon_steps": int(HORIZON),
        "horizon_seconds": int(HORIZON * SAMPLE_SECONDS),
        "forecast_stride_steps": int(args.stride),
        "forecast_stride_seconds": int(args.stride * SAMPLE_SECONDS),
        "test_split": "Final 15% chronologically within each station-satellite series",
        "training_boundary": "Matches src/o1.py: first 85% of original observations used for training",
        "prediction_count": int(len(predictions)),
        "overall_metrics": overall,
        "per_station_satellite_metrics": per_series,
        "notes": [
            "Each forecast uses only the preceding 60 regularly sampled target observations.",
            "The target is sigma_phi_proxy, not a directly measured standard S4 or ROTI.",
            "Persistence predicts the last observed target value at the forecast origin.",
            "Default stride equals the 20-step horizon, avoiding overlapping forecast targets.",
            "The saved predictor is evaluated without retraining or modifying model artifacts.",
        ],
    }
    summary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== OVERALL HELD-OUT TEST METRICS ===")
    print(f"Forecasts evaluated: {len(predictions):,}")
    for name, metrics in overall.items():
        print(
            f"{name:12s} | RMSE={metrics['rmse']} | MAE={metrics['mae']} "
            f"| R2={metrics['r2']} | N={metrics['n']}"
        )
    print(f"\nPredictions: {predictions_path}")
    print(f"Metrics:     {summary_path}")


if __name__ == "__main__":
    main()
