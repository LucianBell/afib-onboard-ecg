"""Painel de demonstração do monitor de AFIB a bordo (roda sem internet).

    streamlit run app/dashboard.py        (ou: make demo)

Replay de registros clínicos públicos (teste do experimento A) convertidos para o formato do aparelho,
ou sinal sintético se o pacote de demonstração não existir. Protótipo de pesquisa; não é dispositivo
médico nem diagnóstico; não são dados de astronautas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.demo import LABELS, PACK, SCENARIOS, Stream, get_pack  # noqa: E402
from src.inference import AFibDetector, Monitor  # noqa: E402
from src.preprocess import preprocess_window  # noqa: E402
from src.qrs import detect_qrs  # noqa: E402

st.set_page_config(page_title="Monitor de AFIB a bordo", page_icon="🫀", layout="wide")

# tokens (paleta de referência da skill de visualização): superfície clara, tinta, série e status
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES, MARK = "#2a78d6", "#eb6834"
STATUS = {  # cor de status + ícone + rótulo: a cor nunca carrega o sentido sozinha
    "OK": ("#0ca30c", "✓", "Ritmo sinusal, FC dentro do esperado", "nenhuma"),
    "AVISO_FC_BAIXA": ("#fab219", "↓", "Aviso leve: frequência cardíaca baixa", "leve"),
    "AVISO_FC_ALTA": ("#fab219", "↑", "Aviso leve: frequência cardíaca alta", "leve"),
    "INCERTO": ("#ec835a", "?", "Incerto: revisar", "revisar"),
    "ALERTA_AFIB": ("#d03b3b", "⚠", "ALERTA: fibrilação atrial em janelas consecutivas", "alta"),
    "SINAL_RUIM": ("#8a8984", "✕", "Sinal ruim: sem avaliação clínica", "técnica"),
}

st.markdown(f"""
<style>
.block-container {{padding-bottom: 4.5rem;}}
.faixa {{position: fixed; left: 0; right: 0; bottom: 0; z-index: 999999; background: #3b3a37; color: #ffffff;
         padding: .55rem 1rem; font-size: .95rem; font-weight: 600; text-align: center; letter-spacing: .01em;}}
.faixa small {{font-weight: 400; opacity: .85; margin-left: .75rem;}}
.tile {{border: 1px solid {GRID}; border-left: 10px solid var(--c); border-radius: 8px; padding: .8rem 1rem;
        background: {SURF}; color: {INK};}}
.tile .icone {{display: inline-block; width: 2.1rem; height: 2.1rem; line-height: 2.1rem; text-align: center;
               border-radius: 50%; background: var(--c); color: #fff; font-weight: 700; font-size: 1.2rem;
               margin-right: .6rem;}}
.tile .estado {{font-size: 1.35rem; font-weight: 700;}}
.tile .desc {{color: {INK2}; font-size: .92rem; margin-top: .25rem;}}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def _detector() -> AFibDetector:
    return AFibDetector()


@st.cache_resource
def _pack(kind: str) -> dict:
    return get_pack(prefer_replay=(kind == "replay"))


def reset(kind: str, scenario: str):
    s = st.session_state
    s.kind, s.scenario = kind, scenario
    s.stream = Stream(_pack(kind), scenario, seed=int(np.random.default_rng().integers(1e6)))
    s.monitor = Monitor(_detector())
    s.hist, s.events, s.last_window = [], [], None


def step():
    s = st.session_state
    s.stream.set_scenario(s.scenario)
    w, t = s.stream.next_window()
    r = s.monitor.update(w, t=t)
    r["cenario"] = s.scenario
    r["registro"] = s.stream.src_ids[-1]
    s.last_window = w
    prev = s.hist[-1]["estado"] if s.hist else None
    s.hist = (s.hist + [r])[-300:]
    if r["alerta_novo"] or (r["estado"].startswith("AVISO") and r["estado"] != prev):
        s.events = ([{"janela": r["janela"], "tempo simulado": _mmss(t), "evento": r["estado"],
                      "prob. AFIB": r["prob_afib"], "FC (bpm)": r["fc"], "cenário reproduzido": LABELS[s.scenario]}]
                    + s.events)[:50]


