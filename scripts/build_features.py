"""Janelas pré-processadas + atributos + SQI para todas as bases.

Saídas (data/processed/, fora do Git):
    {base}_windows.npy        (N, 2400) float32, janela central pré-processada
    {base}_features.parquet   record_id, row, grupo, fonte, atributos, SQI, sqi_ok, sqi_motivos

    python scripts/build_features.py [--bases chapman ptbxl]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import features, sqi  # noqa: E402
from src.config import load_config  # noqa: E402
from src.data import clean_age  # noqa: E402
from src.preprocess import crop, preprocess_window, resample_to_target  # noqa: E402
from src.qrs import detect_qrs  # noqa: E402


def _one(x: np.ndarray, fs_in: float):
    raw = crop(resample_to_target(x, fs_in))
    w = preprocess_window(raw)
    r = detect_qrs(w)
    f = features.extract(w, r=r)
    q = sqi.compute(raw, w, r=r)
    ok, why = sqi.passes(q)
    return w, {**f, **q, "sqi_ok": ok, "sqi_motivos": ",".join(why)}


def _chunk(X, rows, fs_in):
    return [_one(np.asarray(X[i], dtype=np.float64), fs_in) for i in rows]


def build(cfg, base: str):
    interim, out = cfg["paths"]["interim"], cfg["paths"]["processed"]
    out.mkdir(parents=True, exist_ok=True)
    idx = pd.read_parquet(interim / f"{base}_index.parquet")
    X = np.load(interim / f"{base}_leadI_500hz.npy", mmap_mode="r")
    valid = idx["read_ok"].fillna(False).astype(bool) & (idx["nan_leadI"].fillna(1) == 0) & ~idx["leadI_flat"].fillna(True).astype(bool)
    idx = idx[valid].reset_index(drop=True)
    fs_in = cfg["datasets"][base]["fs"]
    rows = idx["row"].to_numpy()
    chunks = np.array_split(rows, max(1, len(rows) // 500))
    t = time.time()
    res = Parallel(n_jobs=cfg["audit"]["n_jobs"])(delayed(_chunk)(X, c, fs_in) for c in chunks)
    res = [r for c in res for r in c]
    W = np.stack([r[0] for r in res]).astype(np.float32)
    F = pd.DataFrame([r[1] for r in res])
    keep = ["record_id", "row", "group", "subtype", "source", "sex", "hash_all"] + (
        ["patient_id", "strat_fold"] if base == "ptbxl" else [])
    meta = idx[keep].copy()
    meta["age"] = clean_age(idx)
    df = pd.concat([meta, F], axis=1)
    df["win"] = np.arange(len(df))
    np.save(out / f"{base}_windows.npy", W)
    df.to_parquet(out / f"{base}_features.parquet", index=False)
    print(f"[{base}] {len(df)} janelas em {time.time() - t:.0f} s; SQI reprovado: {(~df['sqi_ok']).mean():.1%}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bases", nargs="*", default=None)
    a = ap.parse_args(argv)
    cfg = load_config()
    for b in a.bases or list(cfg["datasets"]):
        build(cfg, b)


if __name__ == "__main__":
    main()
