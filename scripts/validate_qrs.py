"""Validação do detector de QRS e do SQI em dados reais.

As bases não têm anotação batimento a batimento. Duas verificações indiretas:
1. concordância com o detector XQRS do pacote wfdb (referência independente), rodado no sinal
   original a 500 Hz, em amostra aleatória de registros;
2. coerência entre a FC estimada e os rótulos de ritmo (bradicardia < 60, taquicardia > 100).
Também tabula a reprovação do SQI por grupo (para verificar que o SQI não esconde AFIB).

    python scripts/validate_qrs.py  ->  results/qrs_validation.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import load_config  # noqa: E402
from src.preprocess import crop, preprocess_window, resample_to_target  # noqa: E402
from src.qrs import detect_qrs, match_beats  # noqa: E402

GROUPS = ["AFIB", "SINUS_NORMAL", "SINUS_OUTRO", "SINUS_BRADY", "SINUS_TACHY", "SINUS_ARRITMIA"]


def _compare(x500: np.ndarray, tol_s: float = 0.075):
    logging.disable(logging.WARNING)
    from wfdb import processing

    raw = crop(resample_to_target(x500, 500))
    ours = detect_qrs(preprocess_window(raw)) + 50  # janela central começa na amostra 50 (0,2 s)
    try:
        ref = processing.xqrs_detect(x500, fs=500, verbose=False) / 2.0  # -> amostras a 250 Hz
    except Exception:
        return None
    lo, hi = 50 + 0.3 * 250, 50 + 2400 - 0.3 * 250  # ignora bordas
    ref = ref[(ref >= lo) & (ref <= hi)]
    if ref.size == 0:
        return None
    # o XQRS precisa de alguns batimentos para aprender o limiar: compara só a partir do 1º batimento dele
    lo = max(lo, ref.min() - 0.075 * 250)
    ours = ours[(ours >= lo) & (ours <= hi)]
    ref = np.round(ref).astype(int)
    m = match_beats(ref, ours, 250.0, tol_s * 1000)
    return len(ref), len(ours), m


def main(n_per_group: int = 150):
    cfg = load_config()
    out = {"tolerancia_ms": 75, "referencia": "wfdb.processing.xqrs_detect a 500 Hz",
           "nota": "comparação a partir do 1º batimento do XQRS (período de aprendizado dele excluído)",
           "por_grupo": {}}
    rng_seed = cfg["seed"]
    for base in cfg["datasets"]:
        f = pd.read_parquet(cfg["paths"]["processed"] / f"{base}_features.parquet")
        X = np.load(cfg["paths"]["interim"] / f"{base}_leadI_500hz.npy", mmap_mode="r")
        for src_, fs_ in f.groupby("source"):
            for g in GROUPS:
                sub = fs_[fs_["group"] == g]
                if len(sub) == 0:
                    continue
                key = f"{src_}:{g}"
                samp = sub.sample(min(n_per_group, len(sub)), random_state=rng_seed)
                res = Parallel(n_jobs=6)(delayed(_compare)(np.asarray(X[r], float)) for r in samp["row"])
                res = [r for r in res if r is not None]
                nref, nours, m = (int(sum(v)) for v in zip(*res))
                ok = sub["sqi_ok"]
                hr = sub.loc[ok, "hr_median"]
                rec = {"n_registros_comparados": len(res), "sensibilidade_vs_xqrs": m / nref,
                       "ppv_vs_xqrs": m / nours, "sqi_reprovado": float((~ok).mean()), "n": int(len(sub)),
                       "fc_mediana": float(hr.median())}
                if g == "SINUS_BRADY":
                    rec["frac_fc_lt_60"] = float((hr < 60).mean())
                if g == "SINUS_TACHY":
                    rec["frac_fc_gt_100"] = float((hr > 100).mean())
                if g == "SINUS_NORMAL":
                    rec["frac_fc_60_100"] = float(hr.between(60, 100).mean())
                out["por_grupo"][key] = rec
                print(key, {k: round(v, 3) if isinstance(v, float) else v for k, v in rec.items()}, flush=True)
    p = cfg["paths"]["results"] / "qrs_validation.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
