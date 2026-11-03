"""Benchmark da inferência a bordo: latência por etapa, memória e tamanho dos artefatos.

Mede NA MÁQUINA ATUAL, que fica identificada no resultado. Não inventa números de Raspberry Pi:
rode este mesmo script no Pi para obter os dele.

    python scripts/benchmark.py [--n 500] [--threads 1]   -> results/benchmark/benchmark_<host>.json
"""
from __future__ import annotations

import argparse
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=500, help="janelas medidas")
ap.add_argument("--threads", type=int, default=1, help="threads de BLAS (o Pi roda a inferência em 1 núcleo)")
A = ap.parse_args()
for v in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[v] = str(A.threads)

import datetime as dt  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402
import tracemalloc  # noqa: E402
from pathlib import Path  # noqa: E402

import psutil  # noqa: E402

PROC = psutil.Process()
rss0 = PROC.memory_info().rss
t_imp = time.perf_counter()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa: E402

from src import features as F  # noqa: E402
from src import sqi as SQ  # noqa: E402
from src.config import ROOT  # noqa: E402
from src.demo import SCENARIOS, Stream, get_pack  # noqa: E402
from src.inference import AFibDetector, Monitor  # noqa: E402
from src.preprocess import preprocess_window  # noqa: E402
from src.qrs import detect_qrs  # noqa: E402

t_imp = time.perf_counter() - t_imp
det = AFibDetector()
rss_loaded = PROC.memory_info().rss


def cpu_model():
    """'model name' (x86/ARM), ou 'Model' (Raspberry Pi: ex. 'Raspberry Pi 4 Model B'), ou 'Hardware'."""
    info = {}
    try:
        for ln in open("/proc/cpuinfo"):
            if ":" in ln:
                k, v = ln.split(":", 1)
                info.setdefault(k.strip(), v.strip())
    except OSError:
        pass
    parts = [info[k] for k in ["model name", "Hardware"] if k in info]
    if "Model" in info:
        parts.append(info["Model"])
    return " | ".join(parts) or platform.processor() or platform.machine()


def stats(v):
    v = np.asarray(v) * 1000
    return {"mediana_ms": float(np.median(v)), "p95_ms": float(np.percentile(v, 95)), "max_ms": float(v.max()),
            "media_ms": float(v.mean())}


def main():
    pack = get_pack()
    wins = []
    for i in range(A.n):
        st = Stream(pack, SCENARIOS[i % len(SCENARIOS)], seed=i)
        wins.append(st.next_window()[0])
    # aquecimento
    for w in wins[:20]:
        det.predict(w)
    T = {k: [] for k in ["preprocess", "qrs", "atributos", "sqi", "modelo_json", "predict_total", "monitor_update"]}
    for w in wins:
        t = time.perf_counter(); x = preprocess_window(w); T["preprocess"].append(time.perf_counter() - t)  # noqa: E702
        t = time.perf_counter(); r = detect_qrs(x); T["qrs"].append(time.perf_counter() - t)  # noqa: E702
        t = time.perf_counter(); f = F.extract(x, r=r); T["atributos"].append(time.perf_counter() - t)  # noqa: E702
        t = time.perf_counter(); SQ.passes(SQ.compute(w, x, r=r), det.sqi_cfg); T["sqi"].append(time.perf_counter() - t)  # noqa: E702
        X = np.array([[f[k] for k in det.features]])
        t = time.perf_counter(); det.prob(X); det.ood_distance(X); T["modelo_json"].append(time.perf_counter() - t)  # noqa: E702
        t = time.perf_counter(); det.predict(w); T["predict_total"].append(time.perf_counter() - t)  # noqa: E702
    mon = Monitor(det)
    for w in wins:
        t = time.perf_counter(); mon.update(w); T["monitor_update"].append(time.perf_counter() - t)  # noqa: E702
    out = {k: stats(v) for k, v in T.items()}
    # ONNX (opcional no Pi): só a parte do modelo
    onnx_p = ROOT / "models" / "afib_logreg_v1.onnx"
    try:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = A.threads
        sess = ort.InferenceSession(str(onnx_p), so, providers=["CPUExecutionProvider"])
        Xs = [np.array([[F.extract(preprocess_window(w))[k] for k in det.features]], np.float32) for w in wins[:200]]
        tt = []
        for X in Xs:
            t = time.perf_counter(); sess.run(None, {"features": X}); tt.append(time.perf_counter() - t)  # noqa: E702
        out["modelo_onnx"] = stats(tt)
    except Exception as e:
        out["modelo_onnx"] = {"erro": f"{type(e).__name__}: {e}"}
    tracemalloc.start()
    for w in wins[:50]:
        det.predict(w)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    vm = psutil.virtual_memory()
    res = {
        "aviso": "Medido na máquina abaixo, NÃO em Raspberry Pi. Rode este script no Pi para os números dele.",
        "data": dt.datetime.now().isoformat(timespec="seconds"),
        "maquina": {"host": socket.gethostname(), "cpu": cpu_model(), "arquitetura": platform.machine(),
                    "nucleos_logicos": psutil.cpu_count(), "ram_total_gb": round(vm.total / 2**30, 1),
                    "so": platform.platform(), "python": platform.python_version(), "numpy": np.__version__,
                    "scipy": __import__("scipy").__version__, "threads_blas": A.threads},
        "n_janelas": len(wins), "janela": "2.400 amostras a 250 Hz (9,6 s)", "fonte_janelas": pack["fonte"],
        "latencia": out,
        "tempo_real": {"janela_s": 9.6, "fracao_do_tempo_real_mediana": out["monitor_update"]["mediana_ms"] / 9600},
        "memoria": {"rss_inicial_mb": rss0 / 2**20, "rss_apos_import_e_modelo_mb": rss_loaded / 2**20,
                    "rss_final_mb": PROC.memory_info().rss / 2**20, "pico_alocado_por_predict_kb": peak / 1024,
                    "tempo_import_s": t_imp},
        "artefatos_kb": {p.name: round(p.stat().st_size / 1024, 1) for p in sorted((ROOT / "models").glob("afib_logreg_v1*"))},
    }
    p = ROOT / "results" / "benchmark" / f"benchmark_{socket.gethostname()}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
