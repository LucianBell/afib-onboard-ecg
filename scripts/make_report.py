"""Gera README.md e MODEL_CARD.md a partir de docs/templates/*.md (make report).

Todo número dos documentos entra por um marcador {{chave}} preenchido aqui a partir de um arquivo
em results/ (ou de configs/default.yaml, para constantes de projeto). A origem de cada valor é
gravada em results/readme_numbers.json. tests/test_report_numbers.py confere que os documentos
não foram editados à mão e que o template não tem números fora dos marcadores.

    python scripts/make_report.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, load_config  # noqa: E402

RES = ROOT / "results"
TPL = ROOT / "docs" / "templates"
DOCS = {"README.md": "README.template.md", "MODEL_CARD.md": "MODEL_CARD.template.md"}


class Values:
    def __init__(self, allow_missing: bool = False):
        self.v: dict[str, dict] = {}
        self.allow_missing = allow_missing
        self.falhas: dict[str, str] = {}

    def secao(self, nome):
        """Em modo tolerante (subconjunto), uma seção sem dados vira 'n/d' em vez de abortar."""
        outer = self

        class _S:
            def __enter__(self):
                return self

            def __exit__(self, et, ev, tb):
                if et is not None and outer.allow_missing and issubclass(et, (KeyError, IndexError, StopIteration, ValueError)):
                    outer.falhas[nome] = f"{et.__name__}: {ev}"
                    return True
                return False
        return _S()

    def put(self, key, value, fonte, campo, fmt="{:.3f}"):
        if key in self.v:
            raise KeyError(f"chave duplicada: {key}")
        txt = fmt(value) if callable(fmt) else fmt.format(value)
        self.v[key] = {"valor": txt, "fonte": fonte, "campo": campo, "bruto": value if isinstance(value, (int, float, str)) else str(value)}


def j(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def ci(v):
    return ast.literal_eval(v) if isinstance(v, str) else v


INT = "{:,}".format
P1 = lambda x: f"{100 * x:.1f}%"  # noqa: E731
P0 = lambda x: f"{100 * x:.0f}%"  # noqa: E731
CI3 = lambda c: f"{c[0]:.3f}–{c[1]:.3f}"  # noqa: E731


def collect(allow_missing: bool = False) -> Values:
    V = Values(allow_missing)
    cfg = load_config()
    cf = "configs/default.yaml"
    ts = cfg["target_signal"]
    V.put("fs", ts["fs"], cf, "target_signal.fs", "{:d}")
    V.put("win", ts["window_samples"], cf, "target_signal.window_samples", INT)
    V.put("win_s", ts["window_samples"] / ts["fs"], cf, "window_samples/fs", "{:.1f}")
    V.put("band_lo", ts["band_hz"][0], cf, "target_signal.band_hz[0]", "{:g}")
    V.put("band_hi", ts["band_hz"][1], cf, "target_signal.band_hz[1]", "{:g}")
    V.put("adc_bits", ts["adc_bits"], cf, "target_signal.adc_bits", "{:d}")
    V.put("margin", cfg["experiment_a"]["selection_margin"], cf, "experiment_a.selection_margin")
    V.put("min_spec", cfg["experiment_a"]["threshold_rule"]["min_specificity"], cf, "experiment_a.threshold_rule.min_specificity", "{:.2f}")
    V.put("wpd", cfg["voting"]["windows_per_day"], cf, "voting.windows_per_day", INT)
    V.put("brady", cfg["hr_rule"]["brady_bpm"], cf, "hr_rule.brady_bpm", "{:d}")
    V.put("tachy", cfg["hr_rule"]["tachy_bpm"], cf, "hr_rule.tachy_bpm", "{:d}")
    V.put("n_feat", 30, "src/features.py", "len(FEATURE_NAMES)", "{:d}")
    V.put("snr0", 0, cf, "noise.snr_db (contém 0)", "{:d}")
    V.put("snrm6", min(cfg["noise"]["snr_db"]), cf, "min(noise.snr_db)", lambda x: f"−{abs(x)}")
    epw = cfg["voting"]["episode_windows"]
    V.put("ep5", epw[1] * 9.6 / 60, cf, "voting.episode_windows[1] × 9,6 s / 60", "{:.0f}")
    V.put("ep1", epw[0] * 9.6 / 60, cf, "voting.episode_windows[0] × 9,6 s / 60", "{:.0f}")
    V.put("rec_s", cfg["datasets"]["chapman"]["n_samples"] / cfg["datasets"]["chapman"]["fs"], cf, "datasets.chapman.n_samples/fs", "{:.0f}")
    V.put("inv_fold", cfg["experiment_b"]["inverse_test_fold"], cf, "experiment_b.inverse_test_fold", "{:d}")
    man = j("results/audit/data_manifest.json")
    V.put("dl_gb", sum(v["bytes"] for v in man.values()) / 1e9, "results/audit/data_manifest.json", "soma de *.bytes / 1e9", "{:.1f}")
    from src.features import FEATURE_NAMES
    assert len(FEATURE_NAMES) == 30

    # ---------------- auditoria
    with V.secao("auditoria"):
        g = pd.read_csv(RES / "audit" / "group_counts_by_source.csv", index_col=0)
        fa = "results/audit/group_counts_by_source.csv"
        for col, k in [("chapman_shaoxing", "sh"), ("chapman_ningbo", "nb"), ("ptbxl", "ptb")]:
            V.put(f"{k}_total", int(g.loc["TOTAL", col]), fa, f"TOTAL/{col}", INT)
            V.put(f"{k}_afib", int(g.loc["AFIB", col]), fa, f"AFIB/{col}", INT)
        au = j("results/audit/audit_summary.json")
        V.put("bnd_cmp", au["boundary"]["codigos_comparados"], "results/audit/audit_summary.json", "boundary.codigos_comparados", "{:d}")
        V.put("bnd_eq", au["boundary"]["codigos_com_contagem_identica_nas_duas_fontes"], "results/audit/audit_summary.json",
              "boundary.codigos_com_contagem_identica_nas_duas_fontes", "{:d}")
        cs = {(r["ritmo_shaoxing"], r["ritmo_ningbo"]): r["pares"] for r in au["cross_source_rhythm"]}
        V.put("dup_afib_af", cs[("AFIB", "AF")], "results/audit/audit_summary.json", "cross_source_rhythm[AFIB→AF].pares", "{:d}")
        V.put("supp_recs", au["records_with_supplementary_codes"], "results/audit/audit_summary.json", "records_with_supplementary_codes", INT)
        q = j("results/qrs_validation.json")["por_grupo"]
        V.put("qrs_sens_min", min(r["sensibilidade_vs_xqrs"] for r in q.values()), "results/qrs_validation.json", "min(por_grupo.*.sensibilidade_vs_xqrs)")
        V.put("qrs_ppv_min", min(r["ppv_vs_xqrs"] for r in q.values()), "results/qrs_validation.json", "min(por_grupo.*.ppv_vs_xqrs)")

    # ---------------- experimento A
    with V.secao("experimento A"):
        A = j("results/expA/test.json")
        fA = "results/expA/test.json"
        V.put("a_n", A["n_teste"], fA, "n_teste", INT)
        V.put("a_pos", A["n_pos"], fA, "n_pos", INT)
        V.put("a_prev", A["prevalencia_teste"], fA, "prevalencia_teste", P0)
        for m, mm in A["metricas"].items():
            for k, kk in [("auroc", "auroc"), ("auprc", "auprc"), ("sens", "sensibilidade"), ("spec", "especificidade"), ("ppv", "ppv")]:
                V.put(f"a_{m}_{k}", mm[kk], fA, f"metricas.{m}.{kk}", "{:.4f}" if k == "auroc" else "{:.3f}")
                if k != "ppv":
                    V.put(f"a_{m}_{k}_ci", mm["ic95"][kk], fA, f"metricas.{m}.ic95.{kk}", CI3)
            V.put(f"a_{m}_ppv1", mm["ppv_prevalencia"]["0.01"], fA, f"metricas.{m}.ppv_prevalencia.0.01")
            if "ece" in mm:
                V.put(f"a_{m}_ece", mm["ece"], fA, f"metricas.{m}.ece", "{:.4f}")
        sel = j("results/expA/selection.json")
        for m, v in sel["auprc_validacao"].items():
            V.put(f"val_{m}", v, "results/expA/selection.json", f"auprc_validacao.{m}", "{:.4f}")
        V.put("chosen", sel["escolhido"], "results/expA/selection.json", "escolhido", "{}")
        sg = pd.read_csv(RES / "expA" / "test_subgroups.csv")
        r = sg[(sg["subgrupo"] == "faixa") & (sg["valor"] == "30-54") & (sg["modelo"] == "logreg")].iloc[0]
        fs_ = "results/expA/test_subgroups.csv"
        V.put("age_band", r["valor"].replace("-", "–"), fs_, "faixa (valor)", "{}")
        V.put("sub3054_pos", int(r["n_pos"]), fs_, "faixa=30-54,logreg,n_pos", "{:d}")
        V.put("sub3054_sens", r["sensibilidade"], fs_, "faixa=30-54,logreg,sensibilidade")
        V.put("sub3054_spec", r["especificidade"], fs_, "faixa=30-54,logreg,especificidade")
        V.put("sub3054_spec_ci", ci(r["esp_ic95"]), fs_, "faixa=30-54,logreg,esp_ic95", CI3)
        r = sg[(sg["subgrupo"] == "faixa") & (sg["valor"] == "70+") & (sg["modelo"] == "logreg")].iloc[0]
        V.put("sub70_spec", r["especificidade"], fs_, "faixa=70+,logreg,especificidade")
        V.put("age_old", r["valor"], fs_, "faixa (valor)", "{}")

    # ---------------- experimento B
    with V.secao("experimento B"):
        B = pd.read_csv(RES / "expB" / "external_validation.csv").set_index("cenario")
        fB = "results/expB/external_validation.csv"
        rows = {"ext": "B: Shaoxing→PTB-XL (todo)", "inv_ptb": "Inverso: PTB-XL→PTB-XL (fold 10)",
                "inv_sh": "Inverso: PTB-XL→Shaoxing (teste A)", "ext_hv": "B: Shaoxing→PTB-XL (só validated_by_human)"}
        for k, name in rows.items():
            for m, mm in [("auroc", "auroc"), ("sens", "sensibilidade"), ("spec", "especificidade"), ("ppv", "ppv"), ("auprc", "auprc")]:
                V.put(f"{k}_{m}", B.loc[name, mm], fB, f"{name}/{mm}", "{:.4f}" if m == "auroc" else "{:.3f}")
            V.put(f"{k}_pos", int(B.loc[name, "n_pos"]), fB, f"{name}/n_pos", INT)
            V.put(f"{k}_neg", int(B.loc[name, "n_neg"]), fB, f"{name}/n_neg", INT)
        for m in ["auroc", "sensibilidade", "especificidade"]:
            V.put(f"ext_{m[:4]}_ci", ci(B.loc[rows["ext"], f"{m}_ic95"]), fB, f"{rows['ext']}/{m}_ic95", CI3)
        V.put("ext_prev", B.loc[rows["ext"], "prevalencia"], fB, f"{rows['ext']}/prevalencia", P0)
        V.put("ext_fp_x", (1 - B.loc[rows["ext"], "especificidade"]) / (1 - A["metricas"]["logreg"]["especificidade"]),
              f"{fB} + {fA}", "(1-esp_B)/(1-esp_A), logreg", "{:.1f}")
        am = pd.read_csv(RES / "expB" / "all_models.csv")
        fBm = "results/expB/all_models.csv"
        for m in ["baseline_rr", "logreg", "random_forest", "lightgbm", "cnn"]:
            rr = am[(am["modelo"] == m) & (am["cenario"] == "PTB-XL todo")].iloc[0]
            V.put(f"b_{m}_auroc", rr["auroc"], fBm, f"{m}/PTB-XL todo/auroc", "{:.4f}")
            V.put(f"b_{m}_spec", rr["especificidade"], fBm, f"{m}/PTB-XL todo/especificidade")
            V.put(f"b_{m}_sens", rr["sensibilidade"], fBm, f"{m}/PTB-XL todo/sensibilidade")

    # ---------------- experimento D
    with V.secao("experimento D"):
        D = j("results/expD/summary.json")
        fD = "results/expD/summary.json"
        for k, name in [("a", "A: teste Shaoxing"), ("b", "B: PTB-XL todo")]:
            bs = D[name]["bootstrap_pareado_logreg_menos_baseline"]
            for m in ["auroc", "auprc", "sensibilidade", "especificidade"]:
                V.put(f"d_{k}_{m[:4]}", bs[m]["diferenca_media"], fD, f"{name}.bootstrap.{m}.diferenca_media", "{:+.3f}")
                V.put(f"d_{k}_{m[:4]}_ci", bs[m]["ic95"], fD, f"{name}.bootstrap.{m}.ic95", lambda c: f"{c[0]:+.3f} to {c[1]:+.3f}")
            mc = D[name]["mcnemar"]
            V.put(f"d_{k}_p", mc["p_valor"], fD, f"{name}.mcnemar.p_valor", "{:.3f}")
            V.put(f"d_{k}_only_ml", mc["so_a_acerta"], fD, f"{name}.mcnemar.so_a_acerta", "{:d}")
            V.put(f"d_{k}_only_bl", mc["so_b_acerta"], fD, f"{name}.mcnemar.so_b_acerta", "{:d}")
            V.put(f"d_{k}_err_ml", D[name]["erros"]["logreg"], fD, f"{name}.erros.logreg", INT)
            V.put(f"d_{k}_err_bl", D[name]["erros"]["baseline_rr"], fD, f"{name}.erros.baseline_rr", INT)

    # ---------------- experimento C
    with V.secao("experimento C"):
        C1 = pd.read_csv(RES / "expC" / "source_classifier.csv")
        fC = "results/expC/source_classifier.csv"
        def c1(par, sub):  # noqa: E306
            r = C1[(C1["par"] == par) & C1["atributos"].str.contains(sub, regex=False)].iloc[0]
            return r["auroc_cv5"], f"{par} | {r['atributos']}"
        for k, par, sub in [("c_tcc", "Shaoxing vs PTB-XL", "escala do TCC"), ("c_amp", "Shaoxing vs PTB-XL", "unidades corretas"),
                            ("c_rhy", "Shaoxing vs PTB-XL", "atributos de ritmo"), ("c_desc", "Shaoxing vs PTB-XL", "descritores"),
                            ("c_nb_rhy", "Shaoxing vs Ningbo", "atributos de ritmo"), ("c_nb_desc", "Shaoxing vs Ningbo", "descritores")]:
            v, campo = c1(par, sub)
            V.put(k, v, fC, campo, "{:.2f}")
        C2 = pd.read_csv(RES / "expC" / "tcc_design.csv")
        fC2 = "results/expC/tcc_design.csv"
        for k, mod, tst, col in [("c2_lr_mix", "logreg", "misto", "auroc"), ("c2_lr_sh", "logreg", "mesma fonte Shaoxing", "auroc"),
                                 ("c2_lr_ptb", "logreg", "mesma fonte PTB-XL", "auroc"),
                                 ("c2_ds_mix_spec", "LightGBM", "misto", "especificidade@0.5"),
                                 ("c2_ds_sh_spec", "LightGBM", "mesma fonte Shaoxing", "especificidade@0.5")]:
            r = C2[C2["modelo"].str.startswith(mod) & C2["teste"].str.startswith(tst)].iloc[0]
            V.put(k, r[col], fC2, f"{r['modelo']} | {r['teste']} | {col}", "{:.4f}" if col == "auroc" else "{:.3f}")

    # ---------------- experimento E
    with V.secao("experimento E"):
        E = pd.read_csv(RES / "expE" / "false_afib_by_rate.csv")
        fE = "results/expE/false_afib_by_rate.csv"
        for k, conj, grp in [("e_ptb_brady", "PTB-XL", "SINUS_BRADY"), ("e_ptb_tachy", "PTB-XL", "SINUS_TACHY"),
                             ("e_ptb_norm", "PTB-XL", "SINUS_NORMAL"), ("e_sh_brady", "Shaoxing", "SINUS_BRADY"),
                             ("e_sh_tachy", "Shaoxing", "SINUS_TACHY"), ("e_nb_tachy", "Ningbo", "SINUS_TACHY")]:
            r = E[E["conjunto"].str.startswith(conj) & (E["grupo"] == grp)].iloc[0]
            V.put(k, r["falso_afib_logreg_limiar"], fE, f"{r['conjunto']}/{grp}/falso_afib_logreg_limiar", P1)
        Hr = pd.read_csv(RES / "expE" / "hr_rule_vs_labels.csv").fillna(0)
        fH = "results/expE/hr_rule_vs_labels.csv"
        br = Hr[Hr["rotulo"] == "SINUS_BRADY"]
        tc = Hr[Hr["rotulo"] == "SINUS_TACHY"]
        V.put("hr_brady_min", (br["AVISO_FC_BAIXA"] / br["n"]).min(), fH, "min(AVISO_FC_BAIXA/n) para SINUS_BRADY", P1)
        V.put("hr_tachy_min", (tc["AVISO_FC_ALTA"] / tc["n"]).min(), fH, "min(AVISO_FC_ALTA/n) para SINUS_TACHY", P1)
        pn = Hr[(Hr["rotulo"] == "SINUS_NORMAL") & Hr["conjunto"].str.startswith("PTB")].iloc[0]
        V.put("hr_ptb_norm_low", pn["AVISO_FC_BAIXA"] / pn["n"], fH, "PTB-XL SINUS_NORMAL AVISO_FC_BAIXA/n", P0)

    # ---------------- experimento F
    with V.secao("experimento F"):
        F = pd.read_csv(RES / "expF" / "robustness_sqi_calibrated.csv")
        fF = "results/expF/robustness_sqi_calibrated.csv"
        for k, ru, snr in [("ma0", "ruído muscular", 0), ("mam6", "ruído muscular", -6), ("em0", "movimento de eletrodo", 0),
                           ("emm6", "movimento de eletrodo", -6), ("bwm6", "oscilação de linha de base", -6), ("ma6", "ruído muscular", 6)]:
            r = F[(F["ruido"] == ru) & (F["snr_db"] == snr)].iloc[0]
            for c, cc in [("nosqi", "esp_sem_sqi"), ("init", "esp_sqi_inicial"), ("cal", "esp_sqi_calibrado")]:
                V.put(f"f_{k}_{c}", r[cc], fF, f"{ru}/{snr} dB/{cc}")
        V.put("f_sens_min", F["sens_sem_sqi"].min(), fF, "min(sens_sem_sqi)")
        Fr = pd.read_csv(RES / "expF" / "robustness.csv")
        r = Fr[Fr["ruido"] == "conversão A/D 12 bits"].iloc[0]
        V.put("f_adc_spec", r["esp_sem_sqi"], "results/expF/robustness.csv", "conversão A/D 12 bits/esp_sem_sqi")
        V.put("f_clean_spec", Fr[Fr["ruido"] == "limpo"].iloc[0]["esp_sem_sqi"], "results/expF/robustness.csv", "limpo/esp_sem_sqi")
        Cr = pd.read_csv(RES / "expF" / "sqi_clean_rejection.csv")
        fCr = "results/expF/sqi_clean_rejection.csv"
        for lab in ["inicial", "calibrado"]:
            x = Cr[Cr["sqi"] == lab]["rejeicao"]
            V.put(f"rej_{lab}_lo", x.min(), fCr, f"min(rejeicao | sqi={lab})", P1)
            V.put(f"rej_{lab}_hi", x.max(), fCr, f"max(rejeicao | sqi={lab})", P1)
        sc = j("results/expF/sqi_calibrated.json")["limiares"]
        V.put("sqi_agree", sc["min_qrs_agreement"], "results/expF/sqi_calibrated.json", "limiares.min_qrs_agreement", "{:.2f}")

    # ---------------- experimento G
    with V.secao("experimento G"):
        G = pd.read_csv(RES / "expG" / "out_of_training.csv")
        fG = "results/expG/out_of_training.csv"
        for k, base, cat in [("g_fl_sh", "Shaoxing", "AF"), ("g_fl_ptb", "PTB-XL", "AFLT"), ("g_at", "Shaoxing", "AT"),
                             ("g_ect_ptb", "PTB-XL", "ECTOPIA"), ("g_ect_sh", "Shaoxing", "ECTOPIA"),
                             ("g_sa_ptb", "PTB-XL", "arritmia sinusal"), ("g_sa_nb", "Ningbo", "arritmia sinusal"),
                             ("g_svt", "Shaoxing", "SVT"), ("g_bav_ptb", "PTB-XL", "BAV")]:
            r = G[(G["base"] == base) & (G["categoria"] == cat)].iloc[0]
            V.put(k, r["pct_AFIB"], fG, f"{base}/{cat}/pct_AFIB", P0)
            V.put(k + "_inc", r["pct_INCERTO"], fG, f"{base}/{cat}/pct_INCERTO", P0)
        r = G[(G["base"] == "Ningbo") & G["categoria"].str.startswith("AF")].iloc[0]
        V.put("g_nb_af", r["pct_AFIB"], fG, f"Ningbo/{r['categoria']}/pct_AFIB", P0)

    # ---------------- experimento H
    with V.secao("experimento H"):
        Hs = j("results/expH/summary.json")
        fHs = "results/expH/summary.json"
        V.put("vote_n", int(Hs["escolhido"]["N"]), fHs, "escolhido.N", "{:d}")
        V.put("vote_m", int(Hs["escolhido"]["M"]), fHs, "escolhido.M", "{:d}")
        Mo = pd.read_csv(RES / "expH" / "monitoring.csv")
        fMo = "results/expH/monitoring.csv"
        for k, conj in [("sh", "Shaoxing"), ("ptb", "PTB-XL"), ("nb", "Ningbo")]:
            for kk, cfgname in [("1", "1 de 1"), ("v", "escolhido")]:
                r = Mo[Mo["conjunto"].str.startswith(conj) & Mo["configuracao"].str.contains(cfgname, regex=False)].iloc[0]
                V.put(f"h_{k}_{kk}", r["falsos_alertas_dia"], fMo, f"{r['conjunto']}/{r['configuracao']}/falsos_alertas_dia",
                      "{:.0f}" if kk == "1" else "{:.2f}")
        r = Mo[Mo["conjunto"].str.startswith("PTB") & Mo["configuracao"].str.contains("escolhido")].iloc[0]
        V.put("h_ptb_sens1", r["sens_episodio_6j"], fMo, "PTB-XL/escolhido/sens_episodio_6j")
        V.put("h_ptb_sens5", r["sens_episodio_31j"], fMo, "PTB-XL/escolhido/sens_episodio_31j")
        V.put("h_tmed", r["tempo_alerta_mediana_s_31j"], fMo, "PTB-XL/escolhido/tempo_alerta_mediana_s_31j", "{:.0f}")
        Ms = pd.read_csv(RES / "expH" / "monitoring_sensitivity.csv")
        fMs = "results/expH/monitoring_sensitivity.csv"
        for k, conj in [("sh", "Shaoxing"), ("ptb", "PTB-XL")]:
            r = Ms[Ms["cenario"].str.startswith("negativos correlacionados") & Ms["conjunto"].str.startswith(conj)].iloc[0]
            V.put(f"h_corr_{k}", r["falsos_alertas_dia"], fMs, f"{r['cenario']}/{r['conjunto']}/falsos_alertas_dia", "{:.1f}")
        for k, lab in [("ect", "ectopia"), ("sa", "arritmia sinusal")]:
            x = Ms[Ms["cenario"].str.contains(lab, regex=False)]["falsos_alertas_dia"]
            V.put(f"h_{k}_lo", x.min(), fMs, f"min(falsos_alertas_dia | {lab})", "{:.0f}")
            V.put(f"h_{k}_hi", x.max(), fMs, f"max(falsos_alertas_dia | {lab})", "{:.0f}")

    # ---------------- experimento I
    with V.secao("experimento I"):
        I = j("results/expI/summary.json")
        fI = "results/expI/summary.json"
        ksh = next(k for k in I if k.startswith("Shaoxing"))
        kpt = next(k for k in I if k.startswith("PTB-XL"))
        V.put("i_sh_n", I[ksh]["n_por_classe"], fI, f"{ksh}.n_por_classe", "{:d}")
        V.put("i_sh_acc", I[ksh]["acuracia"], fI, f"{ksh}.acuracia", P1)
        V.put("i_ptb_n", I[kpt]["n_por_classe"], fI, f"{kpt}.n_por_classe", "{:d}")
        V.put("i_ptb_acc", I[kpt]["acuracia"], fI, f"{kpt}.acuracia", P1)
        V.put("i_ptb_rec_afib", I[kpt]["recall_por_classe"]["AFIB"], fI, f"{kpt}.recall_por_classe.AFIB", P1)
        V.put("i_ptb_rec_norm", I[kpt]["recall_por_classe"]["NORMAL"], fI, f"{kpt}.recall_por_classe.NORMAL", P1)
        T = j("results/reference/tcc_reported.json")
        fT = "results/reference/tcc_reported.json"
        V.put("tcc_acc", T["acuracia"], fT, "acuracia", P1)
        V.put("tcc_spec", T["especificidade_macro"], fT, "especificidade_macro", P1)
        V.put("tcc_n", T["n_por_classe"], fT, "n_por_classe", "{:d}")
        V.put("tcc_fa_day", (1 - T["especificidade_macro"]) * cfg["voting"]["windows_per_day"], f"{fT} + {cf}",
              "(1-especificidade_macro)*windows_per_day", "{:.0f}")

    # ---------------- benchmark
    with V.secao("benchmark"):
        bp = sorted((RES / "benchmark").glob("benchmark_*.json"))[0]
        Bm = json.loads(bp.read_text())
        fb = str(bp.relative_to(ROOT))
        V.put("bench_cpu", Bm["maquina"]["cpu"], fb, "maquina.cpu", "{}")
        V.put("bench_med", Bm["latencia"]["monitor_update"]["mediana_ms"], fb, "latencia.monitor_update.mediana_ms", "{:.1f}")
        V.put("bench_p95", Bm["latencia"]["monitor_update"]["p95_ms"], fb, "latencia.monitor_update.p95_ms", "{:.1f}")
        V.put("bench_model", Bm["latencia"]["modelo_json"]["mediana_ms"], fb, "latencia.modelo_json.mediana_ms", "{:.2f}")
        V.put("bench_rss", Bm["memoria"]["rss_apos_import_e_modelo_mb"], fb, "memoria.rss_apos_import_e_modelo_mb", "{:.0f}")
        V.put("bench_json_kb", Bm["artefatos_kb"]["afib_logreg_v1.json"], fb, "artefatos_kb.afib_logreg_v1.json", "{:.0f}")
        V.put("bench_onnx_kb", Bm["artefatos_kb"]["afib_logreg_v1.onnx"], fb, "artefatos_kb.afib_logreg_v1.onnx", "{:.1f}")

    # ---------------- calibração externa
    with V.secao("calibração externa"):
        ce = j("results/expB/calibration_external.json")
        fce = "results/expB/calibration_external.json"
        V.put("cal_ext_ece", ce["ece"], fce, "ece")
        mid = [r for r in ce["confiabilidade"] if 0.5 <= float(r["faixa_prob"].split("-")[0]) < 0.9 and r["n"]]
        V.put("cal_lo", float(mid[0]["faixa_prob"].split("-")[0]), fce, "confiabilidade: início da faixa intermediária", "{:.1f}")
        V.put("cal_hi", float(mid[-1]["faixa_prob"].split("-")[1]), fce, "confiabilidade: fim da faixa intermediária", "{:.1f}")
        V.put("cal_obs_lo", min(r["fracao_afib_observada"] for r in mid), fce, "min(fracao_afib_observada) nas faixas 0,5–0,9", P0)
        V.put("cal_obs_hi", max(r["fracao_afib_observada"] for r in mid), fce, "max(fracao_afib_observada) nas faixas 0,5–0,9", P0)

    # ---------------- literatura (conferida na fonte)
    with V.secao("literatura (conferida na fonte)"):
        L = j("results/reference/literature.json")
        fL = "results/reference/literature.json"
        V.put("lit_sw_sens", L["smartwatch_meta_analise"]["algoritmo_sensibilidade"], fL, "smartwatch_meta_analise.algoritmo_sensibilidade", P0)
        V.put("lit_sw_spec", L["smartwatch_meta_analise"]["algoritmo_especificidade"], fL, "smartwatch_meta_analise.algoritmo_especificidade", P0)
        V.put("lit_h_dnn", L["holter_dnn"]["afib_sensibilidade_dnn"], fL, "holter_dnn.afib_sensibilidade_dnn", P0)
        V.put("lit_h_conv", L["holter_dnn"]["afib_sensibilidade_convencional"], fL, "holter_dnn.afib_sensibilidade_convencional", P0)
        V.put("lit_khine_prev", L["khine_2018"]["prevalencia_afib_astronautas_ativos"], fL, "khine_2018.prevalencia_afib_astronautas_ativos", P0)
        V.put("lit_khine_months", L["khine_2018"]["meses_em_orbita"], fL, "khine_2018.meses_em_orbita", "{:d}")
    return V


def render(template: str, V: Values) -> str:
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", template)) - set(V.v))
    if missing and not V.allow_missing:
        raise KeyError(f"marcadores sem valor: {missing}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: V.v[m.group(1)]["valor"] if m.group(1) in V.v else "n/d", template)


def build(allow_missing: bool | None = None) -> tuple[dict[str, str], Values]:
    if allow_missing is None:  # make reproduce SUBSET=N exporta AFIB_SUBSET
        allow_missing = bool(os.environ.get("AFIB_SUBSET"))
    V = collect(allow_missing)
    out = {}
    for doc, tpl in DOCS.items():
        out[doc] = render((TPL / tpl).read_text(encoding="utf-8"), V)
    return out, V


def main():
    out, V = build()
    for doc, txt in out.items():
        (ROOT / doc).write_text(txt, encoding="utf-8")
    used = set()
    for tpl in DOCS.values():
        used |= set(re.findall(r"\{\{(\w+)\}\}", (TPL / tpl).read_text(encoding="utf-8")))
    (RES / "readme_numbers.json").write_text(json.dumps(
        {"nota": "Origem de cada número de README.md e MODEL_CARD.md (gerados por scripts/make_report.py).",
         "valores": {k: v for k, v in sorted(V.v.items()) if k in used}}, indent=1, ensure_ascii=False, default=str))
    unused = sorted(set(V.v) - used)
    print(f"README.md e MODEL_CARD.md gerados; {len(used)} valores usados" + (f"; não usados: {unused}" if unused else ""))
    if V.falhas:
        print("modo subconjunto: seções sem dados (marcadas n/d):", V.falhas)


if __name__ == "__main__":
    main()
