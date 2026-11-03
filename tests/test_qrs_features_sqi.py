import numpy as np
import pytest

from src import baseline, features, sqi
from src.preprocess import preprocess_window
from src.qrs import agreement, detect_qrs, match_beats
from tests.synth import irregular_rr, synth_ecg

FS = 250.0


def _sens_ppv(det, ref, tol_ms=50):
    m = match_beats(ref, det, FS, tol_ms)
    return m / len(ref), m / max(len(det), 1)


@pytest.mark.parametrize("rr,polarity,noise", [
    ([0.8], 1, 0.0), ([0.45], 1, 0.02), ([1.3], 1, 0.02), ([0.8], -1, 0.02),
    (list(irregular_rr(0.7, 0.25, seed=1)), 1, 0.03), (list(irregular_rr(0.5, 0.2, seed=2)), -1, 0.03),
])
def test_qrs_detector_synthetic(rr, polarity, noise):
    x, ref = synth_ecg(rr, polarity=polarity, noise=noise, seed=7)
    det = detect_qrs(preprocess_window(x), FS)
    se, ppv = _sens_ppv(det, ref)
    assert se >= 0.95 and ppv >= 0.95, (se, ppv, len(det), len(ref))


def test_qrs_empty_and_flat():
    assert detect_qrs(np.zeros(2400), FS).size == 0
    assert detect_qrs(np.zeros(10), FS).size == 0


def test_rr_features_regular_vs_irregular():
    xr, _ = synth_ecg([0.8], noise=0.01, seed=1)
    xi, _ = synth_ecg(list(irregular_rr(0.8, 0.25, seed=3)), noise=0.01, seed=1)
    fr = features.extract(preprocess_window(xr))
    fi = features.extract(preprocess_window(xi))
    assert fr["hr_median"] == pytest.approx(75, abs=2)
    assert fr["nrmssd"] < 0.02 < 0.1 < fi["nrmssd"]
    assert fr["cv_rr"] < fi["cv_rr"]
    assert set(fr) == set(features.FEATURE_NAMES)


def test_p_wave_feature_detects_absent_p():
    xp, _ = synth_ecg([0.8], p_wave=True, noise=0.005, seed=1)
    xn, _ = synth_ecg([0.8], p_wave=False, noise=0.005, seed=1)
    assert features.extract(preprocess_window(xp))["p_amp_rel"] > 2 * features.extract(preprocess_window(xn))["p_amp_rel"]


def test_sqi_clean_passes_and_bad_fails():
    x, _ = synth_ecg([0.8], noise=0.01, seed=1)
    ok, why = sqi.passes(sqi.compute(x, preprocess_window(x)))
    assert ok, why
    flat = np.full(2400, 2048.0)
    ok, why = sqi.passes(sqi.compute(flat, preprocess_window(flat)))
    assert not ok and "linha_plana" in why
    noise = np.random.default_rng(0).standard_normal(2400)
    ok, why = sqi.passes(sqi.compute(noise, preprocess_window(noise)))
    assert not ok
    sat = np.clip(x * 50, -1, 1)
    ok, why = sqi.passes(sqi.compute(sat, preprocess_window(sat)))
    assert not ok and "saturacao" in why


def test_agreement_bounds():
    a = np.array([10, 200, 400])
    assert agreement(a, a) == 1.0
    assert agreement(a, np.array([])) == 0.0


def test_baseline_and_hr_rule():
    assert baseline.rr_irregularity_score({"nrmssd": np.array([0.1, np.nan])}).tolist() == [0.1, 0.0]
    assert baseline.hr_state(45) == "AVISO_FC_BAIXA"
    assert baseline.hr_state(130) == "AVISO_FC_ALTA"
    assert baseline.hr_state(72) == "OK"
    assert baseline.hr_state(np.nan) == "FC_INDEFINIDA"
