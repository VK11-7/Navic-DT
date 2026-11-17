from pathlib import Path
ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data.parquet"
DATA_FILE_ID = "1dDR5rEteACPD7BdoFOQfJPykZNREtZpJ"
O1_DIR = ROOT / "models" / "o1_deepar"
O2_DIR = ROOT / "models" / "o2_lightgbm"
SAMPLE_SECONDS = 30
LOOKBACK = 60
HORIZON = 20
RANDOM_STATE = 42
O2_MAX_ROWS_PER_SERIES = 120_000
O2_MAX_PER_CLASS = 250_000

# Geography assets are loaded automatically; no frontend file upload is required.
GEOGRAPHY_DIR = ROOT / "data" / "geography"
RAILWAY_CORRIDOR_GEOJSON = GEOGRAPHY_DIR / "railway_corridor.geojson"
