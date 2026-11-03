"""Inferência a bordo: só numpy/scipy + o artefato JSON em models/. Não usa rede nem scikit-learn.

    from src.inference import predict
    predict(window)  # 2.400 amostras a 250 Hz, qualquer unidade/offset (ex.: A/D de 12 bits)
    -> {"estado", "prob_afib", "fc", "sqi", ...}

`predict` classifica UMA janela. Estados por janela: SINAL_RUIM, INCERTO, AFIB, AVISO_FC_BAIXA,
AVISO_FC_ALTA, OK. A janela AFIB isolada ainda não é alerta.

`Monitor` aplica a camada temporal sobre janelas consecutivas e devolve os estados do sistema:
    SINAL_RUIM | INCERTO | ALERTA_AFIB (AFIB em N de M janelas) | AVISO_FC_BAIXA | AVISO_FC_ALTA | OK
Uma janela AFIB ainda não confirmada pela votação aparece como INCERTO ("afib_em_confirmacao").

Protótipo de pesquisa e apoio à decisão. Não é dispositivo médico nem diagnóstico.
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import numpy as np

from src import features as F
from src import sqi as SQ
from src.preprocess import preprocess_window, resample_to_target
from src.qrs import detect_qrs

DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "afib_logreg_v1.json"


class AFibDetector:
    def __init__(self, model_path: str | Path = DEFAULT_MODEL):
        m = json.loads(Path(model_path).read_text(encoding="utf-8"))
        self.meta = m
        self.features = m["features"]
        self.stats = np.asarray(m["imputer_statistics"], float)
        self.ind = np.asarray(m["indicator_features"], int)
        self.mu, self.sd = np.asarray(m["scaler_mean"], float), np.asarray(m["scaler_scale"], float)
        self.coef, self.b = np.asarray(m["coef"], float), float(m["intercept"])
        self.pa, self.pb = float(m["platt_coef"]), float(m["platt_intercept"])
        self.thr, self.p_conf = float(m["threshold"]), float(m["p_confident"])
        self.ood_loc, self.ood_P = np.asarray(m["ood_location"], float), np.asarray(m["ood_precision"], float)
        self.ood_thr = float(m["ood_threshold"])
        self.sqi_cfg = m["sqi"]
        self.fs = float(m["signal"]["fs"])
        self.n = int(m["signal"]["window_samples"])
        self.hr_rule = m["hr_rule"]

    # ---- partes do modelo (vetorizadas: aceitam (n_janelas, n_atributos))
    def _z(self, X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, float))
        nan = np.isnan(X)
        imp = np.where(nan, self.stats, X)
        return (np.hstack([imp, nan[:, self.ind].astype(float)]) - self.mu) / self.sd

    def prob(self, X: np.ndarray) -> np.ndarray:
        logit = np.clip(self._z(X) @ self.coef + self.b, -13.815510557964274, 13.815510557964274)
        return 1.0 / (1.0 + np.exp(-(self.pa * logit + self.pb)))

    def ood_distance(self, X: np.ndarray) -> np.ndarray:
        d = self._z(X) - self.ood_loc
        return np.sqrt(np.einsum("ij,jk,ik->i", d, self.ood_P, d))

    # ---- uma janela
    def predict(self, window, fs: float | None = None) -> dict:
        t0 = time.perf_counter()
        x = np.asarray(window, dtype=float)
        if fs is not None and fs != self.fs:
            x = resample_to_target(x, fs, self.fs)
        if x.size < self.n:
            raise ValueError(f"janela precisa de {self.n} amostras a {self.fs:g} Hz (recebeu {x.size})")
        raw = x[-self.n :]
        w = preprocess_window(raw, self.fs)
        r = detect_qrs(w, self.fs)
        q = SQ.compute(raw, w, self.fs, r=r)
        ok, why = SQ.passes(q, self.sqi_cfg)
        f = F.extract(w, self.fs, r=r)
        hr = f["hr_median"]
        out = {"prob_afib": None, "fc": None if not np.isfinite(hr) else round(float(hr), 1),
               "sqi": {"aprovado": bool(ok), "motivos": why, **{k: round(float(v), 4) for k, v in q.items()}},
               "fora_do_padrao": None, "motivo": ""}
        if not ok:
            out.update(estado="SINAL_RUIM", motivo=",".join(why))
        else:
            X = np.array([[f[k] for k in self.features]], float)
            p = float(self.prob(X)[0])
            dist = float(self.ood_distance(X)[0])
            ood = dist > self.ood_thr
            out.update(prob_afib=round(p, 4), fora_do_padrao=bool(ood), distancia_padrao=round(dist, 2))
            if ood:
                out.update(estado="INCERTO", motivo="entrada_fora_do_padrao")
            elif p >= self.p_conf:
                out.update(estado="AFIB")
            elif p >= self.thr:
                out.update(estado="INCERTO", motivo="confianca_baixa")
            else:
                st = _hr_state(hr, self.hr_rule["brady_bpm"], self.hr_rule["tachy_bpm"])
                out.update(estado=st)
        out["latencia_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return out


def _hr_state(hr, brady, tachy):
    if not np.isfinite(hr):
        return "OK"
    return "AVISO_FC_BAIXA" if hr < brady else ("AVISO_FC_ALTA" if hr > tachy else "OK")


class Monitor:
    """Camada temporal: votação N de M para AFIB e regra de FC com histórico da própria pessoa.

    Regra de FC: limiares absolutos configuráveis; depois de `min_hist` janelas sinusais com sinal bom, o limiar de FC
    baixa passa a min(limiar, 0,8 × mediana pessoal) — atleta com FC de repouso baixa não recebe
    aviso contínuo — e o de FC alta, max(limiar, 1,5 × mediana pessoal). Avisos de FC são leves.
    """

    def __init__(self, detector: AFibDetector | None = None, n: int | None = None, m: int | None = None,
                 brady_bpm: float | None = None, tachy_bpm: float | None = None, min_hist: int = 30, hist_len: int = 375):
        self.det = detector or AFibDetector()
        v = self.det.meta["voting"]
        self.n, self.m = n or v["N"], m or v["M"]
        self.brady = brady_bpm or self.det.hr_rule["brady_bpm"]
        self.tachy = tachy_bpm or self.det.hr_rule["tachy_bpm"]
        self.votes = deque(maxlen=self.m)
        self.hr_hist = deque(maxlen=hist_len)  # ~1 h de janelas
        self.min_hist = min_hist
        self.alert_active = False
        self.i = 0

    def thresholds(self) -> tuple[float, float]:
        if len(self.hr_hist) >= self.min_hist:
            med = float(np.median(self.hr_hist))
            return min(self.brady, 0.8 * med), max(self.tachy, 1.5 * med)
        return self.brady, self.tachy

    def update(self, window, fs: float | None = None, t: float | None = None) -> dict:
        r = self.det.predict(window, fs)
        self.votes.append(r["estado"] == "AFIB")
        cond = sum(self.votes) >= self.n
        novo = cond and not self.alert_active
        self.alert_active = cond
        lo, hi = self.thresholds()
        if r["estado"] == "SINAL_RUIM":
            estado, sev = "SINAL_RUIM", "tecnica"
        elif cond:
            estado, sev = "ALERTA_AFIB", "alta"
        elif r["estado"] == "AFIB":
            estado, sev = "INCERTO", "revisar"
            r["motivo"] = f"afib_em_confirmacao ({sum(self.votes)} de {self.n} votos em {self.m} janelas)"
        elif r["estado"] == "INCERTO":
            estado, sev = "INCERTO", "revisar"
        else:
            hr = r["fc"] if r["fc"] is not None else float("nan")
            estado = _hr_state(hr, lo, hi)
            sev = "leve" if estado != "OK" else "nenhuma"
            if np.isfinite(hr):  # histórico pessoal: toda janela sinusal com sinal bom (inclusive com aviso de FC)
                self.hr_hist.append(hr)
        out = {"janela": self.i, "t_s": t, "estado": estado, "severidade": sev, "alerta_novo": bool(novo),
               "estado_janela": r["estado"], "prob_afib": r["prob_afib"], "fc": r["fc"], "sqi": r["sqi"],
               "motivo": r["motivo"], "limiares_fc": [round(lo, 1), round(hi, 1)], "latencia_ms": r["latencia_ms"]}
        self.i += 1
        return out


_DEFAULT: AFibDetector | None = None


def predict(window, fs: float | None = None) -> dict:
    """API simples: predict(window) -> {estado, prob_afib, fc, sqi, ...} para uma janela."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AFibDetector()
    return _DEFAULT.predict(window, fs)
