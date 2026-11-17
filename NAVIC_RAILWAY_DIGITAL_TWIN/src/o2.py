import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from config import RANDOM_STATE, O2_MAX_ROWS_PER_SERIES, O2_MAX_PER_CLASS

WAVELENGTH = 299792458.0/1176.45e6
FEATURES = [
"cn0","cn0_diff","cn0_rate","cn0_std_10","cn0_mean_10",
"pseudorange","pseudorange_diff","pseudorange_rate","pseudorange_accel","pseudorange_std_10",
"carrier_phase","carrier_phase_diff","carrier_phase_rate","carrier_phase_accel","carrier_phase_std_10","phase_jump_score",
"doppler","doppler_diff","doppler_rate","doppler_accel","doppler_std_10","doppler_jump_score",
"cmc_residual","cmc_std_10","phase_range_rate_mps","code_carrier_rate_residual","doppler_phase_residual",
"pr_rate_std_5","pr_rate_std_10","pr_rate_std_20","doppler_rate_std_5","doppler_rate_std_10","doppler_rate_std_20",
"cn0_std_5","cn0_std_10","cn0_std_20","cmc_std_5","cmc_std_10","cmc_std_20"
]
# The notebook's literal feature list repeats cn0_std_10 and cmc_std_10.
# LightGBM requires unique feature names; preserve first-seen order.
FEATURES = list(dict.fromkeys(FEATURES))

def engineer(g):
    g=g.sort_values("time").copy()
    g["cn0"]=g.S5A; g["cn0_diff"]=g.S5A.diff(); g["cn0_rate"]=g.cn0_diff/30
    g["cn0_std_10"]=g.S5A.rolling(10,min_periods=3).std()
    g["cn0_mean_10"]=g.S5A.rolling(10,min_periods=3).mean()
    g["pseudorange"]=g.C5A; g["pseudorange_diff"]=g.C5A.diff()
    g["pseudorange_rate"]=g.pseudorange_diff/30
    g["pseudorange_accel"]=g.pseudorange_rate.diff()/30
    g["pseudorange_std_10"]=g.C5A.rolling(10,min_periods=3).std()
    g["carrier_phase"]=g.L5A; g["carrier_phase_diff"]=g.L5A.diff()
    g["carrier_phase_rate"]=g.carrier_phase_diff/30
    g["carrier_phase_accel"]=g.carrier_phase_rate.diff()/30
    g["carrier_phase_std_10"]=g.L5A.rolling(10,min_periods=3).std()
    med=g.carrier_phase_diff.rolling(10,min_periods=3).median()
    std=g.carrier_phase_diff.rolling(10,min_periods=3).std()
    g["phase_jump_score"]=(g.carrier_phase_diff-med).abs()/(std+1e-6)
    # D5A is not present in checked data: this is a carrier-phase-derived Doppler proxy.
    if "doppler_proxy_hz" not in g.columns:
        g["doppler_proxy_hz"] = -g.carrier_phase_rate / WAVELENGTH
    g["doppler"]=g["doppler_proxy_hz"]
    g["doppler_diff"]=g.doppler.diff(); g["doppler_rate"]=g.doppler_diff/30
    g["doppler_accel"]=g.doppler_rate.diff()/30
    g["doppler_std_10"]=g.doppler.rolling(10,min_periods=3).std()
    dm=g.doppler_diff.rolling(10,min_periods=3).median()
    ds=g.doppler_diff.rolling(10,min_periods=3).std()
    g["doppler_jump_score"]=(g.doppler_diff-dm).abs()/(ds+1e-6)
    g["cmc"]=g.C5A-g.L5A*WAVELENGTH
    g["cmc_residual"]=g.cmc-g.cmc.rolling(10,min_periods=3).mean()
    g["cmc_std_10"]=g.cmc.rolling(10,min_periods=3).std()
    g["phase_range_rate_mps"]=g.carrier_phase_rate*WAVELENGTH
    g["code_carrier_rate_residual"]=g.pseudorange_rate-g.phase_range_rate_mps
    g["doppler_phase_residual"]=g.doppler+g.carrier_phase_rate/WAVELENGTH
    for w in [5,10,20]:
        g[f"pr_rate_std_{w}"]=g.pseudorange_rate.rolling(w,min_periods=3).std()
        g[f"doppler_rate_std_{w}"]=g.doppler_rate.rolling(w,min_periods=3).std()
        g[f"cn0_std_{w}"]=g.cn0.rolling(w,min_periods=3).std()
        g[f"cmc_std_{w}"]=g.cmc_residual.rolling(w,min_periods=3).std()
    return g


