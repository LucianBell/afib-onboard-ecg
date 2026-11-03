"""Fonte de sinal para a demonstração (simulação de stream e painel). Funciona sem internet.

Duas fontes:
- **replay** (padrão): `data/demo/demo_pack.npz`, gerado por `make demo-data` a partir de registros do
  teste do experimento A (Chapman-Shaoxing, nunca vistos no treino), convertidos para o que o aparelho
  entregaria (250 Hz, A/D de 12 bits, só valores positivos). Dados clínicos públicos, terrestres, de repouso.
  "Sinal ruim" = registros sinusais com ruído real da MIT-BIH NSTDB a −6 dB ou eletrodo solto.
- **sintética**: ECG sintético simples (sem dados reais), para clones sem as bases baixadas.

A transmissão Holter → Pi está fora do escopo: o stream é a concatenação de registros de 10 s de
pacientes diferentes, com transições artificiais entre eles.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.config import ROOT
from src.preprocess import DEV

PACK = ROOT / "data" / "demo" / "demo_pack.npz"
SCENARIOS = ["sinusal", "afib", "bradicardia", "taquicardia", "sinal_ruim"]
LABELS = {"sinusal": "Ritmo sinusal", "afib": "Fibrilação atrial", "bradicardia": "Bradicardia sinusal",
          "taquicardia": "Taquicardia sinusal", "sinal_ruim": "Sinal ruim"}
FS = 250
REC = 2500  # 10 s a 250 Hz
BANNER_REPLAY = "Replay de dados clínicos públicos. Não são dados de astronautas."
BANNER_SYNTH = "Sinal SINTÉTICO gerado por código (sem dados reais). Não são dados de astronautas."


def _to_adc(x_mv: np.ndarray) -> np.ndarray:
    levels = 2 ** DEV["adc_bits"]
    lsb = DEV["vref_v"] * 1000.0 / levels / DEV["analog_gain"]
    return np.clip(np.round(x_mv / lsb + DEV["offset_frac"] * levels), 0, levels - 1).astype(np.int16)


def synthetic_pack(n: int = 30, seed: int = 0) -> dict:
    """ECG sintético por cenário (gaussianas P-QRS-T; AFIB sem P, RR irregular e ondas f)."""
    rng = np.random.default_rng(seed)
    t = np.arange(REC) / FS

    def beat_train(rr_fn, p_wave, fwave=0.0):
        x = np.zeros(REC)
        tr = rng.uniform(0.1, 0.6)
        while tr < REC / FS:
            comps = [(0, 0.012, 1.0), (-0.03, 0.01, -0.12), (0.03, 0.01, -0.18), (0.25, 0.05, 0.3)]
            if p_wave:
                comps.append((-0.16, 0.025, 0.15))
            for dt, sd, a in comps:
                x += a * np.exp(-0.5 * ((t - tr - dt) / sd) ** 2)
            tr += rr_fn()
        if fwave:
            x += fwave * np.sin(2 * np.pi * rng.uniform(5, 7) * t + rng.uniform(0, 6)) * (1 + 0.3 * rng.standard_normal(REC).cumsum() / 50)
        return 0.9 * x + 0.01 * rng.standard_normal(REC) + 0.1 * np.sin(2 * np.pi * 0.2 * t + rng.uniform(0, 6))

    out = {}
    mk = {
        "sinusal": lambda: beat_train(lambda: rng.normal(0.85, 0.02), True),
        "afib": lambda: beat_train(lambda: float(np.clip(rng.normal(0.65, 0.17), 0.33, 1.4)), False, 0.05),
        "bradicardia": lambda: beat_train(lambda: rng.normal(1.25, 0.03), True),
        "taquicardia": lambda: beat_train(lambda: rng.normal(0.5, 0.01), True),
    }
    for k, f in mk.items():
        out[k] = np.stack([_to_adc(f()) for _ in range(n)])
    bad = []
    for i in range(n):
        if i % 2:
            bad.append(np.full(REC, 2 ** DEV["adc_bits"] - 1, np.int16))  # eletrodo solto: saturação
        else:
            bad.append(_to_adc(mk["sinusal"]() + 1.5 * np.cumsum(rng.standard_normal(REC)) / 30 + 0.8 * rng.standard_normal(REC)))
    out["sinal_ruim"] = np.stack(bad)
    return {"windows": out, "ids": {k: [f"sintetico_{k}_{i}" for i in range(n)] for k in out},
            "banner": BANNER_SYNTH, "fonte": "sintetica"}


def load_pack(path: Path = PACK) -> dict:
    z = np.load(path, allow_pickle=False)
    return {"windows": {k: z[f"w_{k}"] for k in SCENARIOS}, "ids": {k: z[f"id_{k}"].tolist() for k in SCENARIOS},
            "banner": BANNER_REPLAY, "fonte": "replay"}


def get_pack(prefer_replay: bool = True) -> dict:
    return load_pack() if (prefer_replay and PACK.exists()) else synthetic_pack()


class Stream:
    """Stream contínuo a 250 Hz montado com registros de 10 s do cenário atual, com janela deslizante.

    Por padrão a janela anda de registro em registro (passo 2.500, deslocamento 50), então cada janela
    de 2.400 amostras fica dentro de um registro. Com passo menor, as janelas cruzam as emendas
    (transições artificiais).
    """

    def __init__(self, pack: dict, scenario: str = "sinusal", stride: int = REC, offset: int = 50, seed: int = 0):
        self.pack, self.scenario, self.stride = pack, scenario, stride
        self.rng = np.random.default_rng(seed)
        self.buf = np.empty(0, np.float64)
        self.pos = offset
        self.t = 0.0
        self.src_ids: list[str] = []

    def set_scenario(self, s: str):
        self.scenario = s

    def _append_record(self):
        w = self.pack["windows"][self.scenario]
        i = int(self.rng.integers(0, len(w)))
        self.buf = np.concatenate([self.buf, w[i].astype(np.float64)])
        self.src_ids.append(str(self.pack["ids"][self.scenario][i]))

    def next_window(self, n: int = 2400) -> tuple[np.ndarray, float]:
        while self.buf.size < self.pos + n:
            self._append_record()
        win = self.buf[self.pos : self.pos + n].copy()
        t = self.t
        self.pos += self.stride
        self.t += self.stride / FS
        if self.pos > 4 * REC:  # descarta o passado para não crescer sem limite
            cut = self.pos - REC
            self.buf, self.pos = self.buf[cut:], self.pos - cut
        return win, t