def _mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


# ------------------------------------------------------------------ barra lateral
replay_ok = PACK.exists()
with st.sidebar:
    st.markdown("### Fonte do sinal")
    kind = st.radio("fonte", ["replay", "sintético"], index=0 if replay_ok else 1, label_visibility="collapsed",
                    format_func=lambda k: "Replay de dados públicos" if k == "replay" else "ECG sintético",
                    disabled=not replay_ok, horizontal=True)
    kind = "replay" if kind == "replay" else "sintetica"
    if not replay_ok:
        st.caption("Pacote de replay ausente: rode `make demo-data` (exige `make data`). Usando ECG sintético.")
    if "stream" not in st.session_state or st.session_state.kind != kind:
        reset(kind, st.session_state.get("scenario", "sinusal"))
    st.markdown("### Cenário")
    for sc in SCENARIOS:
        if st.button(LABELS[sc], key=f"b_{sc}", width="stretch",
                     type="primary" if st.session_state.scenario == sc else "secondary"):
            st.session_state.scenario = sc
            st.rerun()
    st.markdown("### Reprodução")
    playing = st.toggle("Reproduzir automaticamente", value=True)
    speed = st.select_slider("Janelas por segundo (tempo acelerado)", options=[0.5, 1.0, 2.0, 4.0], value=1.0)
    c1, c2 = st.columns(2)
    if c1.button("Avançar 1 janela", width="stretch"):
        step()
    if c2.button("Reiniciar", width="stretch"):
        reset(kind, st.session_state.scenario)
        st.rerun()
    m = st.session_state.monitor
    st.caption(f"Alerta de AFIB: {m.n} de {m.m} janelas consecutivas. Cada janela = 9,6 s de sinal; "
               "no modo acelerado, várias janelas passam por segundo.")

banner = _pack(kind)["banner"]
st.markdown(f'<div class="faixa">{banner}<small>Protótipo de pesquisa — não é dispositivo médico nem diagnóstico.</small></div>',
            unsafe_allow_html=True)


# ------------------------------------------------------------------ área principal
def ecg_figure(w: np.ndarray, r_idx: np.ndarray):
    t = np.arange(w.size) / 250
    fig, ax = plt.subplots(figsize=(11, 2.6), facecolor=SURF)
    ax.set_facecolor(SURF)
    ax.plot(t, w, color=SERIES, lw=1.1)
    if r_idx.size:
        ax.scatter(t[r_idx], w[r_idx], color=MARK, s=18, zorder=3, label="QRS detectado")
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), fontsize=8, frameon=False, borderaxespad=0.1)
    for s_ in ["top", "right"]:
        ax.spines[s_].set_visible(False)
    for s_ in ["left", "bottom"]:
        ax.spines[s_].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_xlim(0, 9.6)
    ax.set_xlabel("tempo na janela (s)", fontsize=8, color=INK2)
    ax.set_ylabel("A/D 12 bits", fontsize=8, color=INK2)
    fig.tight_layout()
    return fig


def trend_figure(y, ylabel, ref=None, ref_label=None, ylim=None):
    fig, ax = plt.subplots(figsize=(5.4, 2.0), facecolor=SURF)
    ax.set_facecolor(SURF)
    x = np.arange(len(y))
    ax.plot(x, y, color=SERIES, lw=2, marker="o", ms=3)
    for v in (ref or []):
        ax.axhline(v, color=INK2, lw=0.8, ls=":")
    if ref_label:
        ax.text(0.99, 0.95, ref_label, transform=ax.transAxes, ha="right", va="top", fontsize=7, color=INK2)
    for s_ in ["top", "right"]:
        ax.spines[s_].set_visible(False)
    for s_ in ["left", "bottom"]:
        ax.spines[s_].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=7)
    ax.grid(True, color=GRID, lw=0.6)
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_ylabel(ylabel, fontsize=8, color=INK2)
    ax.set_xlabel("janelas recentes", fontsize=7, color=INK2)
    fig.tight_layout()
    return fig