def inject(g, rng, cls, placement="random"):
    """
    Inject synthetic GNSS signal disturbances.

    Classes:
        0 = Genuine
        1 = Multipath
        2 = Spoofing

    placement:
        random = Original-style randomly positioned training events
        latest = One event ending at the latest observation for scenario testing
    """

    g = g.copy()
    n = len(g)
    g["label"] = 0

    if n < 50 or cls not in (1, 2):
        return g

    # Ensure the Doppler proxy exists and follows the same convention
    # used by engineer().
    if "doppler_proxy_hz" not in g.columns:
        phase_rate = pd.to_numeric(
            g["L5A"], errors="coerce"
        ).diff() / 30.0

        g["doppler_proxy_hz"] = -phase_rate / WAVELENGTH

    def apply_event(start, length):
        end = min(start + length, n)
        length = end - start

        if length < 10:
            return 0

        t = np.arange(length, dtype=float)
        ramp = np.linspace(0.0, 1.0, length)
        smooth = 3.0 * ramp**2 - 2.0 * ramp**3

        if cls == 1:
            # Multipath: oscillatory code, carrier-phase and C/N0 disturbances.
            envelope = np.sin(
                np.pi * t / max(length - 1, 1)
            )**2

            frequency = rng.uniform(0.03, 0.12)
            phase = rng.uniform(0.0, 2.0 * np.pi)

            oscillation = envelope * np.sin(
                2.0 * np.pi * frequency * t + phase
            )

            code_delta = rng.uniform(2.0, 8.0) * oscillation
            phase_delta = rng.uniform(0.03, 0.20) * oscillation
            cn0_delta = -rng.uniform(1.0, 4.0) * np.abs(oscillation)

        else:
            # Spoofing: gradually increasing code, phase and C/N0 biases.
            code_delta = rng.uniform(5.0, 30.0) * smooth
            phase_delta = rng.uniform(0.5, 4.0) * smooth
            cn0_delta = rng.uniform(1.0, 4.0) * smooth

        # Apply the disturbances.
        for col, delta in [
            ("C5A", code_delta),
            ("L5A", phase_delta),
            ("S5A", cn0_delta)
        ]:
            base = pd.to_numeric(
                g[col], errors="coerce"
            ).to_numpy(dtype=float)

            base[start:end] += delta
            g[col] = base

        # Use the same wavelength-based Doppler proxy convention
        # as the feature engineering pipeline.
        doppler_delta = (
            -np.gradient(phase_delta, 30.0) / WAVELENGTH
        )

        doppler_base = pd.to_numeric(
            g["doppler_proxy_hz"], errors="coerce"
        ).to_numpy(dtype=float)

        doppler_base[start:end] += doppler_delta
        g["doppler_proxy_hz"] = doppler_base

        # Label only the affected observations.
        g.iloc[
            start:end, g.columns.get_loc("label")
        ] = cls

        return length

    if placement == "latest":

        # One event that remains active at the latest observation.
        if cls == 1:
            length = int(rng.integers(20, 61))
        else:
            length = int(rng.integers(30, 81))

        length = min(length, n)
        apply_event(n - length, length)

    elif placement == "random":

        # Preserve the original random-position training strategy.
        target = int(n * 0.35)
        changed = 0
        attempts = 0

        while changed < target and attempts < max(20, n // 10):
            attempts += 1

            if cls == 1:
                length = int(rng.integers(20, 61))
            else:
                length = int(rng.integers(30, 81))

            # Randomly position the event within the observation stream.
            max_start = max(21, n - 20)
            start = int(rng.integers(20, max_start))

            actual_length = apply_event(start, length)
            changed += actual_length

    else:
        raise ValueError(
            "placement must be either 'random' or 'latest'."
        )

    return g

def build_training(df):
    rng=np.random.default_rng(RANDOM_STATE)
    train_frames=[]; val_frames=[]
    for (station,sv), raw in df.groupby(["station","sv"],sort=False):
        raw=raw.sort_values("time")
        if len(raw)>O2_MAX_ROWS_PER_SERIES:
            pos=np.linspace(0,len(raw)-1,O2_MAX_ROWS_PER_SERIES,dtype=int)
            raw=raw.iloc[pos].copy()
        keep=["time","station","sv","C5A","L5A","S5A"]
        if "doppler_proxy_hz" in raw.columns: keep.append("doppler_proxy_hz")
        raw=raw[keep].copy()
        raw[["C5A","L5A","S5A"]]=raw[["C5A","L5A","S5A"]].apply(pd.to_numeric,errors="coerce")
        if "doppler_proxy_hz" not in raw.columns:
            raw["doppler_proxy_hz"]=-(raw["L5A"].diff()/30.0)/WAVELENGTH
        else:
            raw["doppler_proxy_hz"]=pd.to_numeric(raw["doppler_proxy_hz"],errors="coerce")
        raw=raw.dropna(subset=["C5A","L5A","S5A"])
        n=len(raw)
        if n<300: continue
        tr_end=int(n*.70); va_end=int(n*.85)
        for split_name, segment in [("train",raw.iloc[:tr_end]),("val",raw.iloc[tr_end:va_end])]:
            if len(segment)<100: continue
            for cls in [0,1,2]:
                scenario=segment.copy()
                scenario["label"]=0
                if cls:
                    scenario=inject(scenario,rng,cls)
                # The class label describes the scenario class, matching notebook scenario construction.
                f=engineer(scenario)
                # Preserve attack_label: clean epochs inside an injected scenario
                # remain Genuine, while only injected epochs carry class 1 or 2.
                (train_frames if split_name=="train" else val_frames).append(f)
    if not train_frames or not val_frames:
        raise ValueError("Insufficient per-series data for chronological O2 train/validation scenarios.")
    train=pd.concat(train_frames,ignore_index=True).replace([np.inf,-np.inf],np.nan)
    val=pd.concat(val_frames,ignore_index=True).replace([np.inf,-np.inf],np.nan)
    def balance(frame, limit):
        out=[]
        for cls in [0,1,2]:
            g=frame[frame.label==cls]
            if len(g)>limit: g=g.sample(limit,random_state=RANDOM_STATE)
            out.append(g)
        return pd.concat(out,ignore_index=True).sample(frac=1,random_state=RANDOM_STATE)
    return balance(train,O2_MAX_PER_CLASS), balance(val,min(75_000,O2_MAX_PER_CLASS))

def train(df,out_dir):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); t=time.perf_counter()
    train_data,val_data=build_training(df)
    Xtr=train_data[FEATURES].astype(np.float32)
    Xv=val_data[FEATURES].astype(np.float32)
    med=Xtr.median()
    Xtr=Xtr.fillna(med); Xv=Xv.fillna(med)
    ytr=train_data.label.astype(int); yv=val_data.label.astype(int)
    model=lgb.LGBMClassifier(objective="multiclass",num_class=3,n_estimators=500,
        learning_rate=.05,num_leaves=63,max_depth=-1,min_child_samples=40,
        subsample=.85,colsample_bytree=.85,reg_alpha=.1,reg_lambda=1.0,
        random_state=RANDOM_STATE,n_jobs=-1,verbosity=-1)
    model.fit(Xtr,ytr,eval_set=[(Xv,yv)],callbacks=[lgb.early_stopping(50,verbose=False)])
    elapsed=time.perf_counter()-t
    joblib.dump(model,out/"lightgbm_classifier.joblib")
    joblib.dump(FEATURES,out/"feature_list.joblib")
    joblib.dump(med,out/"train_medians.joblib")
    pred=model.predict(Xv)
    report={"model":"LightGBM","training_seconds":elapsed,"training_rows":len(train_data),"validation_rows":len(val_data),
        "features":len(FEATURES),"validation_accuracy":float(accuracy_score(yv,pred)),
        "validation_macro_f1":float(f1_score(yv,pred,average="macro")),
        "classification_report":classification_report(yv,pred,target_names=["Genuine","Multipath","Spoofing"],output_dict=True,zero_division=0),
        "caveat":"Synthetic attack labels; validation only measures generated scenario discrimination."}
    (out/"training_report.json").write_text(json.dumps(report,indent=2))
    return report

