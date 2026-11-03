"""Atributos por janela (2.400 amostras a 250 Hz, já pré-processada).

Grupos: irregularidade RR, atividade atrial, morfologia, espectro. O SQI é calculado à parte
(`src/sqi.py`). Idade e sexo ficam fora: o monitor recebe só o sinal.
Todos os atributos são invariantes a offset e escala (a janela chega normalizada e os
atributos de amplitude são relativos à amplitude do QRS).
"""
from __future__ import annotations

import numpy as np
from scipy.signal import welch

from src.qrs import detect_qrs

FS = 250.0

RR_FEATURES = ["n_beats", "hr_mean", "hr_median", "rr_mean", "rr_median", "sdnn", "rmssd", "nrmssd", "pnn50",
               "cv_rr", "madnn", "rr_range_norm", "pct_drr_gt10", "sd1", "sd2", "sd1_sd2", "rr_entropy", "tpr"]
ATRIAL_FEATURES = ["p_amp_rel", "p_consistency", "tq_activity", "tq_frac_4_9hz"]
MORPH_FEATURES = ["qrs_width_ms", "beat_corr_mean", "beat_corr_min"]
SPEC_FEATURES = ["pow_0p5_3", "pow_3_8", "pow_8_15", "pow_15_30", "spec_entropy"]
FEATURE_NAMES = RR_FEATURES + ATRIAL_FEATURES + MORPH_FEATURES + SPEC_FEATURES


def rr_features(r: np.ndarray, fs: float = FS) -> dict:
    out = dict.fromkeys(RR_FEATURES, np.nan)
    out["n_beats"] = float(r.size)
    if r.size < 3:
        return out
    rr = np.diff(r) / fs
    d = np.diff(rr)
    m, med = rr.mean(), np.median(rr)
    sdnn = rr.std(ddof=1) if rr.size > 1 else np.nan
    rmssd = np.sqrt(np.mean(d ** 2))
    sd1 = np.sqrt(0.5) * d.std(ddof=1) if d.size > 1 else np.nan
    sd2sq = 2 * sdnn ** 2 - sd1 ** 2 if np.isfinite(sd1) else np.nan
    sd2 = np.sqrt(sd2sq) if np.isfinite(sd2sq) and sd2sq > 0 else np.nan
    # entropia de Shannon do histograma de RR (8 classes entre min e max), normalizada em [0, 1]
    if np.ptp(rr) > 0:
        h, _ = np.histogram(rr, bins=8)
        p = h[h > 0] / h.sum()
        ent = float(-(p * np.log(p)).sum() / np.log(8))
    else:
        ent = 0.0
    # razão de pontos de virada (esperado ~2/3 para sequência aleatória)
    tp = np.sum((rr[1:-1] - rr[:-2]) * (rr[1:-1] - rr[2:]) > 0) if rr.size >= 3 else 0
    tpr = tp / (rr.size - 2) if rr.size >= 3 else np.nan
    out.update(
        hr_mean=60.0 / m, hr_median=60.0 / med, rr_mean=m, rr_median=med, sdnn=sdnn, rmssd=rmssd,
        nrmssd=rmssd / m, pnn50=float(np.mean(np.abs(d) > 0.05)), cv_rr=sdnn / m,
        madnn=float(np.median(np.abs(d)) / med), rr_range_norm=float(np.ptp(rr) / med),
        pct_drr_gt10=float(np.mean(np.abs(d) / rr[:-1] > 0.10)), sd1=sd1, sd2=sd2,
        sd1_sd2=sd1 / sd2 if np.isfinite(sd2) and sd2 > 0 else np.nan, rr_entropy=ent, tpr=tpr,
    )
    return out


def _beats(x: np.ndarray, r: np.ndarray, pre: int, post: int) -> np.ndarray:
    ok = r[(r - pre >= 0) & (r + post <= x.size)]
    if ok.size == 0:
        return np.empty((0, pre + post))
    return np.stack([x[i - pre : i + post] for i in ok])


