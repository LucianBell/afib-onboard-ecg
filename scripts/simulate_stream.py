"""Simula o Pi recebendo ECG do Holter em tempo acelerado: janela deslizante, votação temporal e
eventos em JSON (uma linha por janela; alertas marcados com "alerta_novo": true).

A transmissão Holter → Pi não é implementada: o stream é a concatenação de registros públicos de 10 s
(replay; ver src/demo.py) ou sinal sintético. Transições entre registros são artificiais.

    python scripts/simulate_stream.py                                    # plano padrão, 50x tempo real
    python scripts/simulate_stream.py --plano afib:20 --velocidade 0     # o mais rápido possível
    python scripts/simulate_stream.py --saida results/stream/eventos.jsonl --so-alertas
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.demo import SCENARIOS, Stream, get_pack  # noqa: E402
from src.inference import Monitor  # noqa: E402

PLANO_PADRAO = "sinusal:15,afib:15,sinusal:10,bradicardia:10,taquicardia:10,sinal_ruim:8,sinusal:6"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plano", default=PLANO_PADRAO, help="cenario:janelas,... cenários: " + ", ".join(SCENARIOS))
    ap.add_argument("--velocidade", type=float, default=50.0, help="x tempo real (0 = sem espera)")
    ap.add_argument("--passo", type=int, default=2500, help="passo da janela deslizante em amostras (250 Hz)")
    ap.add_argument("--sintetico", action="store_true", help="usa ECG sintético em vez do replay")
    ap.add_argument("--saida", default=None, help="arquivo .jsonl (padrão: stdout)")
    ap.add_argument("--so-alertas", action="store_true", help="emite só mudanças de estado e alertas novos")
    ap.add_argument("--semente", type=int, default=0)
    a = ap.parse_args(argv)

    pack = get_pack(prefer_replay=not a.sintetico)
    plano = [(s.split(":")[0], int(s.split(":")[1])) for s in a.plano.split(",")]
    for s, _ in plano:
        if s not in SCENARIOS:
            sys.exit(f"cenário desconhecido: {s}")
    out = open(a.saida, "w") if a.saida else sys.stdout
    if a.saida:
        Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"tipo": "inicio", "fonte": pack["fonte"], "aviso": pack["banner"],
                      "plano": a.plano, "velocidade": a.velocidade}, ensure_ascii=False), file=out, flush=True)
    stream, mon = Stream(pack, plano[0][0], stride=a.passo, seed=a.semente), Monitor()
    last, cont, n_alert, lat = None, Counter(), 0, []
    for cenario, n in plano:
        stream.set_scenario(cenario)
        for _ in range(n):
            w, t = stream.next_window()
            r = mon.update(w, t=round(t, 1))
            r["cenario_verdadeiro"] = cenario
            r["registro"] = stream.src_ids[-1]
            cont[(cenario, r["estado"])] += 1
            lat.append(r["latencia_ms"])
            n_alert += r["alerta_novo"]
            if not a.so_alertas or r["alerta_novo"] or r["estado"] != last:
                ev = {k: r[k] for k in ["janela", "t_s", "estado", "severidade", "alerta_novo", "prob_afib", "fc",
                                        "motivo", "cenario_verdadeiro", "registro", "latencia_ms"]}
                ev["sqi_aprovado"] = r["sqi"].get("aprovado")
                print(json.dumps(ev, ensure_ascii=False), file=out, flush=True)
            last = r["estado"]
            if a.velocidade > 0:
                time.sleep(a.passo / 250 / a.velocidade)
    resumo = {"tipo": "resumo", "janelas": sum(n for _, n in plano), "alertas_afib": int(n_alert),
              "latencia_ms_mediana": sorted(lat)[len(lat) // 2],
              "estados_por_cenario": {f"{c} -> {e}": k for (c, e), k in sorted(cont.items())}}
    print(json.dumps(resumo, ensure_ascii=False), file=out, flush=True)
    if a.saida:
        out.close()
        print(json.dumps(resumo, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
