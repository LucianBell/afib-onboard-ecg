"""Pré-processamento único, idêntico em treino e inferência.

Fluxo de um registro da base (derivação I, mV, 500 Hz):
    resample_to_target  -> 250 Hz (resample_poly, com filtro anti-aliasing)
    crop                -> 2.400 amostras (9,6 s), central ou aleatório
    preprocess_window   -> remove offset, notch 50 Hz, Butterworth 0,05-30 Hz (SOS, sosfiltfilt),
                           normalização robusta

No aparelho (MP-IoT, AD8232) o sinal já chega a 250 Hz em janelas de 2.400 amostras de A/D,
e só `preprocess_window` é aplicado. Reamostrar *antes* de filtrar garante que treino e
aparelho passem exatamente pelos mesmos filtros a 250 Hz (decisão D20).

O pipeline não depende do offset absoluto: a mediana da janela é removida antes de qualquer
filtro, e a escala é normalizada por janela.
"""
from __future__ import annotations

from functools import lru_cache
from math import gcd

import numpy as np
from scipy.signal import butter, iirnotch, resample_poly, sosfiltfilt, tf2sos

from src.config import load_config

_CFG = load_config()
P = _CFG["preprocess"]
DEV = _CFG["device"]


@lru_cache(maxsize=8)
def _filters(fs: float) -> tuple[np.ndarray, np.ndarray]:
    b, a = iirnotch(P["notch_hz"], P["notch_q"], fs=fs)
    notch = tf2sos(b, a)
    band = butter(P["band_order"], P["band_hz"], btype="bandpass", fs=fs, output="sos")
    return notch, band


def resample_to_target(x: np.ndarray, fs_in: float, fs_out: float = P["fs"]) -> np.ndarray:
    if fs_in == fs_out:
        return np.asarray(x, dtype=np.float64)
    g = gcd(int(fs_in), int(fs_out))
    return resample_poly(np.asarray(x, dtype=np.float64), int(fs_out) // g, int(fs_in) // g, axis=-1)


def crop(x: np.ndarray, n: int = P["window"], mode: str = "center", rng: np.random.Generator | None = None) -> np.ndarray:
    if x.shape[-1] < n:
        raise ValueError(f"janela curta: {x.shape[-1]} < {n}")
    extra = x.shape[-1] - n
    if mode == "center":
        s = extra // 2
    elif mode == "random":
        s = int((rng or np.random.default_rng()).integers(0, extra + 1))
    else:
        raise ValueError(mode)
    return x[..., s : s + n]


def robust_scale(x: np.ndarray) -> float:
    """Escala robusta: diferença entre os percentis 99 e 1 (≈ amplitude do QRS)."""
    p1, p99 = np.percentile(x, [1, 99])
    return float(p99 - p1)


def filter_window(x: np.ndarray, fs: float = P["fs"]) -> np.ndarray:
    """Remove offset e aplica notch + passa-banda. Mantém a unidade de entrada."""
    x = np.asarray(x, dtype=np.float64)
    x = x - np.median(x)
    notch, band = _filters(float(fs))
    x = sosfiltfilt(notch, x)
    return sosfiltfilt(band, x)


def preprocess_window(x: np.ndarray, fs: float = P["fs"]) -> np.ndarray:
    """Janela pronta para atributos/modelo: filtrada, mediana zero, escala robusta = 1."""
    y = filter_window(x, fs)
    y = y - np.median(y)
    s = robust_scale(y)
    return (y / s if s > 0 else y).astype(np.float32)


def record_to_window(x_mv: np.ndarray, fs_in: float = P["fs_in_dataset"], mode: str = P["crop"],
                     rng: np.random.Generator | None = None) -> np.ndarray:
    """Registro de 10 s da base -> janela de 2.400 amostras a 250 Hz, pré-processada."""
    return preprocess_window(crop(resample_to_target(x_mv, fs_in), mode=mode, rng=rng))


def simulate_device(x_mv: np.ndarray, fs_in: float = P["fs_in_dataset"], rng: np.random.Generator | None = None,
                    dither: bool = False) -> np.ndarray:
    """Converte ECG em mV para o que o MP-IoT entregaria: 250 Hz, inteiros positivos de 12 bits.

    Modelo simplificado: ganho analógico do AD8232 (configurável), referência de A/D, offset no
    meio da escala, quantização e saturação. Não modela o filtro analógico do sensor.
    """
    y = resample_to_target(x_mv, fs_in)
    levels = 2 ** DEV["adc_bits"]
    lsb_mv = DEV["vref_v"] * 1000.0 / levels / DEV["analog_gain"]  # mV no eletrodo por LSB
    code = y / lsb_mv + DEV["offset_frac"] * levels
    if dither:
        code = code + (rng or np.random.default_rng()).uniform(-0.5, 0.5, size=code.shape)
    return np.clip(np.round(code), 0, levels - 1).astype(np.int32)
