import numpy as np
import pytest
from scipy.signal import welch

from src import features, preprocess
from src.preprocess import preprocess_window, record_to_window, simulate_device
from tests.synth import irregular_rr, synth_ecg


def _record_500hz(seed=0):
    x, _ = synth_ecg([0.8], fs=500, n=5000, seed=seed, noise=0.01)
    return 0.8 * x  # ~mV


def test_shapes_and_dtype():
    w = record_to_window(_record_500hz())
    assert w.shape == (2400,) and w.dtype == np.float32
    assert np.isfinite(w).all()


@pytest.mark.parametrize("c", [1.0, 37.5, 2048.0, 1e4])
def test_offset_invariance_window(c):
    x, _ = synth_ecg(irregular_rr(seed=3), noise=0.02, seed=1)
    a = preprocess_window(x)
    b = preprocess_window(x + c)
    np.testing.assert_allclose(a, b, atol=1e-4)


@pytest.mark.parametrize("c", [0.5, 1000.0])
def test_offset_invariance_features(c):
    x, _ = synth_ecg(irregular_rr(seed=4), noise=0.02, seed=2)
    fa = features.extract(preprocess_window(x))
    fb = features.extract(preprocess_window(x + c))
    for k in features.FEATURE_NAMES:
        if np.isfinite(fa[k]):
            assert fb[k] == pytest.approx(fa[k], rel=1e-3, abs=1e-5), k


def test_scale_invariance():
    x, _ = synth_ecg([0.75], noise=0.01, seed=5)
    np.testing.assert_allclose(preprocess_window(x), preprocess_window(250.0 * x), atol=1e-4)


def test_notch_removes_50hz():
    fs = 250
    t = np.arange(2400) / fs
    x, _ = synth_ecg([0.8], seed=6)
    y = preprocess_window(x + 0.5 * np.sin(2 * np.pi * 50 * t))
    f, p = welch(y, fs=fs, nperseg=512)
    ref = preprocess_window(x)
    f, p0 = welch(ref, fs=fs, nperseg=512)
    k = np.argmin(np.abs(f - 50))
    assert p[k] < 10 * p0[k] + 1e-8


def test_resample_and_crop():
    x = np.random.default_rng(0).standard_normal(5000)
    y = preprocess.resample_to_target(x, 500)
    assert y.shape == (2500,)
    assert preprocess.crop(y).shape == (2400,)
    with pytest.raises(ValueError):
        preprocess.crop(y[:100])


def test_simulate_device_positive_12bit_and_compatible():
    rec = _record_500hz()
    dev = simulate_device(rec)
    assert dev.dtype == np.int32 and dev.min() >= 0 and dev.max() <= 4095
    assert dev.shape == (2500,)
    # a janela do aparelho, pré-processada, deve ser quase igual à da base
    w_dev = preprocess_window(preprocess.crop(dev.astype(float)))
    w_ref = record_to_window(rec)
    assert np.corrcoef(w_dev, w_ref)[0, 1] > 0.99
