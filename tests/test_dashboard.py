"""O painel executa sem erro, mostra a faixa fixa e reage à troca de cenário (AppTest, sem navegador)."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.inference import DEFAULT_MODEL  # noqa: E402

pytestmark = pytest.mark.skipif(not DEFAULT_MODEL.exists(), reason="modelo ainda não exportado")


def _run():
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _texts(at):
    return " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)


def test_dashboard_runs_and_shows_banner():
    at = _run()
    txt = _texts(at)
    assert "Não são dados de astronautas" in txt
    assert "não é dispositivo médico" in txt
    assert any(m.label == "Frequência cardíaca" for m in at.metric)


def test_dashboard_scenario_switch_to_afib_raises_alert():
    at = _run()
    at.toggle[0].set_value(False).run()          # pausa a reprodução automática
    next(b for b in at.button if b.label == "Fibrilação atrial").click().run()
    for _ in range(6):
        next(b for b in at.button if b.label == "Avançar 1 janela").click().run()
        assert not at.exception, at.exception
    states = [h["estado"] for h in at.session_state["hist"]]
    assert "ALERTA_AFIB" in states, states
    assert at.session_state["events"], "o alerta deveria aparecer no histórico"


def test_dashboard_bad_signal_scenario():
    at = _run()
    at.toggle[0].set_value(False).run()
    next(b for b in at.button if b.label == "Sinal ruim").click().run()
    for _ in range(8):
        next(b for b in at.button if b.label == "Avançar 1 janela").click().run()
    states = [h["estado"] for h in at.session_state["hist"] if h["cenario"] == "sinal_ruim"]
    assert "SINAL_RUIM" in states, states
