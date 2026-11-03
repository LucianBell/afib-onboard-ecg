"""Gera data/demo/demo_pack.npz (fora do Git) para o painel e a simulação de stream.

Registros do TESTE do experimento A (Shaoxing; o modelo nunca os viu), aprovados pelo SQI,
convertidos por simulate_device() (250 Hz, A/D de 12 bits, valores positivos).
"Sinal ruim": sinusais do teste com ruído real da MIT-BIH NSTDB a −6 dB (movimento de eletrodo e
muscular) e trechos de eletrodo solto (saturação).

    python scripts/build_demo_pack.py [--n 40]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import load_config  # noqa: E402
from src.demo import PACK, REC, SCENARIOS  # noqa: E402
from src.preprocess import DEV, filter_window, simulate_device  # noqa: E402

GROUPS = {"sinusal": "SINUS_NORMAL", "afib": "AFIB", "bradicardia": "SINUS_BRADY", "taquicardia": "SINUS_TACHY"}


def main(n: int):
    cfg = load_config()
    rng = np.random.default_rng(cfg["seed"])
    f = pd.read_parquet(cfg["paths"]["processed"] / "chapman_features.parquet")
    sp = pd.read_csv(cfg["paths"]["results"] / "expA" / "split.csv")
    f = f.merge(sp[["record_id", "split"]], on="record_id")
    f = f[(f["split"] == "test") & f["sqi_ok"]]
    X = np.load(cfg["paths"]["interim"] / "chapman_leadI_500hz.npy", mmap_mode="r")
    out = {}
    for sc, g in GROUPS.items():
        x = f[f["group"] == g].sample(min(n, (f["group"] == g).sum()), random_state=cfg["seed"])
        out[f"w_{sc}"] = np.stack([simulate_device(np.asarray(X[r], float))[:REC] for r in x["row"]]).astype(np.int16)
        out[f"id_{sc}"] = x["record_id"].to_numpy().astype("U16")
    # sinal ruim
    import wfdb

    nz = {k: resample_poly(wfdb.rdrecord(str(cfg["paths"]["raw"] / "nstdb" / k)).p_signal[:, 0], 25, 36) for k in ["em", "ma"]}
    base = f[f["group"] == "SINUS_NORMAL"]
    base = base.sample(min(n, len(base)), random_state=cfg["seed"] + 1)
    bad, ids = [], []
    for i, (row, rid) in enumerate(zip(base["row"], base["record_id"])):
        clean = resample_poly(np.asarray(X[row], float), 1, 2)[:REC]
        if i % 4 == 3:  # eletrodo solto: saturação no topo da escala
            bad.append(np.full(REC, 2 ** DEV["adc_bits"] - 1, np.int16))
            ids.append(f"{rid}+eletrodo_solto")
            continue
        k = "em" if i % 2 == 0 else "ma"
        s0 = int(rng.integers(0, nz[k].size - REC))
        seg = nz[k][s0 : s0 + REC]
        noisy = clean + seg * np.sqrt(np.var(filter_window(clean)) / (np.var(filter_window(seg)) * 10 ** (-6 / 10)))
        bad.append(simulate_device(noisy, fs_in=250).astype(np.int16))
        ids.append(f"{rid}+nstdb_{k}_-6dB")
    out["w_sinal_ruim"], out["id_sinal_ruim"] = np.stack(bad), np.array(ids, dtype="U40")
    assert set(SCENARIOS) == {k[2:] for k in out if k.startswith("w_")}
    PACK.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PACK, **out)
    print(f"{PACK} ({PACK.stat().st_size / 1024:.0f} KB): " + ", ".join(f"{s}={len(out['w_' + s])}" for s in SCENARIOS))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    main(ap.parse_args().n)
