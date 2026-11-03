"""Somar uma constante positiva ao sinal não altera a predição do modelo treinado (briefing, seção 6)."""
import numpy as np
import pandas as pd
import pytest

from src import features
from src.config import load_config
from src.preprocess import crop, preprocess_window, resample_to_target, simulate_device
from tests.synth import irregular_rr, synth_ecg

CFG = load_config()
MOD = CFG["paths"]["processed"] / "expA_models"
FEATURE_MODELS = [m for m in ["logreg", "random_forest", "lightgbm"] if (MOD / f"{m}.joblib").exists()]


def _prob(art, raw_window):
    f = pd.DataFrame([features.extract(preprocess_window(raw_window))])[features.FEATURE_NAMES]
    return float(art["calibrator"].transform(art["model"].predict_proba(f)[:, 1])[0])


@pytest.mark.skipif(not FEATURE_MODELS, reason="modelos do experimento A ainda não treinados")
@pytest.mark.parametrize("name", FEATURE_MODELS)
@pytest.mark.parametrize("c", [0.7, 512.0, 2048.0])
def test_constant_offset_does_not_change_prediction(name, c):
    import joblib

    art = joblib.load(MOD / f"{name}.joblib")
    for seed, rr in [(1, [0.8]), (2, list(irregular_rr(0.6, 0.25, seed=5)))]:
        x, _ = synth_ecg(rr, noise=0.02, seed=seed)
        assert _prob(art, x + c) == pytest.approx(_prob(art, x), abs=1e-6)


@pytest.mark.skipif(not FEATURE_MODELS, reason="modelos do experimento A ainda não treinados")
def test_device_units_give_same_decision():
    import joblib

    art = joblib.load(MOD / f"{FEATURE_MODELS[0]}.joblib")
    for seed, rr in [(3, [0.9]), (4, list(irregular_rr(0.7, 0.3, seed=6)))]:
        x500, _ = synth_ecg(rr, fs=500, n=5000, noise=0.01, seed=seed)
        mv = crop(resample_to_target(x500, 500))
        dev = crop(simulate_device(x500).astype(float))  # inteiros positivos de 12 bits
        p_mv, p_dev = _prob(art, mv), _prob(art, dev)
        assert (p_mv >= art["threshold"]) == (p_dev >= art["threshold"])
        assert abs(p_mv - p_dev) < 0.05
