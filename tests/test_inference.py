import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.inference import DEFAULT_MODEL, AFibDetector, Monitor, predict
from src.preprocess import crop, simulate_device
from tests.synth import irregular_rr, synth_ecg

CFG = load_config()
pytestmark = pytest.mark.skipif(not DEFAULT_MODEL.exists(), reason="modelo ainda não exportado (make export)")
JOBLIB = CFG["paths"]["processed"] / "expA_models" / "logreg.joblib"
FEATS = CFG["paths"]["processed"] / "chapman_features.parquet"


@pytest.mark.skipif(not (JOBLIB.exists() and FEATS.exists()), reason="artefatos do experimento A ausentes")
def test_json_model_matches_sklearn_pipeline():
    import joblib

    art = joblib.load(JOBLIB)
    det = AFibDetector()
    f = pd.read_parquet(FEATS).sample(2000, random_state=0)
    ref = art["calibrator"].transform(art["model"].predict_proba(f[det.features])[:, 1])
    np.testing.assert_allclose(det.prob(f[det.features].to_numpy()), ref, atol=1e-9)


def test_predict_keys_and_offset_invariance():
    x, _ = synth_ecg([0.8], noise=0.01, seed=1)
    a, b = predict(x), predict(x + 2048.0)
    for k in ["estado", "prob_afib", "fc", "sqi"]:
        assert k in a
    assert a["estado"] == b["estado"] and a["prob_afib"] == pytest.approx(b["prob_afib"], abs=1e-6)
    assert a["fc"] == pytest.approx(75, abs=2)


def test_device_adc_input():
    x500, _ = synth_ecg(list(irregular_rr(0.7, 0.25, seed=2)), fs=500, n=5000, noise=0.01, seed=3, p_wave=False)
    dev = crop(simulate_device(x500))
    r = predict(dev)
    assert r["sqi"]["aprovado"] and r["prob_afib"] is not None


def test_resampling_input_and_short_window():
    x500, _ = synth_ecg([0.8], fs=500, n=5000, noise=0.01, seed=4)
    assert predict(x500, fs=500)["fc"] == pytest.approx(75, abs=2)
    with pytest.raises(ValueError):
        predict(np.zeros(100))


def test_flat_and_saturated_are_bad_signal():
    assert predict(np.full(2400, 2048.0))["estado"] == "SINAL_RUIM"
    x, _ = synth_ecg([0.8], seed=5)
    assert predict(np.clip(x * 50, -1, 1))["estado"] == "SINAL_RUIM"


class _Stub:
    """Detector falso: devolve a sequência de estados de janela pedida."""

    def __init__(self, states, fc=72.0):
        self.states, self.k, self.fc = list(states), 0, fc
        self.meta = {"voting": {"N": 3, "M": 3}}
        self.hr_rule = {"brady_bpm": 60, "tachy_bpm": 100}

    def predict(self, window, fs=None):
        s = self.states[self.k]
        self.k += 1
        fc = self.fc if not isinstance(s, tuple) else s[1]
        s = s if not isinstance(s, tuple) else s[0]
        return {"estado": s, "prob_afib": 0.9 if s == "AFIB" else 0.0, "fc": fc, "sqi": {}, "motivo": "", "latencia_ms": 1}


def test_monitor_voting_and_states():
    seq = ["OK", "AFIB", "AFIB", "AFIB", "AFIB", "OK", "SINAL_RUIM", "AFIB", "AFIB", "AFIB"]
    mon = Monitor(_Stub(seq))
    out = [mon.update(None) for _ in seq]
    assert [o["estado"] for o in out] == ["OK", "INCERTO", "INCERTO", "ALERTA_AFIB", "ALERTA_AFIB", "OK",
                                          "SINAL_RUIM", "INCERTO", "INCERTO", "ALERTA_AFIB"]
    assert [o["alerta_novo"] for o in out].count(True) == 2


def test_monitor_hr_rule_adapts_to_personal_history():
    # atleta: FC de repouso 50 bpm -> aviso no início, depois o limiar se adapta à mediana pessoal
    seq = [("OK", 50.0)] * 40
    mon = Monitor(_Stub(seq), min_hist=30)
    out = [mon.update(None) for _ in seq]
    assert out[0]["estado"] == "AVISO_FC_BAIXA"
    assert out[-1]["estado"] == "OK"  # mediana pessoal 50 -> limiar baixo = min(60, 40)
    seq = [("OK", 50.0)] * 35 + [("OK", 38.0)]
    mon = Monitor(_Stub(seq), min_hist=30)
    assert [mon.update(None) for _ in seq][-1]["estado"] == "AVISO_FC_BAIXA"  # queda > 20% da mediana pessoal
    seq = [("OK", 62.0)] * 35 + [("OK", 52.0)]
    mon = Monitor(_Stub(seq), min_hist=30)
    out = [mon.update(None) for _ in seq]
    assert out[-1]["estado"] == "OK"  # 52 >= 0,8 x 62 = 49,6 -> sem aviso
