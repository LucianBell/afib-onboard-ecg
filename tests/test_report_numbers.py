"""Regra de integridade: todo número do README/MODEL_CARD vem de um arquivo em results/ (ou de uma
constante de projeto em configs/), por meio de scripts/make_report.py."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
make_report = pytest.importorskip("make_report")

# números escritos à mão permitidos fora dos marcadores (não são resultados):
ALLOWED = {
    "2026",  # ano da competição
    "2025", "2022", "2023", "2021",  # anos de publicações citadas (artigos, TCC, CinC 2021)
    "1.0.0", "1.0.3",  # versões das bases na PhysioNet
    "1",  # "afib_logreg_v1" (nome do artefato)
}


def _strip(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)       # blocos de código (comandos)
    text = re.sub(r"`[^`]*`", " ", text)                      # código em linha (caminhos, comandos)
    text = re.sub(r"\]\([^)]*\)", "]", text)                   # destinos de links
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\{\{\w+\}\}", " ", text)                   # marcadores
    text = re.sub(r"\bpt-BR\b|\b1D\b|\bL2\b|\bp95\b|SHA-256", " ", text)  # nomes que contêm dígitos
    text = re.sub(r"95% (?:bootstrap )?CI", " ", text)         # nível de confiança (método, não resultado)
    text = re.sub(r"(?m)^\s*\d+\.\s", " ", text)                # numeração de lista
    return text


@pytest.mark.parametrize("doc,tpl", list(make_report.DOCS.items()))
def test_template_has_no_hand_written_numbers(doc, tpl):
    t = _strip((ROOT / "docs" / "templates" / tpl).read_text(encoding="utf-8"))
    nums = set(re.findall(r"\d+(?:[.,]\d+)*", t))
    assert nums <= ALLOWED, f"{tpl}: números fora de marcadores: {sorted(nums - ALLOWED)}"


def test_documents_match_render_from_results():
    out, V = make_report.build()
    for doc, txt in out.items():
        assert (ROOT / doc).read_text(encoding="utf-8") == txt, f"{doc} difere do gerado a partir de results/ (rode make report)"


def test_every_value_has_a_results_or_config_source():
    _, V = make_report.build()
    for k, v in V.v.items():
        srcs = re.split(r"\s*\+\s*", v["fonte"])
        assert all(s.startswith(("results/", "configs/default.yaml", "src/features.py")) for s in srcs), (k, v["fonte"])
        for s in srcs:
            assert (ROOT / s).exists(), (k, s)
