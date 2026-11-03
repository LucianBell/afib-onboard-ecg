"""Experimentos B a I (etapa 6). Regras fixadas em configs/default.yaml antes da execução.

    python scripts/experiments.py b c d e f g h i      (ou: all)

Saídas em results/exp{B..I}/ e results/figures/. O modelo é o escolhido no experimento A
(regressão logística), com calibração, limiar e detector de "fora do padrão" ajustados só no
treino/validação de Shaoxing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from joblib import Parallel, delayed  # noqa: E402
from scipy.signal import resample_poly, welch  # noqa: E402
from scipy.stats import norm  # noqa: E402
from sklearn.model_selection import GridSearchCV, PredefinedSplit, StratifiedGroupKFold  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import evaluate as ev  # noqa: E402
from src import features as F  # noqa: E402
from src import sqi as SQ  # noqa: E402
from src.baseline import hr_state, rr_irregularity_score  # noqa: E402
from src.config import load_config  # noqa: E402
from src.decision import (OODDetector, alert_condition, count_alerts, episode_detection,  # noqa: E402
                          false_alerts_per_day, window_states)
from src.models import GRIDS, PlattCalibrator, make_feature_model, predict_cnn  # noqa: E402
from src.preprocess import crop, filter_window, preprocess_window, resample_to_target, simulate_device  # noqa: E402
from src.qrs import detect_qrs  # noqa: E402
from src.splits import dedupe  # noqa: E402

CFG = load_config()
SEED = CFG["seed"]
RES = CFG["paths"]["results"]
PROC = CFG["paths"]["processed"]
FIG = RES / "figures"
MOD = PROC / "expA_models"
NEG = CFG["experiment_a"]["negative"]
POS = CFG["experiment_a"]["positive"]
FN = F.FEATURE_NAMES
# paleta categórica de referência (skill dataviz), slots 1-3
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def log(*a):
    print(*a, flush=True)


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def wilson(k, n, z=1.96):
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [float(c - h), float(c + h)]


def style(ax, title=None, xlabel=None, ylabel=None):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=10, color=INK, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8, color=MUTED)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8, color=MUTED)


# ------------------------------------------------------------------ contexto compartilhado
class Ctx:
    def __init__(self):
        ch = pd.read_parquet(PROC / "chapman_features.parquet")
        self.ch, _ = dedupe(ch)  # remove cópias de Ningbo de sinais de Shaoxing (D16)
        self.ch = self.ch.reset_index(drop=True)
        self.pt = pd.read_parquet(PROC / "ptbxl_features.parquet")
        sp = pd.read_csv(RES / "expA" / "split.csv")[["record_id", "split"]]
        self.ch = self.ch.merge(sp, on="record_id", how="left")
        self.art = joblib.load(MOD / "logreg.joblib")
        self.thr = self.art["threshold"]
        self.thr_bl = joblib.load(MOD / "baseline_rr.joblib")["threshold"]
        sh = self.ch[self.ch["split"].notna() & self.ch["sqi_ok"]]
        self.ood = OODDetector(self.art["model"]).fit(sh[sh["split"] == "train"][FN], sh[sh["split"] == "val"][FN])
        for d in (self.ch, self.pt):
            self.score(d)

    def score(self, d: pd.DataFrame):
        d["p"] = self.art["calibrator"].transform(self.art["model"].predict_proba(d[FN])[:, 1])
        d["s_bl"] = rr_irregularity_score(d)
        d["ood"] = self.ood.is_ood(d[FN])
        d["state"] = window_states(d["sqi_ok"], d["p"], self.thr, d["ood"])
        d["y"] = d["group"].isin(POS).astype(int)
        return d

    def shaoxing(self, split=None, sqi=True):
        d = self.ch[self.ch["split"].notna()]
        if split:
            d = d[d["split"] == split]
        return d[d["sqi_ok"]] if sqi else d

    def ptb_binary(self, sqi=True):
        b = CFG["experiment_b"]
        d = self.pt[self.pt["group"].isin(b["ptbxl_groups_positive"] + b["ptbxl_groups_negative"])]
        return d[d["sqi_ok"]] if sqi else d


def metrics_row(name, d, p, thr, n_boot=1000):
    m = ev.full_report(d["y"].to_numpy(), np.asarray(p), thr, n_boot, SEED, calib=False)
    return {"cenario": name, "n_pos": m["n_pos"], "n_neg": m["n_neg"], "prevalencia": m["n_pos"] / (m["n_pos"] + m["n_neg"]),
            **{k: m[k] for k in ["auprc", "auroc", "sensibilidade", "especificidade", "ppv", "npv", "f1"]},
            **{f"{k}_ic95": m["ic95"][k] for k in ["auprc", "auroc", "sensibilidade", "especificidade"]},
            "fp": m["fp"], "fn": m["fn"], "ppv_prev_1pct": m["ppv_prevalencia"]["0.01"]}


# ------------------------------------------------------------------ B: validação externa
def exp_b(c: Ctx):
    out = RES / "expB"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    a_te, ptb = c.shaoxing("test"), c.ptb_binary()
    rows.append(metrics_row("A: Shaoxing→Shaoxing (teste A)", a_te, a_te["p"], c.thr))
    rows.append(metrics_row("B: Shaoxing→PTB-XL (todo)", ptb, ptb["p"], c.thr))
    rows.append(metrics_row("B: Shaoxing→PTB-XL (fold 10)", ptb[ptb["strat_fold"] == 10], ptb.loc[ptb["strat_fold"] == 10, "p"], c.thr))
    # todos os candidatos e o baseline, com limiares de Shaoxing
    allm = []
    for name in ["baseline_rr", "logreg", "random_forest", "lightgbm", "cnn"]:
        for scen, d in [("Shaoxing teste", a_te), ("PTB-XL todo", ptb)]:
            if name == "baseline_rr":
                p, thr = d["s_bl"], c.thr_bl
            elif name == "cnn":
                import torch

                from src.models import build_cnn
                meta = joblib.load(MOD / "cnn_meta.joblib")
                net = build_cnn()
                net.load_state_dict(torch.load(MOD / "cnn_state.pt"))
                W = np.load(PROC / ("chapman_windows.npy" if scen.startswith("Shaoxing") else "ptbxl_windows.npy"), mmap_mode="r")
                p = meta["calibrator"].transform(predict_cnn(net, np.asarray(W[d["win"].to_numpy()])))
                thr = meta["threshold"]
            else:
                art = joblib.load(MOD / f"{name}.joblib")
                p, thr = art["calibrator"].transform(art["model"].predict_proba(d[FN])[:, 1]), art["threshold"]
            r = metrics_row(scen, d, p, thr, n_boot=500)
            allm.append({"modelo": name, **r})
    pd.DataFrame(allm).to_csv(out / "all_models.csv", index=False)

    # sentido inverso: treino PTB-XL folds 1-8 (CV por fold = por paciente), limiar/calibração no fold 9
    b = CFG["experiment_b"]
    tr = ptb[ptb["strat_fold"].isin(b["inverse_train_folds"])]
    va = ptb[ptb["strat_fold"] == b["inverse_val_fold"]]
    te = ptb[ptb["strat_fold"] == b["inverse_test_fold"]]
    gs = GridSearchCV(make_feature_model("logreg", SEED), GRIDS["logreg"], scoring="average_precision",
                      cv=PredefinedSplit(tr["strat_fold"].to_numpy() - 1), n_jobs=2).fit(tr[FN], tr["y"])
    cal = PlattCalibrator().fit(gs.predict_proba(va[FN])[:, 1], va["y"])
    pinv = lambda d: cal.transform(gs.predict_proba(d[FN])[:, 1])  # noqa: E731
    thr_inv = ev.threshold_for_specificity(va["y"].to_numpy(), pinv(va), CFG["experiment_a"]["threshold_rule"]["min_specificity"])
    sh_all = c.shaoxing()
    rows.append(metrics_row("Inverso: PTB-XL→PTB-XL (fold 10)", te, pinv(te), thr_inv))
    rows.append(metrics_row("Inverso: PTB-XL→Shaoxing (teste A)", a_te, pinv(a_te), thr_inv))
    rows.append(metrics_row("Inverso: PTB-XL→Shaoxing (todo)", sh_all, pinv(sh_all), thr_inv))
    # análise de sensibilidade: só laudos validados por humano no PTB-XL
    idx = pd.read_parquet(CFG["paths"]["interim"] / "ptbxl_index.parquet", columns=["record_id", "validated_by_human"])
    pv = ptb.merge(idx, on="record_id")
    pv = pv[pv["validated_by_human"]]
    rows.append(metrics_row("B: Shaoxing→PTB-XL (só validated_by_human)", pv, pv["p"], c.thr))
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "external_validation.csv", index=False)
    a, bb = rows[0], rows[1]
    dump(out / "summary.json", {
        "queda_A_para_B": {k: bb[k] - a[k] for k in ["auroc", "auprc", "sensibilidade", "especificidade", "ppv"]},
        "inverso_melhores_params": gs.best_params_, "inverso_limiar": thr_inv,
        "nota": "AUPRC e PPV dependem da prevalência (Shaoxing ~21%, PTB-XL ~8%); AUROC, sensibilidade e especificidade não.",
        "linhas": rows})
    log(tab[["cenario", "n_pos", "n_neg", "auroc", "auprc", "sensibilidade", "especificidade", "ppv"]].round(4).to_string())


# ------------------------------------------------------------------ C: confusão de fonte
def descriptors(d: pd.DataFrame, base: str) -> pd.DataFrame:
    """Descritores genéricos do sinal (sensíveis a equipamento/base): PSD em 1-40 Hz e amplitude em mV."""
    W = np.load(PROC / f"{base}_windows.npy", mmap_mode="r")
    X = np.asarray(W[d["win"].to_numpy()])
    f, pw = welch(X, fs=250, nperseg=256, axis=1)
    keep = (f >= 1) & (f <= 40)
    psd = np.log10(pw[:, keep] + 1e-12)
    idx = pd.read_parquet(CFG["paths"]["interim"] / f"{base}_index.parquet",
                          columns=["record_id", "qrs_p2p_leadI_mv", "leadI_std_mv"])
    amp = d[["record_id"]].merge(idx, on="record_id", how="left")
    out = pd.DataFrame(psd, columns=[f"psd_{x:.1f}" for x in f[keep]], index=d.index)
    out["amp_qrs_mv"] = amp["qrs_p2p_leadI_mv"].to_numpy()
    out["amp_std_mv"] = amp["leadI_std_mv"].to_numpy()
    return out


def _cv_auroc(X, y, groups, model):
    from sklearn.metrics import roc_auc_score
    cv = StratifiedGroupKFold(5, shuffle=True, random_state=SEED)
    pr = np.zeros(len(y))
    for tr, te in cv.split(X, y, groups):
        pr[te] = model.fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    return float(roc_auc_score(y, pr))


def exp_c(c: Ctx):
    from sklearn.metrics import roc_auc_score
    out = RES / "expC"
    out.mkdir(parents=True, exist_ok=True)
    sh_n = c.ch[(c.ch["source"] == "shaoxing") & (c.ch["group"] == "SINUS_NORMAL") & c.ch["sqi_ok"]]
    nb_n = c.ch[(c.ch["source"] == "ningbo") & (c.ch["group"] == "SINUS_NORMAL") & c.ch["sqi_ok"]]
    pt_n = c.pt[(c.pt["group"] == "SINUS_NORMAL") & c.pt["sqi_ok"]]
    res = {"C1_separar_normais_por_base": []}
    # escala descrita no TCC: Chapman dividida por 10^3 e PTB-XL por 10 -> razão de 100x entre bases.
    # AUROC univariado da amplitude do QRS (sem modelo), com unidades corretas e com a escala do TCC.
    idx = {b: pd.read_parquet(CFG["paths"]["interim"] / f"{b}_index.parquet", columns=["record_id", "qrs_p2p_leadI_mv"])
           for b in ["chapman", "ptbxl"]}
    a_sh = sh_n[["record_id"]].merge(idx["chapman"], on="record_id")["qrs_p2p_leadI_mv"].to_numpy()
    a_pt = pt_n[["record_id"]].merge(idx["ptbxl"], on="record_id")["qrs_p2p_leadI_mv"].to_numpy()
    yy = np.r_[np.zeros(a_sh.size), np.ones(a_pt.size)]
    for lab, k in [("amplitude do QRS em mV (unidades corretas)", 1.0), ("amplitude com a escala do TCC (÷10³ vs ÷10)", 100.0)]:
        auc = float(roc_auc_score(yy, np.r_[a_sh, k * a_pt]))
        res["C1_separar_normais_por_base"].append({"par": "Shaoxing vs PTB-XL", "atributos": lab + " — 1 variável, sem modelo",
                                                   "n": [int(a_sh.size), int(a_pt.size)], "auroc_cv5": auc})
        log(f"C1 Shaoxing vs PTB-XL | {lab}: AUROC {auc:.4f}")
    for name, A, ba, B, bb in [("Shaoxing vs PTB-XL", sh_n, "chapman", pt_n, "ptbxl"),
                                ("Shaoxing vs Ningbo", sh_n, "chapman", nb_n, "chapman")]:
        y = np.r_[np.zeros(len(A)), np.ones(len(B))].astype(int)
        groups = np.r_[A["record_id"].to_numpy(), np.where(B["source"] == "ptbxl", B.get("patient_id", B["record_id"]).astype(str), B["record_id"]).astype(str)]
        for fs_name, XA, XB in [("atributos de ritmo (30, os do modelo)", A[FN], B[FN]),
                                ("descritores do sinal (PSD 1–40 Hz + amplitude em mV)", descriptors(A, ba), descriptors(B, bb))]:
            X = pd.concat([XA, XB], ignore_index=True)
            auc = _cv_auroc(X, y, groups, make_feature_model("lightgbm", SEED).set_params(clf__n_estimators=300, clf__num_leaves=15))
            res["C1_separar_normais_por_base"].append({"par": name, "atributos": fs_name, "n": [len(A), len(B)], "auroc_cv5": auc})
            log(f"C1 {name} | {fs_name}: AUROC {auc:.4f}")

    # C2: desenho do TCC — AFIB de Shaoxing vs normais do PTB-XL
    sh = c.shaoxing()
    afib_tr = sh[(sh["group"] == "AFIB") & sh["split"].isin(["train", "val"])]
    afib_te = sh[(sh["group"] == "AFIB") & (sh["split"] == "test")]
    pn_tr, pn_te = pt_n[pt_n["strat_fold"] <= 8], pt_n[pt_n["strat_fold"] >= 9]
    cat = lambda *ds: pd.concat(ds, ignore_index=True)  # noqa: E731  (índices de bases diferentes colidem)
    tr = cat(afib_tr, pn_tr)
    tests = {
        "misto (desenho do TCC): AFIB Shaoxing × normal PTB-XL": cat(afib_te, pn_te),
        "mesma fonte Shaoxing: AFIB × normal Shaoxing": cat(afib_te, sh[(sh["group"] == "SINUS_NORMAL") & (sh["split"] == "test")]),
        "mesma fonte PTB-XL: AFIB × normal PTB-XL (folds 9-10)": cat(c.pt[(c.pt["group"] == "AFIB") & c.pt["sqi_ok"] & (c.pt["strat_fold"] >= 9)], pn_te),
    }
    res["C2_desenho_TCC"] = []
    for mname, feat in [("logreg + atributos de ritmo", "rhythm"), ("LightGBM + descritores do sinal", "desc")]:
        def X(d):
            if feat == "rhythm":
                return d[FN]
            m = (d["source"] == "ptbxl").to_numpy()
            parts = [descriptors(d[mask], b) for mask, b in [(~m, "chapman"), (m, "ptbxl")] if mask.any()]
            return pd.concat(parts).sort_index()
        model = make_feature_model("logreg" if feat == "rhythm" else "lightgbm", SEED)
        model.fit(X(tr), tr["y"])
        for tname, d in tests.items():
            p = model.predict_proba(X(d))[:, 1]
            m = ev.point_metrics(d["y"], p, 0.5)
            res["C2_desenho_TCC"].append({"modelo": mname, "teste": tname, "n_pos": int(d["y"].sum()), "n_neg": int((1 - d["y"]).sum()),
                                          "auroc": m["auroc"], "sensibilidade@0.5": m["sensibilidade"], "especificidade@0.5": m["especificidade"],
                                          "acuracia@0.5": (m["tp"] + m["tn"]) / len(d)})
            log(f"C2 {mname} | {tname}: AUROC {m['auroc']:.4f} sens {m['sensibilidade']:.3f} esp {m['especificidade']:.3f}")
    dump(out / "summary.json", res)
    pd.DataFrame(res["C2_desenho_TCC"]).to_csv(out / "tcc_design.csv", index=False)
    pd.DataFrame(res["C1_separar_normais_por_base"]).to_csv(out / "source_classifier.csv", index=False)


# ------------------------------------------------------------------ D: ML vs baseline
def paired_bootstrap(d, p_a, thr_a, p_b, thr_b, n=2000):
    from sklearn.metrics import average_precision_score, roc_auc_score
    rng = np.random.default_rng(SEED)
    y = d["y"].to_numpy().astype(bool)
    pa, pb = np.asarray(p_a), np.asarray(p_b)
    pos, neg = np.flatnonzero(y), np.flatnonzero(~y)
    acc = {k: [] for k in ["auroc", "auprc", "sensibilidade", "especificidade"]}
    for _ in range(n):
        i = np.concatenate([rng.choice(pos, pos.size), rng.choice(neg, neg.size)])
        yy = y[i]
        acc["auroc"].append(roc_auc_score(yy, pa[i]) - roc_auc_score(yy, pb[i]))
        acc["auprc"].append(average_precision_score(yy, pa[i]) - average_precision_score(yy, pb[i]))
        acc["sensibilidade"].append((pa[i][yy] >= thr_a).mean() - (pb[i][yy] >= thr_b).mean())
        acc["especificidade"].append((pa[i][~yy] < thr_a).mean() - (pb[i][~yy] < thr_b).mean())
    out = {}
    for k, v in acc.items():
        v = np.asarray(v)
        out[k] = {"diferenca_media": float(v.mean()), "ic95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))],
                  "p_bilateral": float(min(1.0, 2 * min((v <= 0).mean(), (v >= 0).mean())))}
    return out


def exp_d(c: Ctx):
    out = RES / "expD"
    res = {}
    for name, d in [("A: teste Shaoxing", c.shaoxing("test")), ("B: PTB-XL todo", c.ptb_binary())]:
        y = d["y"].to_numpy().astype(bool)
        corr_ml, corr_bl = (d["p"] >= c.thr).to_numpy() == y, (d["s_bl"] >= c.thr_bl).to_numpy() == y
        res[name] = {"mcnemar": ev.mcnemar(corr_ml, corr_bl),
                     "bootstrap_pareado_logreg_menos_baseline": paired_bootstrap(d, d["p"], c.thr, d["s_bl"], c.thr_bl),
                     "erros": {"logreg": int((~corr_ml).sum()), "baseline_rr": int((~corr_bl).sum()), "n": int(len(d))}}
        log(name, json.dumps(res[name], ensure_ascii=False)[:600])
    dump(out / "summary.json", res)


# ------------------------------------------------------------------ E: frequência alterada
def exp_e(c: Ctx):
    out = RES / "expE"
    out.mkdir(parents=True, exist_ok=True)
    rows, hr_rows = [], []
    sets = {"Shaoxing (teste A)": c.shaoxing("test"), "PTB-XL (todo)": c.pt[c.pt["sqi_ok"]],
            "Ningbo (todo, só negativos; fonte nunca vista)": c.ch[(c.ch["source"] == "ningbo") & c.ch["sqi_ok"]]}
    for sname, d in sets.items():
        for g in ["SINUS_NORMAL", "SINUS_OUTRO", "SINUS_BRADY", "SINUS_TACHY"]:
            x = d[d["group"] == g]
            if len(x) == 0:
                continue
            k_thr, k_state, k_bl = int((x["p"] >= c.thr).sum()), int((x["state"] == "AFIB").sum()), int((x["s_bl"] >= c.thr_bl).sum())
            rows.append({"conjunto": sname, "grupo": g, "n": len(x),
                         "falso_afib_logreg_limiar": k_thr / len(x), "ic95": wilson(k_thr, len(x)),
                         "falso_afib_estado_AFIB": k_state / len(x), "ic95_estado": wilson(k_state, len(x)),
                         "falso_afib_baseline": k_bl / len(x), "ic95_baseline": wilson(k_bl, len(x))})
        # regra de FC contra os rótulos
        x = d[d["group"].isin(["SINUS_NORMAL", "SINUS_BRADY", "SINUS_TACHY"])]
        pred = x["hr_median"].map(hr_state)
        ct = pd.crosstab(x["group"], pred)
        for g, r in ct.iterrows():
            hr_rows.append({"conjunto": sname, "rotulo": g, "n": int(r.sum()), **{k: int(v) for k, v in r.items()}})
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "false_afib_by_rate.csv", index=False)
    hr = pd.DataFrame(hr_rows).fillna(0)
    hr.to_csv(out / "hr_rule_vs_labels.csv", index=False)
    dump(out / "summary.json", {"falso_afib": rows, "regra_fc": hr_rows,
                                "limiares_fc": CFG["hr_rule"]})
    log(tab[["conjunto", "grupo", "n", "falso_afib_logreg_limiar", "falso_afib_estado_AFIB", "falso_afib_baseline"]].round(4).to_string())
    log(hr.to_string())


# ------------------------------------------------------------------ F: robustez a ruído
def _load_noise():
    import wfdb
    nz = {}
    for r in CFG["noise"]["records"]:
        rec = wfdb.rdrecord(str(CFG["paths"]["raw"] / "nstdb" / r))
        nz[r] = resample_poly(rec.p_signal[:, 0], 25, 36)  # 360 -> 250 Hz
    return nz


def _noisy_eval(raw, nseg, snr):
    if nseg is not None:
        ps = np.var(filter_window(raw))
        pn = np.var(filter_window(nseg))
        raw = raw + nseg * np.sqrt(ps / (pn * 10 ** (snr / 10)))
    w = preprocess_window(raw)
    r = detect_qrs(w)
    f = F.extract(w, r=r)
    q = SQ.compute(raw, w, r=r)
    return f, SQ.passes(q)[0], q


def _eval_block(c, d, raws, noise, snr, tag):
    rng = np.random.default_rng(SEED)
    segs = [None] * len(raws)
    if noise is not None:  # trecho aleatório do registro de ruído para cada janela (semente fixa)
        st = rng.integers(0, noise.size - raws[0].size, len(raws))
        segs = [noise[a : a + raws[0].size].copy() for a in st]
    res = Parallel(n_jobs=6, batch_size=64)(delayed(_noisy_eval)(raws[i], segs[i], snr) for i in range(len(raws)))
    fx = pd.DataFrame([r[0] for r in res])[FN]
    ok = np.array([r[1] for r in res])
    p = c.art["calibrator"].transform(c.art["model"].predict_proba(fx)[:, 1])
    s_bl = rr_irregularity_score(fx)
    y = d["y"].to_numpy().astype(bool)
    row = {"ruido": tag, "snr_db": snr}
    for lab, mask in [("sem_sqi", np.ones_like(ok)), ("com_sqi", ok)]:
        yy, pp, bb = y[mask], p[mask], s_bl[mask]
        row[f"sens_{lab}"] = float((pp[yy] >= c.thr).mean()) if yy.any() else np.nan
        row[f"esp_{lab}"] = float((pp[~yy] < c.thr).mean()) if (~yy).any() else np.nan
        row[f"sens_baseline_{lab}"] = float((bb[yy] >= c.thr_bl).mean()) if yy.any() else np.nan
        row[f"esp_baseline_{lab}"] = float((bb[~yy] < c.thr_bl).mean()) if (~yy).any() else np.nan
    row["sqi_rejeita_afib"] = float((~ok[y]).mean())
    row["sqi_rejeita_sinusal"] = float((~ok[~y]).mean())
    return row


def exp_f(c: Ctx):
    out = RES / "expF"
    out.mkdir(parents=True, exist_ok=True)
    d = c.shaoxing("test")  # janelas limpas (aprovadas pelo SQI sem ruído) do teste A
    X = np.load(CFG["paths"]["interim"] / "chapman_leadI_500hz.npy", mmap_mode="r")
    raw500 = [np.asarray(X[r], float) for r in d["row"]]
    raws = [crop(resample_to_target(x, 500)) for x in raw500]
    rows = [_eval_block(c, d, raws, None, np.inf, "limpo")]
    dev = [crop(simulate_device(x).astype(float)) for x in raw500]
    rows.append(_eval_block(c, d, dev, None, np.inf, "conversão A/D 12 bits"))
    nz = _load_noise()
    for k, desc in CFG["noise"]["records"].items():
        for snr in CFG["noise"]["snr_db"]:
            t = time.time()
            rows.append(_eval_block(c, d, raws, nz[k], snr, desc))
            log(f"F {desc} {snr} dB: {({kk: round(v, 3) for kk, v in rows[-1].items() if isinstance(v, float)})} ({time.time() - t:.0f}s)")
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "robustness.csv", index=False)
    log(tab.round(3).to_string())
    # figura: 3 painéis (tipo de ruído) × 2 linhas (sensibilidade, especificidade); séries: sem SQI, com SQI
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.6), sharex=True, sharey="row")
    for j, (k, desc) in enumerate(CFG["noise"]["records"].items()):
        t = tab[tab["ruido"] == desc].sort_values("snr_db")
        for i, met in enumerate(["sens", "esp"]):
            ax = axes[i, j]
            ax.plot(t["snr_db"], t[f"{met}_sem_sqi"], color=C1, lw=2, marker="o", ms=4, label="sem SQI")
            ax.plot(t["snr_db"], t[f"{met}_com_sqi"], color=C2, lw=2, marker="o", ms=4, label="com SQI (janelas aprovadas)")
            ax.plot(t["snr_db"], t[f"{met}_baseline_sem_sqi"], color=C3, lw=2, marker="o", ms=4, ls="--", label="baseline RR, sem SQI")
            style(ax, title=desc if i == 0 else None, xlabel="SNR (dB)" if i == 1 else None,
                  ylabel=("sensibilidade" if met == "sens" else "especificidade") if j == 0 else None)
    axes[0, 0].invert_xaxis()  # eixo x compartilhado: inverter uma vez
    axes[0, 0].set_ylim(0.0, 1.02)
    axes[0, 0].legend(fontsize=7, frameon=False, loc="lower left")
    fig.suptitle("Experimento F — robustez a ruído real (MIT-BIH NSTDB) no teste A; ruído aumenta para a direita",
                 fontsize=10, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "expF_robustness.png", dpi=140)
    plt.close(fig)


# ------------------------------------------------------------------ F, fase 2: calibração do SQI na validação
def _conditions(c, d, X, conds, nz):
    """{(ruído, snr): (atributos, valores SQI)} para as janelas de `d`."""
    raw500 = [np.asarray(X[r], float) for r in d["row"]]
    raws = [crop(resample_to_target(x, 500)) for x in raw500]
    out = {}
    for tag, snr in conds:
        rng = np.random.default_rng(SEED)
        segs = [None] * len(raws)
        if tag != "limpo":
            st = rng.integers(0, nz[tag].size - raws[0].size, len(raws))
            segs = [nz[tag][a : a + raws[0].size].copy() for a in st]
        res = Parallel(n_jobs=6, batch_size=64)(delayed(_noisy_eval)(raws[i], segs[i], snr) for i in range(len(raws)))
        out[(tag, snr)] = (pd.DataFrame([r[0] for r in res])[FN], pd.DataFrame([r[2] for r in res]))
    return out


def _sqi_ok(qdf, S):
    return np.array([SQ.passes(q, S)[0] for q in qdf.to_dict(orient="records")])


def exp_f2(c: Ctx):
    out = RES / "expF"
    K = CFG["sqi_calibration"]
    X = np.load(CFG["paths"]["interim"] / "chapman_leadI_500hz.npy", mmap_mode="r")
    nz = _load_noise()
    conds = [("limpo", np.inf)] + [(k, snr) for k in CFG["noise"]["records"] for snr in K["snr_db"]]
    va = c.shaoxing("val")
    vc = _conditions(c, va, X, conds, nz)
    y = va["y"].to_numpy().astype(bool)
    grid = []
    for kmin in K["grid"]["min_kurtosis"]:
        for amin in K["grid"]["min_qrs_agreement"]:
            S = {**SQ.S, "min_kurtosis": kmin, "min_qrs_agreement": amin}
            row = {"min_kurtosis": kmin, "min_qrs_agreement": amin}
            fx, q = vc[("limpo", np.inf)]
            ok = _sqi_ok(q, S)
            row["rejeicao_limpo_afib"], row["rejeicao_limpo_sinusal"] = float((~ok[y]).mean()), float((~ok[~y]).mean())
            specs = []
            for cond in conds[1:]:
                fx, q = vc[cond]
                ok = _sqi_ok(q, S)
                p = c.art["calibrator"].transform(c.art["model"].predict_proba(fx)[:, 1])
                m = ok & ~y
                specs.append(float((p[m] < c.thr).mean()) if m.any() else np.nan)
            row["especificidade_media_ruido"] = float(np.nanmean(specs))
            grid.append(row)
    grid = pd.DataFrame(grid)
    grid.to_csv(out / "sqi_calibration_grid.csv", index=False)
    elig = grid[(grid["rejeicao_limpo_afib"] <= K["max_clean_rejection"]) & (grid["rejeicao_limpo_sinusal"] <= K["max_clean_rejection"])]
    best = elig.sort_values(["especificidade_media_ruido", "min_kurtosis"], ascending=[False, True]).iloc[0]
    S_cal = {**SQ.S, "min_kurtosis": float(best["min_kurtosis"]), "min_qrs_agreement": float(best["min_qrs_agreement"])}
    log(f"F2: SQI calibrado na validação: curtose >= {S_cal['min_kurtosis']}, concordância >= {S_cal['min_qrs_agreement']}")
    # teste: todas as condições do experimento F, SQI inicial vs. calibrado
    te = c.shaoxing("test")
    conds_te = [("limpo", np.inf)] + [(k, snr) for k in CFG["noise"]["records"] for snr in CFG["noise"]["snr_db"]]
    tc = _conditions(c, te, X, conds_te, nz)
    yt = te["y"].to_numpy().astype(bool)
    rows = []
    for (tag, snr), (fx, q) in tc.items():
        p = c.art["calibrator"].transform(c.art["model"].predict_proba(fx)[:, 1])
        row = {"ruido": CFG["noise"]["records"].get(tag, tag), "snr_db": snr,
               "sens_sem_sqi": float((p[yt] >= c.thr).mean()), "esp_sem_sqi": float((p[~yt] < c.thr).mean())}
        for lab, S in [("inicial", SQ.S), ("calibrado", S_cal)]:
            ok = _sqi_ok(q, S)
            row[f"sens_sqi_{lab}"] = float((p[yt & ok] >= c.thr).mean()) if (yt & ok).any() else np.nan
            row[f"esp_sqi_{lab}"] = float((p[~yt & ok] < c.thr).mean()) if (~yt & ok).any() else np.nan
            row[f"rejeita_afib_{lab}"], row[f"rejeita_sinusal_{lab}"] = float((~ok[yt]).mean()), float((~ok[~yt]).mean())
        rows.append(row)
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "robustness_sqi_calibrated.csv", index=False)
    log(tab.round(3).to_string())
    # custo do SQI calibrado em dados limpos completos (todas as janelas, todos os grupos usados)
    cost = []
    for name, d in [("Shaoxing (A, todos os splits)", c.ch[c.ch["split"].notna()]), ("PTB-XL", c.ptb_binary(sqi=False)),
                    ("Ningbo (negativos)", c.ch[(c.ch["source"] == "ningbo") & c.ch["group"].isin(NEG)])]:
        q = d[SQ.SQI_FEATURES]
        for lab, S in [("inicial", SQ.S), ("calibrado", S_cal)]:
            ok = _sqi_ok(q, S)
            for g, x in pd.Series(ok, index=d.index).groupby(d["group"]):
                cost.append({"conjunto": name, "sqi": lab, "grupo": g, "n": int(len(x)), "rejeicao": float((~x).mean())})
    cost = pd.DataFrame(cost)
    cost.to_csv(out / "sqi_clean_rejection.csv", index=False)
    log(cost.pivot_table(index=["conjunto", "grupo"], columns="sqi", values="rejeicao").round(3).to_string())
    dump(out / "sqi_calibrated.json", {"limiares": {k: S_cal[k] for k in ["min_kurtosis", "min_qrs_agreement"]},
                                       "linha_escolhida_validacao": best.to_dict(), "regra": K})
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.6), sharex=True, sharey="row")
    for j, desc in enumerate(CFG["noise"]["records"].values()):
        t = tab[tab["ruido"] == desc].sort_values("snr_db")
        for i, met in enumerate(["sens", "esp"]):
            ax = axes[i, j]
            ax.plot(t["snr_db"], t[f"{met}_sem_sqi"], color=C1, lw=2, marker="o", ms=4, label="sem SQI")
            ax.plot(t["snr_db"], t[f"{met}_sqi_inicial"], color=C3, lw=2, marker="o", ms=4, ls="--", label="SQI inicial (janelas aprovadas)")
            ax.plot(t["snr_db"], t[f"{met}_sqi_calibrado"], color=C2, lw=2, marker="o", ms=4, label="SQI calibrado (janelas aprovadas)")
            style(ax, title=desc if i == 0 else None, xlabel="SNR (dB)" if i == 1 else None,
                  ylabel=("sensibilidade" if met == "sens" else "especificidade") if j == 0 else None)
    axes[0, 0].invert_xaxis()  # eixo x compartilhado: inverter uma vez
    axes[0, 0].set_ylim(0.0, 1.02)
    axes[1, 0].set_ylim(0.0, 1.02)
    axes[1, 0].legend(fontsize=7, frameon=False, loc="lower left")
    fig.suptitle("Experimento F — logreg sob ruído real (MIT-BIH NSTDB), teste A; ruído aumenta para a direita",
                 fontsize=10, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "expF_robustness.png", dpi=140)
    plt.close(fig)


# ------------------------------------------------------------------ G: ritmos fora de treino
def exp_g(c: Ctx):
    out = RES / "expG"
    out.mkdir(parents=True, exist_ok=True)
    parts = []
    sh = c.ch[c.ch["source"] == "shaoxing"]
    nb = c.ch[c.ch["source"] == "ningbo"]
    for base, d in [("Shaoxing", sh), ("PTB-XL", c.pt)]:
        x = d[d["group"] == "FORA_DE_TREINO"].copy()
        x["categoria"] = x["subtype"]
        parts.append(x.assign(base=base))
        x = d[d["group"] == "SINUS_ARRITMIA"].copy()
        parts.append(x.assign(base=base, categoria="arritmia sinusal"))
    x = nb[nb["group"] == "SINUS_ARRITMIA"].copy()
    parts.append(x.assign(base="Ningbo", categoria="arritmia sinusal"))
    has = lambda d, a: d["subtype"].str.contains(rf"(?:^|\+){a}(?:\+|$)", regex=True)  # noqa: E731
    x = nb[(nb["group"] == "FORA_DE_TREINO") & has(nb, "AF")].copy()
    parts.append(x.assign(base="Ningbo", categoria="AF (\"flutter\") — rótulo duvidoso, D14"))
    for a in ["PVT", "VF", "VFL"]:
        x = nb[(nb["group"] == "FORA_DE_TREINO") & has(nb, a)].copy()
        parts.append(x.assign(base="Ningbo", categoria=f"{a} — rótulo não verificado, D15"))
    # referências: AFIB e sinusal do teste A
    te = c.shaoxing("test", sqi=False)
    parts.append(te[te["group"] == "AFIB"].assign(base="Shaoxing (teste A)", categoria="referência: AFIB"))
    parts.append(te[te["group"] != "AFIB"].assign(base="Shaoxing (teste A)", categoria="referência: sinusal"))
    g = pd.concat(parts, ignore_index=True)
    rows = []
    for (b, cat), x in g.groupby(["base", "categoria"]):
        ok = x[x["sqi_ok"]]
        st = ok["state"].value_counts()
        n = len(ok)
        rows.append({"base": b, "categoria": cat, "n": len(x), "sinal_ruim": float((~x["sqi_ok"]).mean()),
                     "n_sqi_ok": n, "pct_AFIB": st.get("AFIB", 0) / n if n else np.nan,
                     "pct_INCERTO": st.get("INCERTO", 0) / n if n else np.nan,
                     "pct_NAO_AFIB": st.get("NAO_AFIB", 0) / n if n else np.nan,
                     "pct_prob_acima_limiar": float((ok["p"] >= c.thr).mean()) if n else np.nan,
                     "pct_fora_do_padrao": float(ok["ood"].mean()) if n else np.nan})
    tab = pd.DataFrame(rows).sort_values(["base", "n"], ascending=[True, False])
    tab.to_csv(out / "out_of_training.csv", index=False)
    dump(out / "summary.json", {"ood_limiar_mahalanobis": c.ood.threshold, "p_confident": CFG["decision"]["p_confident"],
                                "limiar_afib": c.thr, "linhas": tab.to_dict(orient="records")})
    log(tab[tab["n"] >= 15].round(3).to_string())


# ------------------------------------------------------------------ H: monitoramento contínuo simulado
def _votes(d):
    return (d["state"] == "AFIB").to_numpy()


def _eval_config(neg, pos, n, m, V, rng, days=None):
    fa = false_alerts_per_day(neg, n, m, V["windows_per_day"], days or V["sim_days"], rng)
    out = {"N": n, "M": m, "falsos_alertas_dia": float(fa.mean()),
           "falsos_alertas_dia_p95_dias": float(np.percentile(fa, 95))}
    for L in V["episode_windows"]:
        det, first = episode_detection(neg, pos, n, m, L, 2000, rng)
        out[f"sens_episodio_{L}j"] = float(det.mean())
        out[f"tempo_alerta_mediana_s_{L}j"] = float(np.median(first[det]) * 9.6) if det.any() else np.nan
        out[f"tempo_alerta_p90_s_{L}j"] = float(np.percentile(first[det], 90) * 9.6) if det.any() else np.nan
    return out


def _blocks(v, k, days, n, m, V, rng):
    """Falsos alertas/dia com erros correlacionados: cada registro repetido por k janelas seguidas."""
    nb_ = V["windows_per_day"] // k + 1
    out = []
    for _ in range(days):
        seq = np.repeat(v[rng.integers(0, v.size, nb_)], k)[: V["windows_per_day"]]
        out.append(count_alerts(alert_condition(seq, n, m)))
    return np.array(out)


def exp_h(c: Ctx):
    out = RES / "expH"
    out.mkdir(parents=True, exist_ok=True)
    V = CFG["voting"]
    rng = np.random.default_rng(SEED)
    va = c.shaoxing("val", sqi=False)  # janelas reprovadas pelo SQI entram como não-voto
    neg_v, pos_v = _votes(va[va["y"] == 0]), _votes(va[va["y"] == 1])
    grid = []
    for m in V["m_values"]:
        for n in range(1, m + 1):
            grid.append(_eval_config(neg_v, pos_v, n, m, V, rng, days=100))
    grid = pd.DataFrame(grid)
    grid.to_csv(out / "validation_grid.csv", index=False)
    L = V["selection_episode_windows"]
    ok = grid[grid[f"sens_episodio_{L}j"] >= V["min_episode_sensitivity"]]
    best = ok.sort_values(["falsos_alertas_dia", f"tempo_alerta_mediana_s_{L}j", "M"]).iloc[0]
    n, m = int(best["N"]), int(best["M"])
    log(f"H: escolhido na validação N={n} de M={m}")
    rows = []
    sets = {"Shaoxing (teste A)": c.shaoxing("test", sqi=False),
            "PTB-XL (todo, externo)": c.ptb_binary(sqi=False)}
    for sname, d in sets.items():
        neg, pos = _votes(d[d["y"] == 0]), _votes(d[d["y"] == 1])
        for nn, mm, lab in [(1, 1, "1 de 1 (sem votação)"), (n, m, f"{n} de {m} (escolhido)")]:
            r = _eval_config(neg, pos, nn, mm, V, rng)
            r.update(conjunto=sname, configuracao=lab, fp_por_janela=float(neg.mean()), sens_por_janela=float(pos.mean()))
            rows.append(r)
    nb = c.ch[(c.ch["source"] == "ningbo") & c.ch["group"].isin(NEG)]
    for nn, mm, lab in [(1, 1, "1 de 1 (sem votação)"), (n, m, f"{n} de {m} (escolhido)")]:
        fa = false_alerts_per_day(_votes(nb), nn, mm, V["windows_per_day"], V["sim_days"], rng)
        rows.append({"conjunto": "Ningbo (só negativos)", "configuracao": lab, "N": nn, "M": mm,
                     "falsos_alertas_dia": float(fa.mean()), "falsos_alertas_dia_p95_dias": float(np.percentile(fa, 95)),
                     "fp_por_janela": float(_votes(nb).mean())})
    # análises de sensibilidade (acrescentadas após o resultado principal, D36):
    # (a) erros correlacionados: cada registro negativo repetido por ~5 min (31 janelas) — pior caso de
    #     correlação dentro da pessoa; (b) pessoas cujo ritmo de base é ectopia frequente ou arritmia sinusal.
    def blocks(v, k, days):
        return _blocks(v, k, days, n, m, V, rng)
    sens_rows = []
    for sname, d in sets.items():
        v = _votes(d[d["y"] == 0])
        fa = blocks(v, V["selection_episode_windows"], V["sim_days"])
        sens_rows.append({"cenario": "negativos correlacionados (registro repetido por ~5 min)", "conjunto": sname,
                          "configuracao": f"{n} de {m}", "falsos_alertas_dia": float(fa.mean()),
                          "falsos_alertas_dia_p95_dias": float(np.percentile(fa, 95))})
    for base, d in [("PTB-XL", c.pt), ("Shaoxing", c.ch[c.ch["source"] == "shaoxing"])]:
        for lab, mask in [("ectopia frequente", d["subtype"] == "ECTOPIA"), ("arritmia sinusal", d["group"] == "SINUS_ARRITMIA")]:
            x = d[mask]
            if len(x) < 30:
                continue
            v = _votes(x)
            for corr, fa in [("independentes", false_alerts_per_day(v, n, m, V["windows_per_day"], V["sim_days"], rng)),
                             ("correlacionados (~5 min)", blocks(v, V["selection_episode_windows"], V["sim_days"]))]:
                sens_rows.append({"cenario": f"pessoa com {lab}, janelas {corr}", "conjunto": base, "configuracao": f"{n} de {m}",
                                  "falsos_alertas_dia": float(fa.mean()), "falsos_alertas_dia_p95_dias": float(np.percentile(fa, 95)),
                                  "fp_por_janela": float(v.mean()), "n_registros": int(len(x))})
    sens_tab = pd.DataFrame(sens_rows)
    sens_tab.to_csv(out / "monitoring_sensitivity.csv", index=False)
    log(sens_tab.round(3).to_string())
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "monitoring.csv", index=False)
    log(tab.round(4).to_string())
    # curva sensibilidade (episódio ~1 min, onde há compromisso) × falsos alertas/dia, variando o corte do voto
    cuts = np.r_[0.005, 0.01, np.linspace(0.02, 0.98, 25), 0.99, 0.995, 0.999]
    Lc = V["episode_windows"][0]
    series = [((1, 1), "ind", C1, "1 de 1, janelas independentes"), ((n, m), "ind", C2, f"{n} de {m}, janelas independentes"),
              ((n, m), "corr", C3, f"{n} de {m}, erros correlacionados (~5 min)")]
    curves = []
    for sname, d in sets.items():
        ok_ = d["sqi_ok"].to_numpy() & ~d["ood"].to_numpy()
        yv = d["y"].to_numpy()
        for (nn, mm), kind, _, lab in series:
            for cut in cuts:
                vote = ok_ & (d["p"].to_numpy() >= cut)
                neg, pos = vote[yv == 0], vote[yv == 1]
                fa = (false_alerts_per_day(neg, nn, mm, V["windows_per_day"], 40, rng) if kind == "ind"
                      else _blocks(neg, V["selection_episode_windows"], 40, nn, mm, V, rng)).mean()
                det, _ = episode_detection(neg, pos, nn, mm, Lc, 1000, rng)
                curves.append({"conjunto": sname, "serie": lab, "corte": cut, "falsos_alertas_dia": fa, "sens_episodio_1min": det.mean()})
    cv = pd.DataFrame(curves)
    cv.to_csv(out / "sens_vs_false_alerts.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, sname in zip(axes, sets):
        for _, _, col, lab in series:
            t = cv[(cv["conjunto"] == sname) & (cv["serie"] == lab)].sort_values("corte")
            ax.scatter(t["falsos_alertas_dia"] + 1e-2, t["sens_episodio_1min"], color=col, s=14, label=lab, zorder=3)
        ax.axvline(1 + 1e-2, color=MUTED, lw=0.8, ls=":")
        ax.set_xscale("log")
        style(ax, title=sname, xlabel="falsos alertas por dia (log; +0,01 para exibir zero; linha pontilhada = 1/dia)",
              ylabel="sensibilidade por episódio de ~1 min" if ax is axes[0] else None)
    axes[0].legend(fontsize=7, frameon=False, loc="lower right")
    fig.suptitle("Experimento H — simulação com registros de 10 s concatenados (não é monitoramento real); cada ponto = um corte de probabilidade",
                 fontsize=9.5, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "expH_sens_vs_false_alerts.png", dpi=140)
    plt.close(fig)
    dump(out / "summary.json", {"regra_escolha": {k: V[k] for k in ["selection_episode_windows", "min_episode_sensitivity"]},
                                "escolhido": {"N": n, "M": m, **best.to_dict()},
                                "ressalva": ("Simulação: janelas são registros isolados de 10 s de pacientes diferentes, concatenados "
                                             "e tratados como independentes; transições artificiais. Erros reais de uma mesma pessoa "
                                             "são correlacionados, o que pode aumentar ou reduzir os falsos alertas."),
                                "linhas": rows, "analises_de_sensibilidade": sens_rows})


# ------------------------------------------------------------------ I: referência ao TCC (3 classes)
def exp_i(c: Ctx):
    from sklearn.metrics import confusion_matrix
    out = RES / "expI"
    out.mkdir(parents=True, exist_ok=True)
    tcc = {"fonte": "Maggioni & Rebonatto (2023), TCC UPF, Tabelas 3 e 4 (RHCB5, 3 classes)",
           "acuracia": 0.9691, "precisao_macro": 0.9691, "recall_macro": 0.9690, "f1_macro": 0.9690,
           "especificidade_macro": 0.9845, "matriz": {"AFIB": [354, 1, 1], "SB": [5, 337, 14], "NORMAL": [4, 8, 344]},
           "n_por_classe": 356, "nota": "normais do PTB-XL e arritmias da Chapman; protocolo diferente do nosso"}
    dump(RES / "reference" / "tcc_reported.json", tcc)
    labels = ["AFIB", "SB", "NORMAL"]
    rng = np.random.default_rng(SEED)
    res = {"tcc_relatado": tcc}

    def three(d):
        return np.where(d["p"] >= c.thr, "AFIB", np.where(d["hr_median"] < CFG["hr_rule"]["brady_bpm"], "SB", "NORMAL"))

    for name, d, k in [("Shaoxing teste A (balanceado, maior n possível)", c.shaoxing("test"), None),
                       ("PTB-XL externo (balanceado, 356 por classe como o TCC)", c.pt[c.pt["sqi_ok"]], CFG["experiment_i"]["tcc_test_per_class"])]:
        g = d["group"].map({"AFIB": "AFIB", "SINUS_BRADY": "SB", "SINUS_NORMAL": "NORMAL"})
        d = d[g.notna()].assign(cls=g[g.notna()])
        kk = k or d["cls"].value_counts().min()
        bal = pd.concat([x.iloc[rng.permutation(len(x))[:kk]] for _, x in d.groupby("cls")])
        pred = three(bal)
        cm = confusion_matrix(bal["cls"], pred, labels=labels)
        rec = cm.diagonal() / cm.sum(1)
        prec = cm.diagonal() / np.maximum(cm.sum(0), 1)
        spec = [(cm.sum() - cm[i].sum() - cm[:, i].sum() + cm[i, i]) / (cm.sum() - cm[i].sum()) for i in range(3)]
        f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
        res[name] = {"n_por_classe": int(kk), "acuracia": float(cm.diagonal().sum() / cm.sum()),
                     "precisao_macro": float(prec.mean()), "recall_macro": float(rec.mean()), "f1_macro": float(f1.mean()),
                     "especificidade_macro": float(np.mean(spec)), "recall_por_classe": dict(zip(labels, rec.round(4).tolist())),
                     "matriz": {lab: cm[i].tolist() for i, lab in enumerate(labels)}}
        log(name, json.dumps(res[name], ensure_ascii=False))
    res["ressalva"] = ("Comparação apenas de referência: bases, divisão, classes e pré-processamento diferem do TCC. "
                       "Saída de 3 classes = modelo AFIB (logreg) + regra de FC (< 60 bpm -> SB).")
    dump(out / "summary.json", res)


EXPS = {"b": exp_b, "c": exp_c, "d": exp_d, "e": exp_e, "f": exp_f, "f2": exp_f2, "g": exp_g, "h": exp_h, "i": exp_i}

if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    which = list(EXPS) if which == ["all"] else which
    t = time.time()
    ctx = Ctx()
    log(f"contexto pronto ({time.time() - t:.0f}s); limiar logreg {ctx.thr:.4f}; OOD {ctx.ood.threshold:.2f}")
    for w in which:
        t = time.time()
        log(f"===== experimento {w.upper()} =====")
        EXPS[w](ctx)
        log(f"({time.time() - t:.0f}s)")
