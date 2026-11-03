"""Métricas de AFIB, IC por bootstrap, calibração e escolha de limiar."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def threshold_for_specificity(y: np.ndarray, p: np.ndarray, min_spec: float) -> float:
    """Menor limiar com especificidade ≥ min_spec (máxima sensibilidade sob a restrição).

    Predição positiva = p >= limiar.
    """
    y, p = np.asarray(y).astype(bool), np.asarray(p, dtype=float)
    neg = np.sort(p[~y])
    k = int(np.floor((1 - min_spec) * neg.size))  # nº de falsos positivos permitidos
    if k == 0:
        return float(np.nextafter(neg[-1], np.inf))
    # limiar logo acima do (k+1)-ésimo maior negativo -> no máximo k negativos >= limiar
    t = neg[neg.size - k - 1]
    return float(np.nextafter(t, np.inf))


def confusion(y, pred) -> dict:
    y, pred = np.asarray(y).astype(bool), np.asarray(pred).astype(bool)
    return {"tp": int((y & pred).sum()), "fp": int((~y & pred).sum()),
            "tn": int((~y & ~pred).sum()), "fn": int((y & ~pred).sum())}


def _div(a, b):
    return a / b if b else float("nan")


def point_metrics(y, p, thr) -> dict:
    y = np.asarray(y).astype(bool)
    p = np.asarray(p, dtype=float)
    c = confusion(y, p >= thr)
    sens, spec = _div(c["tp"], c["tp"] + c["fn"]), _div(c["tn"], c["tn"] + c["fp"])
    ppv, npv = _div(c["tp"], c["tp"] + c["fp"]), _div(c["tn"], c["tn"] + c["fn"])
    f1 = _div(2 * ppv * sens, ppv + sens) if np.isfinite(ppv) else float("nan")
    out = {"sensibilidade": sens, "especificidade": spec, "ppv": ppv, "npv": npv, "f1": f1, **c}
    if y.any() and (~y).any():
        out["auroc"] = float(roc_auc_score(y, p))
        out["auprc"] = float(average_precision_score(y, p))
    return out


def brier(y, p) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def ece(y, p, n_bins: int = 10) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    bins = np.minimum((p * n_bins).astype(int), n_bins - 1)
    e = 0.0
    for b in range(n_bins):
        m = bins == b
        if m.any():
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(e)


def ppv_at_prevalence(sens: float, spec: float, prev: float) -> float:
    return _div(sens * prev, sens * prev + (1 - spec) * (1 - prev))


KEYS = ["sensibilidade", "especificidade", "ppv", "npv", "f1", "auroc", "auprc"]


def bootstrap(y, p, thr, n: int = 2000, seed: int = 0, calib: bool = False) -> dict:
    """IC 95% percentil por reamostragem de registros (estratificada por classe)."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y).astype(bool)
    p = np.asarray(p, float)
    pos, neg = np.flatnonzero(y), np.flatnonzero(~y)
    keys = KEYS + (["brier", "ece"] if calib else [])
    acc = {k: [] for k in keys}
    for _ in range(n):
        i = np.concatenate([rng.choice(pos, pos.size), rng.choice(neg, neg.size)])
        m = point_metrics(y[i], p[i], thr)
        if calib:
            m["brier"], m["ece"] = brier(y[i], p[i]), ece(y[i], p[i])
        for k in keys:
            acc[k].append(m.get(k, np.nan))
    return {k: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))] for k, v in acc.items()}


def full_report(y, p, thr, n_boot=2000, seed=0, prevalences=(0.001, 0.01, 0.05), calib=True) -> dict:
    m = point_metrics(y, p, thr)
    if calib:
        m["brier"], m["ece"] = brier(y, p), ece(y, p)
    m["limiar"] = float(thr)
    m["n_pos"], m["n_neg"] = int(np.sum(y)), int(np.size(y) - np.sum(y))
    m["ic95"] = bootstrap(y, p, thr, n_boot, seed, calib)
    m["ppv_prevalencia"] = {f"{q:g}": ppv_at_prevalence(m["sensibilidade"], m["especificidade"], q) for q in prevalences}
    return m


def mcnemar(correct_a, correct_b) -> dict:
    """McNemar exato (binomial) entre dois classificadores no mesmo conjunto."""
    from scipy.stats import binomtest

    a, b = np.asarray(correct_a, bool), np.asarray(correct_b, bool)
    n01, n10 = int((a & ~b).sum()), int((~a & b).sum())
    pval = binomtest(n01, n01 + n10, 0.5).pvalue if n01 + n10 else 1.0
    return {"so_a_acerta": n01, "so_b_acerta": n10, "p_valor": float(pval)}