def _corr_rows(m: np.ndarray, ref: np.ndarray) -> np.ndarray:
    a = m - m.mean(1, keepdims=True)
    b = ref - ref.mean()
    den = np.sqrt((a ** 2).sum(1) * (b ** 2).sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, (a @ b) / den, np.nan)


def template_features(x: np.ndarray, r: np.ndarray, fs: float = FS) -> dict:
    out = dict.fromkeys(ATRIAL_FEATURES + MORPH_FEATURES, np.nan)
    pre, post = int(0.30 * fs), int(0.45 * fs)
    B = _beats(x, r, pre, post)
    if B.shape[0] < 3:
        return out
    B = B - np.median(B[:, : int(0.05 * fs)], axis=1, keepdims=True)  # linha de base local
    T = np.median(B, axis=0)
    qrs = slice(pre - int(0.06 * fs), pre + int(0.06 * fs))
    A = np.max(np.abs(T[qrs]))
    if A <= 0:
        return out
    # onda P: região -250..-80 ms antes do R
    p = slice(pre - int(0.25 * fs), pre - int(0.08 * fs))
    out["p_amp_rel"] = float(np.ptp(T[p]) / A)
    out["p_consistency"] = float(np.nanmedian(_corr_rows(B[:, p], T[p])))
    # morfologia do QRS
    qwin = slice(pre - int(0.10 * fs), pre + int(0.15 * fs))
    c = _corr_rows(B[:, qwin], T[qwin])
    out["beat_corr_mean"], out["beat_corr_min"] = float(np.nanmean(c)), float(np.nanmin(c))
    above = np.abs(T) > 0.25 * A
    i0 = i1 = pre
    while i0 > 0 and above[i0 - 1]:
        i0 -= 1
    while i1 < T.size - 1 and above[i1 + 1]:
        i1 += 1
    out["qrs_width_ms"] = float((i1 - i0 + 1) * 1000 / fs)
    # atividade entre batimentos: segmentos TQ (R+400 ms .. próximo R-300 ms)
    segs = []
    for a, b in zip(r[:-1], r[1:]):
        s0, s1 = a + int(0.40 * fs), b - int(0.30 * fs)
        if s1 - s0 >= int(0.12 * fs):
            seg = x[s0:s1]
            segs.append(seg - seg.mean())
    if segs:
        out["tq_activity"] = float(np.median([s.std() for s in segs]) / A)
        cat = np.concatenate(segs)
        if cat.size >= int(0.5 * fs):
            f, pw = welch(cat, fs=fs, nperseg=min(128, cat.size))
            tot = pw[(f >= 1) & (f <= 30)].sum()
            out["tq_frac_4_9hz"] = float(pw[(f >= 4) & (f <= 9)].sum() / tot) if tot > 0 else np.nan
    return out


def spectral_features(x: np.ndarray, fs: float = FS) -> dict:
    f, pw = welch(x, fs=fs, nperseg=512)
    band = (f >= 0.5) & (f <= 30)
    tot = pw[band].sum()
    out = {}
    for name, lo, hi in [("pow_0p5_3", 0.5, 3), ("pow_3_8", 3, 8), ("pow_8_15", 8, 15), ("pow_15_30", 15, 30)]:
        out[name] = float(pw[(f >= lo) & (f < hi)].sum() / tot) if tot > 0 else np.nan
    p = pw[band] / tot if tot > 0 else None
    out["spec_entropy"] = float(-(p[p > 0] * np.log(p[p > 0])).sum() / np.log(p.size)) if p is not None else np.nan
    return out


def extract(x: np.ndarray, fs: float = FS, r: np.ndarray | None = None) -> dict:
    """Todos os atributos de uma janela pré-processada. `r` pode ser passado para reaproveitar o QRS."""
    if r is None:
        r = detect_qrs(x, fs)
    return {**rr_features(r, fs), **template_features(x, r, fs), **spectral_features(x, fs)}
