import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from config import DATA_PATH,O1_DIR,O2_DIR
from src.data import load_data
from src.o1 import train as train_o1
from src.o2 import train as train_o2

def main():
    print("Reading",DATA_PATH)
    df=load_data(DATA_PATH)
    print(f"Loaded {len(df):,} rows x {len(df.columns)} columns")
    o1_predictor = Path(O1_DIR) / "predictor"
    if (o1_predictor / "gluonts-config.json").exists():
        print("\\n[1/2] O1 DeepAR predictor already exists; skipping retraining.")
    else:
        print("\\n[1/2] Training selected O1 model: DeepAR")
        print(train_o1(df,O1_DIR,epochs=10))
    print("\\n[2/2] Training selected O2 model: LightGBM")
    print(train_o2(df,O2_DIR))
    print("\nBoth selected models trained and saved.")

if __name__=="__main__": main()
