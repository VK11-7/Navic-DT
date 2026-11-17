import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from config import DATA_PATH
from src.data import load_data
d=load_data(DATA_PATH)
print("Rows:",len(d),"Columns:",len(d.columns))
print("Stations:",sorted(d.station.astype(str).unique()))
print("Satellites:",sorted(d.sv.astype(str).unique()))
print("Time:",d.time.min(),"to",d.time.max())
print(d[["C5A","L5A","S5A","sigma_phi_proxy"]].isna().sum())
