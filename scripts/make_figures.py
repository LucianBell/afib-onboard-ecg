"""Figuras do README geradas a partir de results/ (make report). Paleta de referência da skill dataviz.

    python scripts/make_figures.py
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT  # noqa: E402

RES, FIG = ROOT / "results", ROOT / "results" / "figures"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def style(ax, title=None, xlabel=None, ylabel=None):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=10, color=INK, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8, color=INK2)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8, color=INK2)


def ci(v):
    return ast.literal_eval(v) if isinstance(v, str) else v


def fig_internal_external():
    t = pd.read_csv(RES / "expB" / "all_models.csv")
    t = t[t["modelo"].isin(["logreg", "baseline_rr"])]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    names = {"logreg": "regressão logística (escolhida)", "baseline_rr": "baseline RR (nRMSSD)"}
    scen = ["Shaoxing teste", "PTB-XL todo"]
    xt = ["A: interno\n(Shaoxing, teste)", "B: externo\n(PTB-XL inteiro)"]
    for ax, (met, lab) in zip(axes, [("auroc", "AUROC"), ("sensibilidade", "sensibilidade"), ("especificidade", "especificidade")]):
        for k, (mod, col) in enumerate([("logreg", C1), ("baseline_rr", C2)]):
            r = t[t["modelo"] == mod].set_index("cenario").loc[scen]
            x = np.arange(2) + (k - 0.5) * 0.18
            lo = [ci(v)[0] for v in r[f"{met}_ic95"]]
            hi = [ci(v)[1] for v in r[f"{met}_ic95"]]
            ax.errorbar(x, r[met], yerr=[r[met] - lo, np.array(hi) - r[met]], fmt="o", color=col, ms=6, lw=1.5,
                        capsize=3, label=names[mod])
        ax.set_xticks(range(2), xt)
        ax.set_xlim(-0.5, 1.5)
        style(ax, title=lab)
    axes[0].legend(fontsize=7, frameon=False, loc="lower left")
    fig.suptitle("Desempenho por janela, interno vs. externo (IC 95% por bootstrap); limiares escolhidos na validação de Shaoxing",
                 fontsize=9.5, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "fig_internal_vs_external.png", dpi=140)
    plt.close(fig)


def fig_source():
    t = pd.read_csv(RES / "expC" / "source_classifier.csv")
    t["rot"] = t["par"] + " — " + t["atributos"].str.replace(" — 1 variável, sem modelo", " (1 variável)", regex=False)
    t = t.iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 3.4))
    y = np.arange(len(t))
    ax.hlines(y, 0.5, t["auroc_cv5"], color=GRID, lw=2)
    ax.scatter(t["auroc_cv5"], y, color=C1, s=40, zorder=3)
    for yi, v in zip(y, t["auroc_cv5"]):
        ax.text(v + 0.008, yi, f"{v:.2f}", va="center", fontsize=8, color=INK)
    ax.axvline(0.5, color=INK2, lw=0.8, ls=":")
    ax.set_yticks(y, t["rot"], fontsize=8)
    ax.set_xlim(0.45, 1.06)
    style(ax, xlabel="AUROC (validação cruzada de 5 dobras; linha pontilhada = acaso)")
    fig.suptitle("Experimento C — quão bem as bases se separam usando só ECG sinusal normal (AUROC; 0,5 = indistinguíveis)",
                 fontsize=9.5, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "fig_source_confusion.png", dpi=140)
    plt.close(fig)


def fig_out_of_training():
    t = pd.read_csv(RES / "expG" / "out_of_training.csv")
    t = t[(t["n_sqi_ok"] >= 30) & ~t["categoria"].str.contains("rótulo", regex=False)]
    nomes = {"AF": "flutter atrial", "AFLT": "flutter atrial", "AT": "taquicardia atrial", "SVT": "taquicardia supraventricular",
             "ECTOPIA": "ectopia (extrassístoles)", "BAV": "bloqueio AV", "PACE": "marcapasso",
             "SVARR": "arritmia supraventricular", "PRE_EXCITACAO": "pré-excitação",
             "SEM_RITMO_BASE+ECTOPIA": "ectopia, ritmo de base não informado",
             "SEM_RITMO_BASE+BAV": "bloqueio AV, ritmo de base não informado"}
    t = t.assign(rot=t["base"] + " · " + t["categoria"].map(lambda c: nomes.get(c, c))).sort_values("pct_AFIB")
    fig, ax = plt.subplots(figsize=(10, 0.32 * len(t) + 1.4))
    y = np.arange(len(t))
    left = np.zeros(len(t))
    for col_name, col, lab in [("pct_AFIB", "#d03b3b", "classificado AFIB"), ("pct_INCERTO", "#ec835a", "INCERTO"),
                               ("pct_NAO_AFIB", "#8a8984", "não AFIB")]:
        ax.barh(y, t[col_name], left=left, color=col, edgecolor=SURF, linewidth=2, height=0.72, label=lab)
        left += t[col_name].to_numpy()
    for yi, v in zip(y, t["pct_AFIB"]):
        ax.text(1.01, yi, f"{100 * v:.0f}% AFIB", va="center", fontsize=7.5, color=INK)
    ax.set_yticks(y, t["rot"], fontsize=8)
    ax.set_xlim(0, 1.13)
    style(ax, xlabel="fração das janelas")
    ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.45, -0.07))
    fig.suptitle("Experimento G — como o detector classifica ritmos que não estavam no treino (janelas aprovadas pelo SQI)",
                 fontsize=9.5, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "fig_out_of_training.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    fig_internal_external()
    fig_source()
    fig_out_of_training()
    print("figuras:", ", ".join(sorted(p.name for p in FIG.glob("*.png"))))