def load_model(out_dir):
    p=Path(out_dir)
    return joblib.load(p/"lightgbm_classifier.joblib"),joblib.load(p/"feature_list.joblib"),joblib.load(p/"train_medians.joblib")


def predict(model, features, medians, df, station, sv):
    """
    Classify successive observations from the selected station/satellite.

    The model uses the latest 200 observations to engineer features.
    It then evaluates the latest 20 observations independently.
    The final prediction is the current classification.
    """

    g = df[
        (df.station.astype(str) == str(station)) &
        (df.sv.astype(str) == str(sv))
    ].sort_values("time").tail(200).copy()

    if len(g) < 25:
        raise ValueError(
            "At least 25 observations are required for O2 inference."
        )

    # Generate features using the existing O2 feature engineering.
    f = engineer(g)

    x = (
        f[features]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(medians)
    )

    # Evaluate successive observations, not just one isolated row.
    evaluation_window = x.tail(20)

    probability_array = model.predict_proba(evaluation_window)

    # Map model class IDs explicitly.
    class_mapping = {
        0: "Genuine",
        1: "Multipath",
        2: "Spoofing"
    }

    model_classes = [int(c) for c in model.classes_]

    recent_predictions = []

    for i, probabilities in enumerate(probability_array):

        probability_dict = {
            class_mapping[class_id]: float(probability)
            for class_id, probability in zip(
                model_classes, probabilities
            )
        }

        predicted_class = max(
            probability_dict,
            key=probability_dict.get
        )

        row_position = len(g) - len(evaluation_window) + i

        recent_predictions.append({
            "time": str(g.iloc[row_position]["time"]),
            "class_name": predicted_class,
            "confidence": probability_dict[predicted_class],
            "probabilities": probability_dict
        })

    # The final entry represents the latest observation.
    latest = recent_predictions[-1]

    return {
        "class_name": latest["class_name"],
        "confidence": latest["confidence"],
        "probabilities": latest["probabilities"],
        "recent_predictions": recent_predictions
    }