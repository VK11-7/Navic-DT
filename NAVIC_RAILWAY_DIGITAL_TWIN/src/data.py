import gdown
import pandas as pd
from pathlib import Path

from config import DATA_FILE_ID

REQUIRED = {"time","station","sv","C5A","L5A","S5A","sigma_phi_proxy"}

def ensure_data_file(path: Path) -> Path:
    if not path.exists():
        downloaded_path = gdown.download(
            id=DATA_FILE_ID,
            output=str(path),
            quiet=False,
        )
        if downloaded_path is None or not path.is_file():
            raise RuntimeError(f"Failed to download the dataset to {path}")
    return path

def load_data(path):
    ensure_data_file(path)
    df = pd.read_parquet(path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time","station","sv"])
    df = df.sort_values(["station","sv","time"])
    df = df.drop_duplicates(["station","sv","time"], keep="first")
    return df.reset_index(drop=True)

def rebuild_target(df):
    future = df[["station","sv","time","sigma_phi_proxy"]].copy()
    future["time"] = future["time"] - pd.Timedelta(minutes=10)
    future = future.rename(columns={"time":"origin_time","sigma_phi_proxy":"target_10min"})
    x = df.rename(columns={"time":"origin_time"}).drop(columns=["target_10min"], errors="ignore")
    x = x.merge(future, on=["station","sv","origin_time"], how="left", sort=False)
    return x.rename(columns={"origin_time":"time"}).sort_values(["station","sv","time"]).reset_index(drop=True)
