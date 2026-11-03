"""Detecção de QRS leve (numpy/scipy), pensada para o Raspberry Pi.

`detect_qrs`: variante offline do Pan-Tompkins para uma janela inteira — passa-banda 5-18 Hz,
derivada, quadrado, integração móvel, limiar adaptativo com busca retroativa e período refratário.
A posição final do R é o extremo do sinal na polaridade dominante do QRS (a derivação I pode ter
QRS negativo).

`detect_qrs_simple`: detector de princípio diferente (picos de |sinal passa-banda|), usado só para
a concordância entre detectores no SQI (bSQI).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

from src.config import load_config

Q = load_config()["qrs"]


@lru_cache(maxsize=8)
def _band(fs: float, lo: float, hi: float):
    return butter(2, [lo, hi], btype="bandpass", fs=fs, output="sos")


def _bandpass(x: np.ndarray, fs: float) -> np.ndarray:
    return sosfiltfilt(_band(float(fs), *Q["band_hz"]), np.asarray(x, dtype=np.float64))


def detect_qrs(x: np.ndarray, fs: float = 250.0) -> np.ndarray:
    """Índices dos picos R (ordenados). Retorna array vazio se não houver QRS plausível."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < fs or not np.isfinite(x).all() or np.ptp(x) == 0:
        return np.array([], dtype=int)
    bp = _bandpass(x, fs)
    env = np.gradient(bp) ** 2
    w = max(1, int(Q["integration_ms"] * fs / 1000))
    env = np.convolve(env, np.ones(w) / w, mode="same")
    refr = int(Q["refractory_ms"] * fs / 1000)
    cand, props = find_peaks(env, distance=refr, height=0)
    if cand.size == 0:
        return np.array([], dtype=int)
    h = props["peak_heights"]
    # limiar: fração do nível típico dos picos fortes; robusto a um artefato isolado
    signal_level = np.percentile(h, 90)
    noise_level = np.median(env)
    thr = noise_level + 0.25 * (signal_level - noise_level)
    peaks = cand[h >= thr]
    if Q.get("search_back", True) and peaks.size >= 2:
        rr = np.diff(peaks)
        med = np.median(rr)
        extra = []
        for a, b in zip(peaks[:-1], peaks[1:]):
            if b - a > 1.66 * med:  # batimento provavelmente perdido: busca com limiar menor
                inside = cand[(cand > a + refr) & (cand < b - refr)]
                if inside.size:
                    hh = env[inside]
                    best = inside[np.argmax(hh)]
                    if env[best] >= noise_level + 0.5 * (thr - noise_level):
                        extra.append(best)
        if extra:
            peaks = np.sort(np.concatenate([peaks, extra]))
    if peaks.size == 0:
        return peaks.astype(int)
    # refinamento: extremo na polaridade dominante do QRS, em ±75 ms
    half = int(0.075 * fs)
    lo = np.clip(peaks - half, 0, x.size - 1)
    hi = np.clip(peaks + half + 1, 1, x.size)
    xc = x - np.median(x)
    pos = np.array([xc[a:b].max() for a, b in zip(lo, hi)])
    neg = np.array([-xc[a:b].min() for a, b in zip(lo, hi)])
    sign = 1.0 if np.median(pos) >= np.median(neg) else -1.0
    r = np.array([a + int(np.argmax(sign * xc[a:b])) for a, b in zip(lo, hi)])
    # remove duplicatas que o refinamento possa ter juntado
    r = np.unique(r)
    if r.size > 1:
        keep = np.concatenate([[True], np.diff(r) >= refr])
        r = r[keep]
    return r.astype(int)


def detect_qrs_simple(x: np.ndarray, fs: float = 250.0) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.size < fs or not np.isfinite(x).all() or np.ptp(x) == 0:
        return np.array([], dtype=int)
    a = np.abs(_bandpass(x, fs))
    refr = int(Q["refractory_ms"] * fs / 1000)
    p, _ = find_peaks(a, distance=refr, height=0.4 * np.percentile(a, 99.5))
    return p.astype(int)


def match_beats(a: np.ndarray, b: np.ndarray, fs: float = 250.0, tol_ms: float = 100.0) -> int:
    """Número de batimentos de `a` com correspondente em `b` dentro da tolerância (pareamento 1-1)."""
    if a.size == 0 or b.size == 0:
        return 0
    tol = tol_ms * fs / 1000
    used = np.zeros(b.size, dtype=bool)
    n = 0
    for t in a:
        j = np.searchsorted(b, t)
        best, bd = -1, tol + 1
        for k in (j - 1, j):
            if 0 <= k < b.size and not used[k] and abs(b[k] - t) <= bd:
                best, bd = k, abs(b[k] - t)
        if best >= 0 and bd <= tol:
            used[best] = True
            n += 1
    return n


def agreement(a: np.ndarray, b: np.ndarray, fs: float = 250.0) -> float:
    """F1 de concordância entre dois conjuntos de batimentos (bSQI)."""
    if a.size + b.size == 0:
        return 0.0
    return 2.0 * match_beats(a, b, fs) / (a.size + b.size)
