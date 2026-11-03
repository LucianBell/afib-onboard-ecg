"""Calibração externa (pergunta de revisão): Brier e ECE da regressão logística no PTB-XL, com a
calibração Platt ajustada em Shaoxing. Complementa o experimento B.

    python scripts/calibration_external.py -> results/expB/calibration_external.json
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import evaluate as ev  # noqa: E402
from src.config import load_config  # noqa: E402
from src.features import FEATURE_NAMES  # noqa: E402

cfg = load_config()
art = joblib.load(cfg["paths"]["processed"] / "expA_models" / "logreg.joblib")
b = cfg["experiment_b"]
pt = pd.read_parquet(cfg["paths"]["processed"] / "ptbxl_features.parquet")
pt = pt[pt["group"].isin(b["ptbxl_groups_positive"] + b["ptbxl_groups_negative"]) & pt["sqi_ok"]]
y = pt["group"].isin(b["ptbxl_groups_positive"]).to_numpy().astype(int)
p = art["calibrator"].transform(art["model"].predict_proba(pt[FEATURE_NAMES])[:, 1])
bins = np.minimum((p * 10).astype(int), 9)
rel = [{"faixa_prob": f"{k / 10:.1f}-{(k + 1) / 10:.1f}", "n": int((bins == k).sum()),
        "prob_media": float(p[bins == k].mean()) if (bins == k).any() else None,
        "fracao_afib_observada": float(y[bins == k].mean()) if (bins == k).any() else None} for k in range(10)]
out = {"n": int(len(y)), "prevalencia": float(y.mean()), "brier": ev.brier(y, p), "ece": ev.ece(y, p),
       "confiabilidade": rel,
       "nota": "Calibração Platt ajustada na validação de Shaoxing (prevalência ~21%); PTB-XL tem prevalência menor."}
p_out = cfg["paths"]["results"] / "expB" / "calibration_external.json"
p_out.write_text(json.dumps(out, indent=2, ensure_ascii=False))
print(json.dumps({k: out[k] for k in ["n", "prevalencia", "brier", "ece"]}))
for r in rel:
    print(r)
