import json
import time
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from gluonts.dataset.pandas import PandasDataset
from gluonts.torch import DeepAREstimator

from config import SAMPLE_SECONDS, LOOKBACK, HORIZON


def make_series_frame(group: pd.DataFrame) -> pd.DataFrame:
    """
    Reproduce the O1 notebook's DeepAR input format:
    a DataFrame with a `timestamp` column and one `target` column.
    The notebook explicitly passes timestamp="timestamp" to PandasDataset.
    """
    g = group.copy()
    g["time"] = pd.to_datetime(g["time"], errors="coerce")
    g = g.dropna(subset=["time"])
    g = g.sort_values("time").drop_duplicates("time", keep="first")

    if g.empty:
        return pd.DataFrame(columns=["timestamp", "target"])

    s = (
        g[["time", "sigma_phi_proxy"]]
        .set_index("time")
        .sort_index()["sigma_phi_proxy"]
        .astype("float64")
    )

    full_index = pd.date_range(
        start=s.index.min(),
        end=s.index.max(),
        freq=f"{SAMPLE_SECONDS}s",
        name="timestamp",
    )
    s = s.reindex(full_index).rename("target")

    frame = s.rename_axis("timestamp").reset_index()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["target"] = pd.to_numeric(frame["target"], errors="coerce")
    return frame[["timestamp", "target"]]


def _make_pandas_dataset(series_dict):
    """Use the same timestamp-column API as the supplied O1 notebook."""
    return PandasDataset(
        series_dict,
        target="target",
        timestamp="timestamp",
        freq=f"{SAMPLE_SECONDS}s",
    )


def train(df: pd.DataFrame, out_dir, epochs: int = 10):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    series_dict = {}
    metadata = []

    # Match notebook: group by station/satellite, then determine the
    # 85% cutoff from the original number of observations (before reindex).
    for (station, sv), group in df.groupby(["station", "sv"], sort=False):
        g = group.copy()
        g["time"] = pd.to_datetime(g["time"], errors="coerce")
        g = (
            g.dropna(subset=["time"])
             .sort_values("time")
             .drop_duplicates(subset=["time"], keep="first")
        )
        if len(g) < LOOKBACK + HORIZON + 20:
            continue

        cutoff_position = int(len(g) * 0.85)
        if cutoff_position >= len(g):
            continue
        cutoff_time = pd.Timestamp(g.iloc[cutoff_position]["time"])

        full_frame = make_series_frame(g)
        train_frame = full_frame[
            full_frame["timestamp"] < cutoff_time
        ].copy()

        # GluonTS needs enough target history to form training windows.
        valid_count = train_frame["target"].notna().sum()
        if valid_count < LOOKBACK + HORIZON + 20:
            continue

        item_id = f"{station}__{sv}"
        series_dict[item_id] = train_frame.reset_index(drop=True)
        metadata.append({
            "item_id": item_id,
            "station": str(station),
            "sv": str(sv),
            "n_original": int(len(g)),
            "n_reindexed_train": int(len(train_frame)),
            "n_valid_train_targets": int(valid_count),
            "cutoff_time": cutoff_time.isoformat(),
        })

    if not series_dict:
        raise ValueError(
            "No sufficiently long O1 station/satellite series. "
            "Check time, station, sv and sigma_phi_proxy columns."
        )

    train_ds = _make_pandas_dataset(series_dict)

    estimator = DeepAREstimator(
        freq=f"{SAMPLE_SECONDS}s",
        prediction_length=HORIZON,
        context_length=LOOKBACK,
        hidden_size=32,
        num_layers=2,
        dropout_rate=0.1,
        lr=1e-3,
        batch_size=32,
        num_batches_per_epoch=25,
        num_parallel_samples=10,
        trainer_kwargs={
            "max_epochs": int(epochs),
            "accelerator": "auto",
        },
    )

    start = time.perf_counter()
    predictor = estimator.train(train_ds)
    elapsed = time.perf_counter() - start

    destination = out_dir / "predictor"
    if destination.exists():
        shutil.rmtree(destination)
    # GluonTS Predictor.serialize writes files directly into this directory;
    # unlike some serializers, it does not create the destination directory.
    destination.mkdir(parents=True, exist_ok=True)
    predictor.serialize(destination)

    report = {
        "model": "DeepAR",
        "target": "sigma_phi_proxy",
        "input_variables": ["sigma_phi_proxy"],
        "lookback_steps": LOOKBACK,
        "horizon_steps": HORIZON,
        "sampling_seconds": SAMPLE_SECONDS,
        "training_seconds": elapsed,
        "epochs": int(epochs),
        "series_count": len(series_dict),
        "series": metadata,
        "methodology": (
            "Notebook-aligned univariate DeepAR. The notebook's 35 engineered "
            "features are not DeepAR covariates; the selected DeepAR receives "
            "the historical target only."
        ),
        "selection_note": (
            "DeepAR had the lowest reported RMSE in the supplied O1 notebook, "
            "but its evaluation sample count differed from several other models."
        ),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    return {
        "model": "DeepAR",
        "training_seconds": elapsed,
        "series_count": len(series_dict),
        "saved_to": str(destination),
    }


def load_predictor(out_dir):
    from gluonts.torch import PyTorchPredictor
    return PyTorchPredictor.deserialize(Path(out_dir) / "predictor")


def forecast(predictor, df, station, sv):
    subset = df[
        (df["station"].astype(str) == str(station))
        & (df["sv"].astype(str) == str(sv))
    ]
    frame = make_series_frame(subset)

    if len(frame) < LOOKBACK:
        raise ValueError(
            f"At least {LOOKBACK} regularly sampled observations are required "
            "for the DeepAR forecast."
        )

    context = frame.tail(LOOKBACK).copy()
    if context["target"].isna().any():
        # DeepAR can handle missing values in historical series through its
        # observed-value indicator, but an entirely missing context is invalid.
        if context["target"].notna().sum() < max(10, LOOKBACK // 2):
            raise ValueError("Too many missing sigma_phi_proxy values in the context window.")

    item_id = f"{station}__{sv}"
    prediction_ds = _make_pandas_dataset({
        item_id: context.reset_index(drop=True)
    })

    forecast_object = next(iter(predictor.predict(prediction_ds)))
    values = np.asarray(forecast_object.mean, dtype=float)

    return {
        "forecast": float(values[HORIZON - 1]),
        "series": values.tolist(),
        "last_observed": float(context["target"].dropna().iloc[-1]),
    }
