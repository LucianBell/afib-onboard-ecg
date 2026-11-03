"""ECG sintético simples para testes: soma de gaussianas P-QRS-T em instantes conhecidos."""
from __future__ import annotations

import numpy as np


def synth_ecg(rr_s, fs=250.0, n=2400, p_wave=True, polarity=1.0, noise=0.0, seed=0, start=0.3):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    x = np.zeros(n)
    r_times = []
    tr = start
    i = 0
    while tr < n / fs - 0.05:
        r_times.append(tr)
        comps = [(0.0, 0.012, 1.0), (-0.03, 0.01, -0.12), (0.03, 0.01, -0.18), (0.25, 0.05, 0.3)]
        if p_wave:
            comps.append((-0.16, 0.025, 0.15))
        for dt, sd, a in comps:
            x += a * np.exp(-0.5 * ((t - tr - dt) / sd) ** 2)
        tr += rr_s[i % len(rr_s)]
        i += 1
    x = polarity * x
    if noise:
        x += noise * rng.standard_normal(n)
    r_idx = np.array([int(round(rt * fs)) for rt in r_times])
    return x, r_idx


def irregular_rr(mean=0.7, cv=0.2, n=40, seed=0):
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(mean, cv * mean, n), 0.3, 1.6)
