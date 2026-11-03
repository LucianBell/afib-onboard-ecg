"""Camada de decisão: estado por janela, entrada fora do padrão e votação temporal N de M.

Estado por janela (antes da votação):
    SINAL_RUIM  SQI reprovado
    INCERTO     entrada fora do padrão (Mahalanobis > quantil da validação) ou
                confiança baixa (limiar <= prob < p_confident)
    AFIB        prob >= p_confident, dentro do padrão
    NAO_AFIB    prob < limiar

Só janelas AFIB votam. ALERTA_AFIB dispara quando há >= N votos nas últimas M janelas (borda de
subida: um alerta por episódio contínuo da condição).
"""
from __future__ import annotations

import numpy as np
from sklearn.covariance import LedoitWolf

from src.config import load_config

D = load_config()["decision"]


class OODDetector:
    """Distância de Mahalanobis no espaço dos atributos já imputados/padronizados do pipeline."""

    def __init__(self, pipeline):
        self.pre = pipeline[:-1]  # imputação (+ indicadores) e padronização, ajustados no treino

    def fit(self, X_train, X_val, q: float = D["ood_quantile"]):
        self.cov = LedoitWolf().fit(self.pre.transform(X_train))
        self.threshold = float(np.quantile(self.distance(X_val), q))
        return self

    def distance(self, X) -> np.ndarray:
        return np.sqrt(self.cov.mahalanobis(self.pre.transform(X)))

    def is_ood(self, X) -> np.ndarray:
        return self.distance(X) > self.threshold


def window_states(sqi_ok, p, thr, ood, p_confident: float = D["p_confident"]) -> np.ndarray:
    sqi_ok, p, ood = np.asarray(sqi_ok, bool), np.asarray(p, float), np.asarray(ood, bool)
    s = np.full(p.shape, "NAO_AFIB", dtype=object)
    s[p >= p_confident] = "AFIB"
    s[(p >= thr) & (p < p_confident)] = "INCERTO"
    s[ood] = "INCERTO"
    s[~sqi_ok] = "SINAL_RUIM"
    return s


def rolling_votes(votes: np.ndarray, m: int) -> np.ndarray:
    """Soma de votos nas últimas m janelas (inclusive a atual). votes: (..., T) booleano."""
    v = np.asarray(votes, dtype=np.int32)
    c = np.cumsum(v, axis=-1)
    out = c.copy()
    out[..., m:] = c[..., m:] - c[..., :-m]
    return out


def alert_condition(votes: np.ndarray, n: int, m: int) -> np.ndarray:
    return rolling_votes(votes, m) >= n


def count_alerts(cond: np.ndarray) -> np.ndarray:
    """Número de alertas (bordas de subida da condição) ao longo do último eixo."""
    c = np.asarray(cond, bool)
    prev = np.concatenate([np.zeros(c.shape[:-1] + (1,), bool), c[..., :-1]], axis=-1)
    return (c & ~prev).sum(axis=-1)


def false_alerts_per_day(neg_votes: np.ndarray, n: int, m: int, windows_per_day: int, days: int,
                         rng: np.random.Generator) -> np.ndarray:
    """Simula `days` dias de janelas negativas independentes (amostradas com reposição)."""
    out = np.empty(days)
    for d in range(days):
        v = neg_votes[rng.integers(0, neg_votes.size, windows_per_day)]
        out[d] = count_alerts(alert_condition(v, n, m))
    return out


def episode_detection(neg_votes: np.ndarray, pos_votes: np.ndarray, n: int, m: int, length: int,
                      n_episodes: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Episódios sintéticos: M janelas sinusais seguidas de `length` janelas de AFIB (registros
    concatenados de pacientes diferentes). Retorna (detectado, janela do 1º alerta no episódio)."""
    pre = neg_votes[rng.integers(0, neg_votes.size, (n_episodes, m))]
    epi = pos_votes[rng.integers(0, pos_votes.size, (n_episodes, length))]
    cond = alert_condition(np.concatenate([pre, epi], axis=1), n, m)[:, m:]
    det = cond.any(axis=1)
    first = np.where(det, cond.argmax(axis=1) + 1, -1)
    return det, first
