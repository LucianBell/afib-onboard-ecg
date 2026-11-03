"""Baseline sem aprendizado e regra de frequência cardíaca.

Baseline RR: o escore de irregularidade é o RMSSD normalizado pelo RR médio (nRMSSD), uma das
medidas clássicas de irregularidade usadas em detecção de AFIB por intervalos RR. Não há
treino: a única grandeza ajustada é o limiar de decisão, escolhido na validação pela mesma regra
usada para os modelos de ML (decisão D24).

Regra de FC (camada 3): aviso leve de FC baixa/alta, com limiares configuráveis.
"""
from __future__ import annotations

import numpy as np

from src.config import load_config

H = load_config()["hr_rule"]


def rr_irregularity_score(feats) -> np.ndarray:
    """nRMSSD; janelas sem batimentos suficientes recebem 0 (tratadas como regulares)."""
    s = np.asarray(feats["nrmssd"], dtype=float)
    return np.where(np.isfinite(s), s, 0.0)


def hr_state(hr: float, brady: float = H["brady_bpm"], tachy: float = H["tachy_bpm"]) -> str:
    if not np.isfinite(hr):
        return "FC_INDEFINIDA"
    if hr < brady:
        return "AVISO_FC_BAIXA"
    if hr > tachy:
        return "AVISO_FC_ALTA"
    return "OK"
