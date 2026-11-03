"""Exporta o modelo escolhido (regressão logística do experimento A) para artefatos leves.

    python scripts/export_model.py

Gera em models/:
    afib_logreg_v1.json   parâmetros em numpy puro (imputação, padronização, coeficientes,
                          calibração Platt, limiar, detector fora-do-padrão, SQI e votação) + metadados
    afib_logreg_v1.onnx   o pipeline do scikit-learn em ONNX (escore antes da calibração), se a conversão
                          for possível; a inferência padrão usa o JSON (só numpy/scipy)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, load_config  # noqa: E402
from src.decision import OODDetector  # noqa: E402
from src.features import FEATURE_NAMES  # noqa: E402
from src.splits import dedupe  # noqa: E402

CFG = load_config()
OUT = ROOT / "models"
NAME = "afib_logreg_v1"


def main():
    OUT.mkdir(exist_ok=True)
    art = joblib.load(CFG["paths"]["processed"] / "expA_models" / "logreg.joblib")
    pipe = art["model"]
    imp, sc, clf = pipe.named_steps["imp"], pipe.named_steps["sc"], pipe.named_steps["clf"]
    # detector fora-do-padrão: mesmo ajuste dos experimentos (treino/validação de Shaoxing)
    f, _ = dedupe(pd.read_parquet(CFG["paths"]["processed"] / "chapman_features.parquet"))
    sp = pd.read_csv(CFG["paths"]["results"] / "expA" / "split.csv")[["record_id", "split"]]
    f = f.merge(sp, on="record_id")
    f = f[f["sqi_ok"]]
    ood = OODDetector(pipe).fit(f[f["split"] == "train"][FEATURE_NAMES], f[f["split"] == "val"][FEATURE_NAMES])
    manifest = json.loads((CFG["paths"]["results"] / "audit" / "data_manifest.json").read_text())
    sel = json.loads((CFG["paths"]["results"] / "expA" / "selection.json").read_text())
    H = json.loads((CFG["paths"]["results"] / "expH" / "summary.json").read_text())["escolhido"]
    sqi_onboard = {**CFG["sqi"], **CFG["sqi_onboard"]}
    model = {
        "nome": NAME,
        "tarefa": "AFIB vs. ritmo sinusal em janela de 9,6 s de ECG derivação I a 250 Hz",
        "aviso": "Protótipo de pesquisa e apoio à decisão. Não é dispositivo médico nem diagnóstico. "
                 "Não validado em astronautas nem em microgravidade.",
        "features": FEATURE_NAMES,
        "imputer_statistics": imp.statistics_.tolist(),
        "indicator_features": imp.indicator_.features_.tolist() if imp.indicator_ is not None else [],
        "scaler_mean": sc.mean_.tolist(), "scaler_scale": sc.scale_.tolist(),
        "coef": clf.coef_.ravel().tolist(), "intercept": float(clf.intercept_[0]),
        "platt_coef": float(art["calibrator"].lr.coef_.ravel()[0]),
        "platt_intercept": float(art["calibrator"].lr.intercept_[0]),
        "threshold": float(art["threshold"]), "p_confident": CFG["decision"]["p_confident"],
        "ood_location": ood.cov.location_.tolist(), "ood_precision": ood.cov.precision_.tolist(),
        "ood_threshold": ood.threshold,
        "sqi": sqi_onboard, "voting": {"N": int(H["N"]), "M": int(H["M"])}, "hr_rule": CFG["hr_rule"],
        "signal": CFG["target_signal"], "preprocess": CFG["preprocess"],
        "metadados": {
            "exportado_em": dt.datetime.now().isoformat(timespec="seconds"),
            "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "treino": "Chapman-Shaoxing, split de treino do experimento A (results/expA/split.csv)",
            "escolha": sel, "dados_sha256": {k: v["sha256"] for k, v in manifest.items()},
            "metricas": "results/expA/test.json (interno), results/expB/ (externo PTB-XL)",
        },
    }
    p = OUT / f"{NAME}.json"
    p.write_text(json.dumps(model, indent=1, ensure_ascii=False))
    print(f"{p} ({p.stat().st_size / 1024:.1f} KB)")

    (OUT / f"{NAME}.sha256").write_text(hashlib.sha256(p.read_bytes()).hexdigest() + f"  {p.name}\n")
    # ONNX: o skl2onnx não converte o SimpleImputer com indicadores; como o modelo é linear, o grafo é
    # montado à mão (imputação, indicadores, padronização, produto escalar, Platt, sigmoide).
    po = OUT / f"{NAME}.onnx"
    po.write_bytes(build_onnx(model).SerializeToString())
    import onnxruntime as ort

    X = f[FEATURE_NAMES].to_numpy(np.float32)
    sess = ort.InferenceSession(str(po), providers=["CPUExecutionProvider"])
    got = sess.run(None, {"features": X})[0].ravel()
    ref = art["calibrator"].transform(pipe.predict_proba(f[FEATURE_NAMES])[:, 1])
    err = float(np.abs(got - ref).max())
    print(f"{po} ({po.stat().st_size / 1024:.1f} KB); diferença máx. vs scikit-learn em {len(X)} janelas: {err:.2e}")
    if err > 1e-4:
        raise SystemExit("ONNX diverge do modelo original")


def build_onnx(m: dict):
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    nf = len(m["features"])
    ind = np.array(m["indicator_features"], dtype=np.int64)
    c = lambda name, arr: numpy_helper.from_array(np.asarray(arr), name)  # noqa: E731
    w = np.asarray(m["coef"], np.float32).reshape(-1, 1) / np.asarray(m["scaler_scale"], np.float32).reshape(-1, 1)
    b = np.float32(m["intercept"] - float(np.dot(np.asarray(m["coef"]), np.asarray(m["scaler_mean"]) / np.asarray(m["scaler_scale"]))))
    lim = float(np.log((1 - 1e-6) / 1e-6))  # mesmo recorte do PlattCalibrator
    nodes = [
        helper.make_node("IsNaN", ["features"], ["isnan"]),
        helper.make_node("Where", ["isnan", "stats", "features"], ["imputed"]),
        helper.make_node("Gather", ["isnan", "ind_idx"], ["ind_bool"], axis=1),
        helper.make_node("Cast", ["ind_bool"], ["ind_f"], to=TensorProto.FLOAT),
        helper.make_node("Concat", ["imputed", "ind_f"], ["z"], axis=1),
        helper.make_node("MatMul", ["z", "w"], ["zw"]),
        helper.make_node("Add", ["zw", "b"], ["logit"]),
        helper.make_node("Clip", ["logit", "lo", "hi"], ["logit_c"]),
        helper.make_node("Mul", ["logit_c", "pa"], ["t1"]),
        helper.make_node("Add", ["t1", "pb"], ["t2"]),
        helper.make_node("Sigmoid", ["t2"], ["prob_afib"]),
    ]
    inits = [c("stats", np.asarray(m["imputer_statistics"], np.float32)), c("ind_idx", ind), c("w", w),
             c("b", np.array([b], np.float32)), c("lo", np.array(-lim, np.float32)), c("hi", np.array(lim, np.float32)),
             c("pa", np.array([m["platt_coef"]], np.float32)), c("pb", np.array([m["platt_intercept"]], np.float32))]
    g = helper.make_graph(nodes, m["nome"], [helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, nf])],
                          [helper.make_tensor_value_info("prob_afib", TensorProto.FLOAT, [None, 1])], inits)
    mod = helper.make_model(g, opset_imports=[helper.make_opsetid("", 17)], producer_name="ProjetoNasa2026")
    mod.ir_version = 9
    onnx.checker.check_model(mod)
    return mod

if __name__ == "__main__":
    main()
