"""Qualidade do sinal (camada 1). Janela reprovada -> SINAL_RUIM, sem aviso clínico.

Usa a janela bruta (para linha plana e saturação, que o filtro esconderia) e a janela
pré-processada (curtose, concordância entre detectores, número de batimentos e FC plausível).
Todas as medidas são relativas, sem depender de unidade ou offset.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import kurtosis

from src.config import load_config
from src.qrs import agreement, detect_qrs, detect_qrs_simple

S = load_config()["sqi"]
SQI_FEATURES = ["sqi_flat_frac", "sqi_clip_frac", "sqi_kurtosis", "sqi_qrs_agreement", "sqi_n_beats", "sqi_hr"]


def _flat_fraction(raw: np.ndarray, min_run: int) -> float:
    """Fração da janela coberta por trechos de ≥ min_run amostras sem variação."""
    d = np.diff(raw) == 0
    covered, run = 0, 0
    for v in d:
        if v:
            run += 1
        else:
            if run + 1 >= min_run:
                covered += run + 1
            run = 0
    if run + 1 >= min_run:
        covered += run + 1
    return covered / raw.size


def _clip_fraction(raw: np.ndarray) -> float:
    lo, hi = raw.min(), raw.max()
    if lo == hi:
        return 1.0
    return float(np.mean((raw == lo) | (raw == hi)))


def compute(raw: np.ndarray, x: np.ndarray, fs: float = 250.0, r: np.ndarray | None = None) -> dict:
    raw = np.asarray(raw, dtype=np.float64)
    if r is None:
        r = detect_qrs(x, fs)
    r2 = detect_qrs_simple(x, fs)
    hr = 60.0 * fs / np.median(np.diff(r)) if r.size >= 2 else np.nan
    return {
        "sqi_flat_frac": _flat_fraction(raw, int(0.2 * fs)),
        "sqi_clip_frac": _clip_fraction(raw),
        "sqi_kurtosis": float(kurtosis(x, fisher=False)) if np.ptp(x) > 0 else 0.0,
        "sqi_qrs_agreement": agreement(r, r2, fs),
        "sqi_n_beats": float(r.size),
        "sqi_hr": float(hr),
    }


def passes(q: dict) -> tuple[bool, list[str]]:
    """Regra do SQI. Retorna (aprovado, motivos de reprovação)."""
    why = []
    if q["sqi_flat_frac"] > S["max_flat_frac"]:
        why.append("linha_plana")
    if q["sqi_clip_frac"] > S["max_clip_frac"]:
        why.append("saturacao")
    if not (S["min_beats"] <= q["sqi_n_beats"] <= S["max_beats"]):
        why.append("n_batimentos")
    if not (np.isfinite(q["sqi_hr"]) and S["hr_range_bpm"][0] <= q["sqi_hr"] <= S["hr_range_bpm"][1]):
        why.append("fc_implausivel")
    if q["sqi_qrs_agreement"] < S["min_qrs_agreement"]:
        why.append("detectores_discordam")
    if q["sqi_kurtosis"] < S["min_kurtosis"]:
        why.append("curtose_baixa")
    return (not why), why
