"""Experimento A — AFIB vs. sinusal dentro de Chapman-Shaoxing (mesma fonte).

Fase `dev` (make train): divisão 70/15/15, ajuste de hiperparâmetros por validação cruzada
no treino, calibração e limiar na validação, escolha do modelo pela regra pré-registrada em
configs/default.yaml (experiment_a.selection_margin). Não toca no teste.

Fase `test` (make evaluate): exige que results/expA/selection.json esteja commitado no Git
(prova de que a escolha veio antes) e que o teste ainda não tenha sido aberto. Avalia todos
os modelos e o baseline uma única vez e grava a trava results/expA/TEST_OPENED.json.

    python scripts/exp_a.py dev
    python scripts/exp_a.py test
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV, StratifiedKFold

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import evaluate as ev  # noqa: E402
from src.baseline import rr_irregularity_score  # noqa: E402
from src.config import ROOT, load_config  # noqa: E402
from src.features import FEATURE_NAMES  # noqa: E402
from src.models import GRIDS, PlattCalibrator, make_feature_model, predict_cnn, train_cnn  # noqa: E402
from src.preprocess import resample_to_target  # noqa: E402
from src.splits import assert_disjoint, dedupe, split_records  # noqa: E402

CFG = load_config()
A = CFG["experiment_a"]
SEED = CFG["seed"]
RES = CFG["paths"]["results"] / "expA"
MOD = CFG["paths"]["processed"] / "expA_models"


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def log(*a):
    print(*a, flush=True)


def load_data() -> pd.DataFrame:
    f = pd.read_parquet(CFG["paths"]["processed"] / "chapman_features.parquet")
    f = f[(f["source"] == A["source"]) & f["group"].isin(A["positive"] + A["negative"])]
    f, n_dup = dedupe(f)
    f = f.reset_index(drop=True)
    f["y"] = f["group"].isin(A["positive"]).astype(int)
    f.attrs["n_duplicatas_removidas"] = n_dup
    return f


def get_split(f: pd.DataFrame) -> pd.DataFrame:
    p = RES / "split.csv"
    if p.exists():
        s = pd.read_csv(p)
        f = f.merge(s[["record_id", "split"]], on="record_id", how="left")
        if f["split"].isna().any():
            raise RuntimeError("split.csv não cobre todos os registros; apague-o para refazer a divisão")
        return f
    f["split"] = split_records(f, tuple(A["split"]), SEED).values
    assert_disjoint(f)
    f[["record_id", "group", "split", "sqi_ok"]].to_csv(p, index=False)
    return f


def raw_windows(rows: np.ndarray) -> np.ndarray:
    X = np.load(CFG["paths"]["interim"] / "chapman_leadI_500hz.npy", mmap_mode="r")
    return np.stack([resample_to_target(np.asarray(X[r], float), 500) for r in rows]).astype(np.float32)


def windows(wins: np.ndarray) -> np.ndarray:
    W = np.load(CFG["paths"]["processed"] / "chapman_windows.npy", mmap_mode="r")
    return np.asarray(W[wins])


def scores(name: str, art: dict, d: pd.DataFrame) -> np.ndarray:
    if name == "baseline_rr":
        return rr_irregularity_score(d)
    if name == "cnn":
        return predict_cnn(art["model"], windows(d["win"].to_numpy()))
    return art["model"].predict_proba(d[FEATURE_NAMES])[:, 1]


def load_artifact(name: str) -> dict:
    if name == "cnn":
        import torch

        from src.models import build_cnn

        art = joblib.load(MOD / "cnn_meta.joblib")
        m = build_cnn()
        m.load_state_dict(torch.load(MOD / "cnn_state.pt"))
        m.eval()
        art["model"] = m
        return art
    return joblib.load(MOD / f"{name}.joblib")


# ------------------------------------------------------------------ fase dev
def dev():
    RES.mkdir(parents=True, exist_ok=True)
    MOD.mkdir(parents=True, exist_ok=True)
    f = get_split(load_data())
    tr = f[(f["split"] == "train") & f["sqi_ok"]]
    va = f[(f["split"] == "val") & f["sqi_ok"]]
    info = {"n_duplicatas_removidas": int(f.attrs.get("n_duplicatas_removidas", 0)),
            "contagens": f.groupby(["split", "group"]).size().unstack(fill_value=0).to_dict(orient="index"),
            "sqi_reprovado_por_split": f.groupby("split")["sqi_ok"].apply(lambda s: int((~s).sum())).to_dict(),
            "n_treino": len(tr), "n_val": len(va), "pos_treino": int(tr["y"].sum()), "pos_val": int(va["y"].sum())}
    log(json.dumps(info, indent=1))

    cv = StratifiedKFold(A["cv_folds"], shuffle=True, random_state=SEED)
    val, cv_rows = {}, []
    for name in [c for c in A["candidates"] if c != "cnn"]:
        t = time.time()
        gs = GridSearchCV(make_feature_model(name, SEED), GRIDS[name], scoring="average_precision", cv=cv,
                          n_jobs=2, refit=True)
        gs.fit(tr[FEATURE_NAMES], tr["y"])
        i = gs.best_index_
        cv_rows.append({"modelo": name, "melhores_params": json.dumps(gs.best_params_, default=str),
                        "cv_auprc_media": gs.cv_results_["mean_test_score"][i],
                        "cv_auprc_dp": gs.cv_results_["std_test_score"][i], "segundos": time.time() - t})
        log(f"{name}: CV AUPRC {cv_rows[-1]['cv_auprc_media']:.4f} ± {cv_rows[-1]['cv_auprc_dp']:.4f} {gs.best_params_}")
        art = {"model": gs.best_estimator_, "features": FEATURE_NAMES}
        val[name] = art
    if "cnn" in A["candidates"]:
        t = time.time()
        model, cinfo = train_cnn(raw_windows(tr["row"].to_numpy()), tr["y"].to_numpy(), SEED, log=log)
        import torch

        torch.save(model.state_dict(), MOD / "cnn_state.pt")
        cv_rows.append({"modelo": "cnn", "melhores_params": json.dumps(cinfo), "cv_auprc_media": np.nan,
                        "cv_auprc_dp": np.nan, "segundos": time.time() - t})
        val["cnn"] = {"model": model, "info": cinfo}
    pd.DataFrame(cv_rows).to_csv(RES / "cv_results.csv", index=False)

    # calibração + limiar na validação; métricas de validação
    report, selection_vals = {}, {}
    for name in ["baseline_rr"] + list(val):
        art = val.get(name, {})
        s = scores(name, art, va)
        if name == "baseline_rr":
            p, cal = s, None
        else:
            cal = PlattCalibrator().fit(s, va["y"])
            p = cal.transform(s)
        thr = ev.threshold_for_specificity(va["y"].to_numpy(), p, A["threshold_rule"]["min_specificity"])
        m = ev.point_metrics(va["y"], p, thr)
        m["ic95"] = ev.bootstrap(va["y"], p, thr, n=1000, seed=SEED)
        m["limiar"] = thr
        report[name] = m
        if name != "baseline_rr":
            selection_vals[name] = m["auprc"]
            art.update(calibrator=cal, threshold=thr, trained_at=dt.datetime.now().isoformat(timespec="seconds"),
                       config_commit=git_head())
            if name == "cnn":
                joblib.dump({k: v for k, v in art.items() if k != "model"}, MOD / "cnn_meta.joblib")
            else:
                joblib.dump(art, MOD / f"{name}.joblib")
        else:
            joblib.dump({"threshold": thr}, MOD / "baseline_rr.joblib")
        log(f"[val] {name}: AUPRC {m['auprc']:.4f} AUROC {m['auroc']:.4f} sens {m['sensibilidade']:.3f} "
            f"esp {m['especificidade']:.3f} limiar {thr:.4f}")
    (RES / "validation.json").write_text(json.dumps({"info": info, "metricas_validacao": report}, indent=2,
                                                    ensure_ascii=False, default=float))

    best = max(selection_vals.values())
    chosen = next(c for c in A["candidates"] if selection_vals[c] >= best - A["selection_margin"])
    sel = {
        "regra": (f"modelo mais simples, na ordem {A['candidates']}, cujo AUPRC de validação esteja a no máximo "
                  f"{A['selection_margin']} do melhor"),
        "margem": A["selection_margin"], "auprc_validacao": selection_vals, "melhor_auprc": best,
        "escolhido": chosen, "limiar_regra": A["threshold_rule"],
        "data": dt.datetime.now().isoformat(timespec="seconds"), "commit_do_codigo": git_head(),
        "nota": "gerado antes de qualquer acesso ao conjunto de teste; ver TEST_OPENED.json",
    }
    (RES / "selection.json").write_text(json.dumps(sel, indent=2, ensure_ascii=False))
    log(f"ESCOLHIDO: {chosen} (melhor AUPRC val {best:.4f})")


# ------------------------------------------------------------------ fase test
def _committed(p: Path) -> bool:
    rel = str(p.relative_to(ROOT))
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=ROOT).returncode == 0
    return tracked and clean


def test(force: bool = False):
    lock = RES / "TEST_OPENED.json"
    if lock.exists() and not force:
        sys.exit(f"o teste do experimento A já foi aberto ({lock}); use --force apenas para reprodução idêntica")
    sel_p = RES / "selection.json"
    if not (sel_p.exists() and _committed(sel_p) and _committed(RES / "split.csv")):
        sys.exit("selection.json e split.csv precisam estar commitados antes de abrir o teste (pré-registro)")
    sel = json.loads(sel_p.read_text())
    f = get_split(load_data())
    te_all = f[f["split"] == "test"]
    te = te_all[te_all["sqi_ok"]]
    lock.write_text(json.dumps({"aberto_em": dt.datetime.now().isoformat(timespec="seconds"), "commit": git_head(),
                                "selection_sha": subprocess.run(["git", "hash-object", str(sel_p)], capture_output=True,
                                                                text=True).stdout.strip(), "force": force}, indent=2))
    names = ["baseline_rr"] + A["candidates"]
    out, preds = {}, {}
    for name in names:
        art = joblib.load(MOD / "baseline_rr.joblib") if name == "baseline_rr" else load_artifact(name)
        s = scores(name, art, te)
        p = s if name == "baseline_rr" else art["calibrator"].transform(s)
        out[name] = ev.full_report(te["y"].to_numpy(), p, art["threshold"], A["bootstrap"], SEED,
                                   calib=name != "baseline_rr")
        preds[name] = p
        log(f"[teste] {name}: AUPRC {out[name]['auprc']:.4f} sens {out[name]['sensibilidade']:.3f} "
            f"esp {out[name]['especificidade']:.3f}")
    ch = sel["escolhido"]
    y = te["y"].to_numpy().astype(bool)
    correct = {n: (preds[n] >= (joblib.load(MOD / "baseline_rr.joblib")["threshold"] if n == "baseline_rr"
                                else load_artifact(n)["threshold"])) == y for n in names}
    extra = {"mcnemar_escolhido_vs_baseline": ev.mcnemar(correct[ch], correct["baseline_rr"])}
    # secundário: sem o filtro de SQI (modelo aplicado a todas as janelas de teste)
    art = load_artifact(ch)
    p_all = art["calibrator"].transform(scores(ch, art, te_all))
    extra["escolhido_sem_filtro_sqi"] = ev.point_metrics(te_all["y"], p_all, art["threshold"])
    extra["sqi_reprovado_teste_por_grupo"] = te_all.groupby("group")["sqi_ok"].apply(
        lambda s: {"n": int(len(s)), "reprovados": int((~s).sum())}).to_dict()
    # falso AFIB por grupo de negativo
    te2 = te.assign(p_ch=preds[ch], p_bl=preds["baseline_rr"])
    thr_bl = joblib.load(MOD / "baseline_rr.joblib")["threshold"]
    extra["taxa_afib_previsto_por_grupo"] = {
        g: {"n": int(len(x)), ch: float((x["p_ch"] >= art["threshold"]).mean()),
            "baseline_rr": float((x["p_bl"] >= thr_bl).mean())} for g, x in te2.groupby("group")}
    # subgrupos (idade, sexo)
    rows = []
    bins = [0, 30, 55, 70, 200]
    labels = ["<30", "30-54", "55-69", "70+"]
    te2["faixa"] = pd.cut(te2["age"], bins, labels=labels, right=False)
    for col in ["faixa", "sex"]:
        for k, x in te2.groupby(col, observed=True):
            for n, pc, thr in [(ch, "p_ch", art["threshold"]), ("baseline_rr", "p_bl", thr_bl)]:
                m = ev.point_metrics(x["y"], x[pc], thr)
                ci = ev.bootstrap(x["y"], x[pc], thr, n=1000, seed=SEED) if x["y"].nunique() == 2 else {}
                rows.append({"subgrupo": col, "valor": str(k), "modelo": n, "n_pos": int(x["y"].sum()),
                             "n_neg": int((1 - x["y"]).sum()), "sensibilidade": m["sensibilidade"],
                             "sens_ic95": ci.get("sensibilidade"), "especificidade": m["especificidade"],
                             "esp_ic95": ci.get("especificidade"), "auroc": m.get("auroc")})
    pd.DataFrame(rows).to_csv(RES / "test_subgroups.csv", index=False)
    (RES / "test.json").write_text(json.dumps({"escolhido": ch, "n_teste": len(te), "n_pos": int(y.sum()),
                                               "prevalencia_teste": float(y.mean()), "metricas": out, **extra},
                                              indent=2, ensure_ascii=False, default=float))
    tab = []
    for n in names:
        m = out[n]
        tab.append({"modelo": n, "escolhido": n == ch, **{k: m.get(k) for k in
                    ["auprc", "auroc", "sensibilidade", "especificidade", "ppv", "npv", "f1", "brier", "ece"]},
                    "auprc_ic95": m["ic95"]["auprc"], "sens_ic95": m["ic95"]["sensibilidade"],
                    "esp_ic95": m["ic95"]["especificidade"], "ppv_prev_1pct": m["ppv_prevalencia"]["0.01"],
                    "tp": m["tp"], "fp": m["fp"], "tn": m["tn"], "fn": m["fn"], "limiar": m["limiar"]})
    pd.DataFrame(tab).to_csv(RES / "test_table.csv", index=False)
    log("teste avaliado e trancado:", lock)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["dev", "test"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    dev() if a.phase == "dev" else test(a.force)