def render():
    s = st.session_state
    if playing:
        step()
    st.markdown("## Monitor de fibrilação atrial a bordo — demonstração")
    if not s.hist:
        st.info("Clique em **Avançar 1 janela** ou ative a reprodução automática.")
        return
    r = s.hist[-1]
    cor, icone, desc, sev = STATUS[r["estado"]]
    detalhe = f" — {r['motivo']}" if r["motivo"] else ""
    a, b, c, d = st.columns([2.2, 1, 1, 1.2])
    a.markdown(f'<div class="tile" style="--c:{cor}"><span class="icone">{icone}</span>'
               f'<span class="estado">{r["estado"]}</span><div class="desc">{desc} (severidade: {sev}){detalhe}</div></div>',
               unsafe_allow_html=True)
    b.metric("Frequência cardíaca", "—" if r["fc"] is None else f"{r['fc']:.0f} bpm")
    c.metric("Probabilidade de AFIB", "—" if r["prob_afib"] is None else f"{100 * r['prob_afib']:.1f}%")
    sq = r["sqi"]
    d.metric("Qualidade do sinal", "aprovada" if sq.get("aprovado") else "reprovada",
             help="Motivos: " + (", ".join(sq.get("motivos", [])) or "nenhum"))
    st.caption(f"Janela {r['janela']} · tempo simulado {_mmss(r['t_s'])} · cenário reproduzido: **{LABELS[r['cenario']]}** "
               f"· registro `{r['registro']}` · limiares de FC em uso: {r['limiares_fc'][0]:.0f}–{r['limiares_fc'][1]:.0f} bpm "
               f"· latência da inferência: {r['latencia_ms']:.1f} ms")
    w = s.last_window
    st.pyplot(ecg_figure(w, detect_qrs(preprocess_window(w))), width="stretch")
    h = s.hist[-60:]
    t1, t2 = st.columns(2)
    fc = [np.nan if x["fc"] is None else x["fc"] for x in h]
    lo, hi = r["limiares_fc"]
    t1.markdown(f"**Frequência cardíaca** · linhas pontilhadas: limiares {lo:.0f} e {hi:.0f} bpm")
    t1.pyplot(trend_figure(fc, "bpm", [lo, hi]), width="stretch")
    pa = [np.nan if x["prob_afib"] is None else x["prob_afib"] for x in h]
    t2.markdown("**Probabilidade de AFIB por janela** · linha pontilhada: a janela vota AFIB a partir de 0,5")
    t2.pyplot(trend_figure(pa, "probabilidade", [0.5], ylim=(-0.03, 1.03)), width="stretch")
    plt.close("all")
    e1, e2 = st.columns([1.1, 1])
    e1.markdown("**Histórico de alertas e avisos**")
    if s.events:
        ev = pd.DataFrame(s.events).astype({"prob. AFIB": object, "FC (bpm)": object}).fillna("—")
        e1.dataframe(ev, hide_index=True, width="stretch", height=260)
    else:
        e1.caption("Nenhum alerta ou aviso até agora.")
    e2.markdown("**Últimas janelas**")
    fmt = lambda v, d: "—" if v is None else f"{v:.{d}f}"  # noqa: E731
    e2.dataframe(pd.DataFrame([{"janela": x["janela"], "estado": f"{STATUS[x['estado']][1]} {x['estado']}",
                                "prob. AFIB": fmt(x["prob_afib"], 3), "FC": fmt(x["fc"], 0), "cenário": LABELS[x["cenario"]]}
                               for x in reversed(s.hist[-12:])]), hide_index=True, width="stretch", height=260,
                 column_config={"estado": st.column_config.TextColumn(width="medium"),
                                "janela": st.column_config.NumberColumn(width="small")})


st.fragment(run_every=(1.0 / speed) if playing else None)(render)()
