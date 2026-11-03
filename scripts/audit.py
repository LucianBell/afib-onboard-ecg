"""Auditoria das bases antes do treino.

Lê data/interim/{base}_index.parquet (gerado por `python -m src.data index`),
grava tabelas em results/audit/ e figura em results/figures/, e gera
docs/data_audit.md. Todo número do documento vem desses arquivos.

    python scripts/audit.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, load_config  # noqa: E402
from src.data import clean_age  # noqa: E402

GROUP_ORDER = ["AFIB", "SINUS_NORMAL", "SINUS_OUTRO", "SINUS_BRADY", "SINUS_TACHY", "SINUS_ARRITMIA",
               "FORA_DE_TREINO", "CONFLITO", "SEM_RITMO"]
AGE_BINS = [0, 18, 30, 40, 50, 60, 70, 80, 200]
AGE_LABELS = ["<18", "18-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]
ASTRO = (30, 55)  # faixa etária próxima à de astronautas em atividade (aprox.)


def md_table(df: pd.DataFrame, index=True, floatfmt="{:.2f}") -> str:
    d = df.reset_index() if index else df.copy()
    cols = [str(c) for c in d.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in d.iterrows():
        cells = []
        for v in r.values:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else (f"{int(v)}" if float(v).is_integer() else floatfmt.format(v)))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def explode(series: pd.Series) -> list[set[str]]:
    return [set(a.split(",")) if isinstance(a, str) and a else set() for a in series]


def main():
    cfg = load_config()
    interim, res = cfg["paths"]["interim"], cfg["paths"]["results"] / "audit"
    fig_dir = cfg["paths"]["results"] / "figures"
    res.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    dfs = {b: pd.read_parquet(interim / f"{b}_index.parquet") for b in cfg["datasets"]}
    n_exp = {b: cfg["datasets"][b]["n_samples"] for b in cfg["datasets"]}
    S: dict = {"bases": {}}
    for b, d in dfs.items():
        d["fonte"] = d["source"].map(lambda x: x if x == "ptbxl" else f"chapman_{x}")
    # idade: PTB-XL 300 -> 90 (≥ 90); Ningbo 0 -> ausente (src.data.clean_age)
    if "ptbxl" in dfs:
        S["ptbxl_age_300"] = int((dfs["ptbxl"]["age"] == 300).sum())
    if "chapman" in dfs:
        S["ningbo_age_0"] = int(((dfs["chapman"]["source"] == "ningbo") & (dfs["chapman"]["age"] == 0)).sum())
        S["ningbo_age_1_3"] = int(((dfs["chapman"]["source"] == "ningbo") & dfs["chapman"]["age"].between(1, 3)).sum())
    for d in dfs.values():
        d["age"] = clean_age(d)
    allr = pd.concat(dfs.values(), ignore_index=True)

    # ---------------------------------------------------------- 1. contagens por grupo
    counts = pd.DataFrame({b: d["group"].value_counts() for b, d in dfs.items()}).reindex(GROUP_ORDER).fillna(0).astype(int)
    counts.loc["TOTAL"] = counts.sum()
    counts.to_csv(res / "group_counts.csv")
    counts_src = pd.crosstab(allr["group"], allr["fonte"]).reindex(GROUP_ORDER).fillna(0).astype(int)
    counts_src.loc["TOTAL"] = counts_src.sum()
    counts_src.to_csv(res / "group_counts_by_source.csv")
    sub = []
    for b, d in dfs.items():
        x = d[d["group"].isin(["FORA_DE_TREINO", "CONFLITO"])].groupby(["group", "subtype"]).size().rename("n").reset_index()
        x.insert(0, "base", b)
        sub.append(x)
    subtypes = pd.concat(sub).sort_values(["base", "group", "n"], ascending=[True, True, False])
    subtypes.to_csv(res / "subtype_counts.csv", index=False)

    # ---------------------------------------------------------- 1b. fronteira de fonte na Chapman
    if "chapman" in dfs:
        ch = dfs["chapman"]
        sup_cfg = cfg["datasets"]["chapman"]["supplementary_dx_maps"]
        cinc = pd.concat([pd.read_csv(ROOT / sup_cfg["dir"] / f, dtype=str) for f in sup_cfg["files"]])
        code_sets = [set(x.split(",")) if x else set() for x in ch["dx_codes"]]
        src = ch["source"].values
        rows = []
        for _, r in cinc.iterrows():
            code = r["SNOMEDCTCode"].strip()
            ours_s = sum(1 for cs, so in zip(code_sets, src) if so == "shaoxing" and code in cs)
            ours_n = sum(1 for cs, so in zip(code_sets, src) if so == "ningbo" and code in cs)
            rows.append({"codigo": code, "abrev": r["Abbreviation"], "dx": r["Dx"],
                         "cinc_shaoxing": int(r["Chapman_Shaoxing"]), "nosso_shaoxing": ours_s,
                         "cinc_ningbo": int(r["Ningbo"]), "nosso_ningbo": ours_n})
        bnd = pd.DataFrame(rows)
        bnd = bnd[(bnd[["cinc_shaoxing", "nosso_shaoxing", "cinc_ningbo", "nosso_ningbo"]].sum(axis=1) > 0)]
        bnd["dif_shaoxing"] = bnd["nosso_shaoxing"] - bnd["cinc_shaoxing"]
        bnd["dif_ningbo"] = bnd["nosso_ningbo"] - bnd["cinc_ningbo"]
        bnd.to_csv(res / "chapman_source_boundary_check.csv", index=False)
        S["boundary"] = {
            "ultimo_registro_shaoxing": cfg["datasets"]["chapman"]["shaoxing_last_record"],
            "n_registros_shaoxing": int((ch["source"] == "shaoxing").sum()),
            "n_registros_ningbo": int((ch["source"] == "ningbo").sum()),
            "codigos_comparados": int(len(bnd)),
            "codigos_com_contagem_identica_nas_duas_fontes": int(((bnd["dif_shaoxing"] == 0) & (bnd["dif_ningbo"] == 0)).sum()),
            "soma_abs_dif_shaoxing": int(bnd["dif_shaoxing"].abs().sum()),
            "soma_abs_dif_ningbo": int(bnd["dif_ningbo"].abs().sum()),
        }
        S["boundary_table"] = bnd.sort_values("cinc_shaoxing", ascending=False)
        # códigos dos cabeçalhos que só o dicionário complementar resolve
        dic = pd.read_csv(next((cfg["paths"]["raw"] / "chapman").rglob("ConditionNames_SNOMED-CT.csv")), encoding="utf-8-sig", dtype=str)
        off = {r["Acronym Name"].strip(): r["Snomed_CT"].strip() for _, r in dic.iterrows()}
        supc = Counter(c for x in ch["supplementary_codes"].fillna("") for c in x.split(",") if c)
        cmap = {r["SNOMEDCTCode"].strip(): (r["Abbreviation"].strip(), r["Dx"]) for _, r in cinc.iterrows()}
        sup_rows = [{"codigo_no_cabecalho": c, "abrev_cinc": cmap[c][0], "descricao": cmap[c][1], "n_registros": n,
                     "acronimo_oficial_mesmo_nome": cmap[c][0] if cmap[c][0] in off else "",
                     "codigo_no_dicionario_oficial": off.get(cmap[c][0], "")} for c, n in supc.most_common()]
        sup_df = pd.DataFrame(sup_rows)
        sup_df.to_csv(res / "chapman_supplementary_codes.csv", index=False)
        S["supplementary"] = sup_df
        S["records_with_supplementary_codes"] = int((ch["supplementary_codes"].fillna("") != "").sum())

    # ---------------------------------------------------------- 1c. cobertura de ritmos ventriculares
    vent = {"chapman": ["PVT", "VF", "VFL", "AIVR", "VEsR"], "ptbxl": []}
    vrows = []
    for b, d in dfs.items():
        sets = explode(d["acronyms"])
        for a in vent.get(b, []):
            for f in sorted(d["fonte"].unique()):
                vrows.append({"fonte": f, "rotulo": a, "n": int(sum(1 for s_, ff in zip(sets, d["fonte"]) if a in s_ and ff == f))})
    S["ventricular"] = pd.DataFrame(vrows)
    S["ventricular"].to_csv(res / "ventricular_rhythm_counts.csv", index=False)
    if "ptbxl" in dfs:
        stm = pd.read_csv(next((cfg["paths"]["raw"] / "ptbxl").rglob("scp_statements.csv")), index_col=0)
        S["ptbxl_rhythm_statements"] = sorted(stm.index[stm["rhythm"] == 1].str.strip())

    # ---------------------------------------------------------- 2. frequência de rótulos e coocorrência
    freq_tables, cooc_tables = {}, {}
    for b, d in dfs.items():
        sets = explode(d["acronyms"])
        c = Counter(a for s in sets for a in s)
        freq = pd.Series(c).sort_values(ascending=False).rename("n")
        freq.to_csv(res / f"{b}_label_freq.csv", header=True)
        freq_tables[b] = freq
        prim = list(cfg["labels"][b]["primary"])
        mods = cfg["labels"][b]["ectopy"] + cfg["labels"][b]["av_block"] + cfg["labels"][b]["preexcitation"]
        keys = [k for k in prim + mods if c.get(k, 0) > 0]
        m = pd.DataFrame(0, index=keys, columns=keys)
        for s in sets:
            ks = [k for k in keys if k in s]
            for k in ks:
                m.loc[k, k] += 1
            for a, bb in combinations(ks, 2):
                m.loc[a, bb] += 1
                m.loc[bb, a] += 1
        m.to_csv(res / f"{b}_rhythm_cooccurrence.csv")
        cooc_tables[b] = m
        # rótulos que acompanham AFIB
        afib_sets = [s for s in sets if "AFIB" in s]
        S["bases"].setdefault(b, {})["afib_with_other_top"] = Counter(
            a for s in afib_sets for a in s if a != "AFIB").most_common(10)

    # ---------------------------------------------------------- 3. qualidade
    qual_rows = {}
    for b, d in dfs.items():
        ok = d["read_ok"].fillna(False).astype(bool)
        q = {
            "registros no índice": len(d),
            "cabeçalho ilegível": int((~d["header_ok"]).sum()),
            "sinal ilegível": int((~ok).sum()),
            "sem derivação I": int((ok & ~d["has_lead_I"].fillna(False).astype(bool)).sum()),
            f"n_amostras != {n_exp[b]}": int((ok & (d["n_samples"] != n_exp[b])).sum()),
            "NaN em alguma derivação": int((d["nan_any"].fillna(0) > 0).sum()),
            "NaN na derivação I": int((d["nan_leadI"].fillna(0) > 0).sum()),
            "derivação I plana": int(d["leadI_flat"].fillna(False).astype(bool).sum()),
            "≥1 derivação plana": int((d["n_flat_leads"].fillna(0) > 0).sum()),
            "derivação I com >50% de zeros": int((d["leadI_zero_frac"].fillna(0) > 0.5).sum()),
            "código de rótulo desconhecido": int((d["unknown_codes"].fillna("") != "").sum()),
            "sem idade": int(d["age"].isna().sum()),
            "sem sexo": int(d["sex"].isna().sum()),
        }
        qual_rows[b] = q
        unk = Counter(c for s in d["unknown_codes"].fillna("") for c in s.split(",") if c)
        S["bases"][b]["unknown_codes"] = unk.most_common(20)
        S["bases"][b]["read_errors"] = d.loc[~ok, "read_error"].fillna("").value_counts().head(5).to_dict() if "read_error" in d else {}
        S["bases"][b]["n_samples_values"] = d["n_samples"].value_counts().head(10).to_dict()
        S["bases"][b]["fs_values"] = d["fs"].value_counts().to_dict()
        S["bases"][b]["units"] = d["units"].value_counts().to_dict()
        S["bases"][b]["adc_gain"] = d["adc_gain"].value_counts().to_dict()
        S["bases"][b]["adc_res"] = d["adc_res"].value_counts().to_dict()
        S["bases"][b]["hea_keys"] = d["hea_keys"].value_counts().head(5).to_dict() if "hea_keys" in d else {}
        # registros problemáticos por grupo (qualquer um dos defeitos de sinal)
        bad = (~ok) | (d["nan_leadI"].fillna(0) > 0) | d["leadI_flat"].fillna(False).astype(bool) | (d["n_samples"] != n_exp[b])
        d["sinal_invalido"] = bad
        S["bases"][b]["invalid_by_group"] = d[bad]["group"].value_counts().to_dict()
        pd.Series(d.loc[bad, "record_id"]).to_csv(res / f"{b}_invalid_records.csv", index=False)
    quality = pd.DataFrame(qual_rows)
    quality.to_csv(res / "quality.csv")

    if "ptbxl" in dfs:
        d = dfs["ptbxl"]
        flags = ["baseline_drift", "static_noise", "burst_noise", "electrodes_problems", "extra_beats", "pacemaker"]
        pq = pd.DataFrame({f: d.groupby("group")[f].apply(lambda s: int(s.notna().sum())) for f in flags}).reindex(GROUP_ORDER).dropna(how="all")
        pq["n"] = d["group"].value_counts()
        pq.to_csv(res / "ptbxl_quality_flags.csv")
        S["bases"]["ptbxl"]["validated_by_human"] = d["validated_by_human"].value_counts().to_dict()

    # ---------------------------------------------------------- 4. unidades / amplitude
    qs = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    amp_rows = []
    allr = pd.concat(dfs.values(), ignore_index=True)
    for b, d in allr.groupby("fonte"):
        for col in ["qrs_p2p_leadI_mv", "qrs_p2p_maxlead_mv"]:
            v = d.loc[~d["sinal_invalido"], col].dropna()
            amp_rows.append({"base": b, "medida": col, "n": len(v), **{f"p{int(q*100)}": v.quantile(q) for q in qs}})
        for grp in ["AFIB", "SINUS_NORMAL", "SINUS_BRADY", "SINUS_TACHY"]:
            v = d.loc[(~d["sinal_invalido"]) & (d["group"] == grp), "qrs_p2p_leadI_mv"].dropna()
            if len(v):
                amp_rows.append({"base": b, "medida": f"qrs_p2p_leadI_mv [{grp}]", "n": len(v),
                                 **{f"p{int(q*100)}": v.quantile(q) for q in qs}})
    amp = pd.DataFrame(amp_rows)
    amp.to_csv(res / "amplitude_mv.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, col, title in [(axes[0], "qrs_p2p_leadI_mv", "Derivação I"), (axes[1], "qrs_p2p_maxlead_mv", "Derivação de maior amplitude")]:
        for b, d in allr.groupby("fonte"):
            v = d.loc[~d["sinal_invalido"], col].dropna().clip(0, 6)
            ax.hist(v, bins=120, range=(0, 6), histtype="step", density=True, label=b, lw=1.4)
        ax.set_xlabel("pico-a-pico mediano por segundo (mV; valores ≥ 6 acumulados em 6)")
        ax.set_title(title)
        ax.legend()
    fig.suptitle("Amplitude do QRS por fonte (unidades lidas do cabeçalho via wfdb)")
    fig.tight_layout()
    fig.savefig(fig_dir / "audit_qrs_amplitude.png", dpi=130)
    plt.close(fig)

    # ---------------------------------------------------------- 5. idade e sexo
    demo_rows = []
    for b, d in allr.groupby("fonte"):
        for grp, x in d.groupby("group"):
            demo_rows.append({"base": b, "grupo": grp, "n": len(x), "idade_mediana": x["age"].median(),
                              "idade_p25": x["age"].quantile(.25), "idade_p75": x["age"].quantile(.75),
                              "pct_F": 100 * (x["sex"] == "F").mean(),
                              f"pct_{ASTRO[0]}_{ASTRO[1]}anos": 100 * x["age"].between(*ASTRO).mean()})
    demo = pd.DataFrame(demo_rows)
    demo["ordem"] = demo["grupo"].map({g: i for i, g in enumerate(GROUP_ORDER)})
    demo = demo.sort_values(["base", "ordem"]).drop(columns="ordem")
    demo.to_csv(res / "demographics.csv", index=False)
    agebin_rows = []
    for b, d in allr.groupby("fonte"):
        x = d[d["group"].isin(["AFIB", "SINUS_NORMAL", "SINUS_OUTRO", "SINUS_BRADY", "SINUS_TACHY"])]
        t = pd.crosstab(pd.cut(x["age"], AGE_BINS, labels=AGE_LABELS, right=False), x["group"])
        t.insert(0, "base", b)
        agebin_rows.append(t)
    agebins = pd.concat(agebin_rows)
    agebins.to_csv(res / "age_bins.csv")
    for b, d in dfs.items():
        S["bases"][b]["age_max"] = float(d["age"].max())
        S["bases"][b]["age_ge_90"] = int((d["age"] >= 90).sum())

    # ---------------------------------------------------------- 6. paciente
    pat = {}
    for b, d in dfs.items():
        if d["patient_id"].notna().any():
            pc = d.groupby("patient_id").size()
            multi_grp = d[d["group"].isin(["AFIB", "SINUS_NORMAL", "SINUS_OUTRO", "SINUS_BRADY", "SINUS_TACHY"])].groupby("patient_id")["group"].nunique()
            fold_per_pat = d.groupby("patient_id")["strat_fold"].nunique() if "strat_fold" in d else None
            pat[b] = {"tem_id_paciente": True, "n_pacientes": int(pc.size), "registros_por_paciente_max": int(pc.max()),
                      "pacientes_com_>1_registro": int((pc > 1).sum()),
                      "registros_de_pacientes_com_>1": int(pc[pc > 1].sum()),
                      "pacientes_com_>1_grupo_de_ritmo": int((multi_grp > 1).sum()),
                      "pacientes_em_>1_strat_fold": int((fold_per_pat > 1).sum()) if fold_per_pat is not None else None}
        else:
            pat[b] = {"tem_id_paciente": False, "campos_do_cabecalho": list(S["bases"][b].get("hea_keys", {}).keys())}
    S["patients"] = pat

    # ---------------------------------------------------------- 7. duplicatas
    dup = {}
    for b, d in dfs.items():
        ok = d[d["read_ok"].fillna(False).astype(bool)]
        for h in ["hash_all", "hash_leadI"]:
            vc = ok[h].value_counts()
            dupset = vc[vc > 1]
            rows = ok[ok[h].isin(dupset.index)]
            dup[f"{b}:{h}"] = {"grupos_duplicados": int(len(dupset)), "registros_envolvidos": int(len(rows)),
                               "grupos_com_rotulos_diferentes": int(rows.groupby(h)["group"].nunique().gt(1).sum()) if len(rows) else 0}
            if h == "hash_all" and len(rows):
                rows.sort_values(h)[["record_id", "source", h, "group", "acronyms", "age", "sex"]].to_csv(res / f"{b}_duplicates.csv", index=False)
                gb = rows.groupby(h)
                dup[f"{b}:{h}"]["pares_entre_fontes"] = int(gb["source"].nunique().gt(1).sum())
                dup[f"{b}:{h}"]["grupos_mesma_idade_e_sexo"] = int((gb["age"].nunique().eq(1) & gb["sex"].nunique().eq(1)).sum())
                dup[f"{b}:{h}"]["grupos_com_AFIB"] = int(gb["group"].apply(lambda x: (x == "AFIB").any()).sum())
                pairs = Counter(" vs ".join(sorted(x)) for _, x in gb["group"] if x.nunique() > 1)
                dup[f"{b}:{h}"]["combinacoes_de_rotulo_divergentes"] = dict(pairs.most_common(8))
    if "chapman" in dfs:
        ch_ = dfs["chapman"]
        prim = set(cfg["labels"]["chapman"]["primary"])
        okc = ch_[ch_["read_ok"].fillna(False).astype(bool)]
        corr = Counter()
        for _, x in okc[okc["hash_all"].duplicated(keep=False)].groupby("hash_all"):
            if x["source"].nunique() == 2:
                lab = {so: "+".join(sorted(set(a.split(",")) & prim)) or "-" for so, a in zip(x["source"], x["acronyms"])}
                corr[(lab["shaoxing"], lab["ningbo"])] += 1
        S["cross_source_rhythm"] = pd.DataFrame([{"ritmo_shaoxing": k[0], "ritmo_ningbo": k[1], "pares": v}
                                                 for k, v in corr.most_common()])
        S["cross_source_rhythm"].to_csv(res / "chapman_cross_source_duplicate_labels.csv", index=False)
    if len(dfs) == 2:
        a, bq = (dfs[k] for k in dfs)
        cross = set(a["hash_leadI"].dropna()) & set(bq["hash_leadI"].dropna())
        dup["entre_bases:hash_leadI"] = {"grupos_duplicados": len(cross)}
    S["duplicates"] = dup

    # ---------------------------------------------------------- 8. viabilidade
    via = {}
    ch, pt = dfs.get("chapman"), dfs.get("ptbxl")
    if ch is not None:
        v = ch[~ch["sinal_invalido"]]
        for f in ["shaoxing", "ningbo"]:
            vv = v[v["source"] == f]
            via[f"chapman_{f}_afib"] = int((vv["group"] == "AFIB").sum())
            for g_ in ["SINUS_NORMAL", "SINUS_OUTRO", "SINUS_BRADY", "SINUS_TACHY", "SINUS_ARRITMIA"]:
                via[f"chapman_{f}_{g_.lower()}"] = int((vv["group"] == g_).sum())
        via["chapman_afib_validos"] = int((v["group"] == "AFIB").sum())
        via["chapman_sinusal_validos"] = int(v["group"].isin(["SINUS_NORMAL", "SINUS_OUTRO", "SINUS_BRADY", "SINUS_TACHY"]).sum())
        via["chapman_afib_teste_15pct_aprox"] = int(round(0.15 * via["chapman_afib_validos"]))
        S["flat_leads_by_source"] = ch[ch["n_flat_leads"].fillna(0) > 0]["source"].value_counts().to_dict()
    if pt is not None:
        v = pt[~pt["sinal_invalido"]]
        fold = v["strat_fold"]
        for name, mask in [("folds_1_8", fold <= 8), ("fold_9", fold == 9), ("fold_10", fold == 10), ("total", fold > 0)]:
            via[f"ptbxl_afib_{name}"] = int(((v["group"] == "AFIB") & mask).sum())
            via[f"ptbxl_sinus_normal_{name}"] = int(((v["group"] == "SINUS_NORMAL") & mask).sum())
        via["ptbxl_sinus_brady_total"] = int((v["group"] == "SINUS_BRADY").sum())
        via["ptbxl_sinus_tachy_total"] = int((v["group"] == "SINUS_TACHY").sum())
        via["ptbxl_flutter_total"] = int(v["acronyms"].str.contains(r"(?:^|,)AFLT(?:,|$)").sum())
    if ch is not None:
        via["chapman_flutter_total"] = int(ch["acronyms"].str.contains(r"(?:^|,)AF(?:,|$)").sum())
    S["viability"] = via

    S_json = {k: (v.to_dict(orient="records") if isinstance(v, pd.DataFrame) else v) for k, v in S.items()}
    (res / "audit_summary.json").write_text(json.dumps(S_json, indent=2, default=str, ensure_ascii=False))
    write_markdown(cfg, counts, counts_src, subtypes, freq_tables, cooc_tables, quality, amp, demo, agebins, S,
                   pq if "ptbxl" in dfs else None)
    print("auditoria gerada:", ROOT / "docs" / "data_audit.md")


def write_markdown(cfg, counts, counts_src, subtypes, freq, cooc, quality, amp, demo, agebins, S, pq):
    manifest_p = cfg["paths"]["results"] / "audit" / "data_manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    L = []
    w = L.append
    w("# Auditoria dos dados\n")
    w("> Documento gerado por `make audit` (`scripts/audit.py`). Não editar à mão: todos os números vêm de "
      "`results/audit/`. A interpretação está em `docs/decisions.md` e no texto marcado como *Leitura*.\n")
    w("## 1. Bases e versões\n")
    for b, d in cfg["datasets"].items():
        m = manifest.get(b, {})
        w(f"- **{b}** — {d['name']} v{d['version']} — zip {m.get('bytes', '?')} bytes, sha256 `{m.get('sha256', '?')}`")
    w("")
    w("## 2. Contagem de exames por grupo de rótulo\n")
    w("Regras de agrupamento em `src/labels.py::assign_group` e `configs/default.yaml` (seção `labels`).\n")
    w(md_table(counts.rename_axis("grupo")))
    w("\nPor fonte (a Chapman junta dois hospitais, ver 2.1):\n")
    w(md_table(counts_src.rename_axis("grupo")))
    if "boundary" in S:
        b_ = S["boundary"]
        w("\n### 2.1 Duas fontes dentro da Chapman: Shaoxing e Ningbo\n")
        w("O cabeçalho não informa o hospital de origem. A fronteira foi inferida em "
          f"JS{b_['ultimo_registro_shaoxing']:05d}: registros até ela = Chapman-Shaoxing "
          f"({b_['n_registros_shaoxing']}), depois = Ningbo ({b_['n_registros_ningbo']}). "
          "Conferência: contagem de cada código SNOMED por fonte comparada com as colunas "
          "`Chapman_Shaoxing` e `Ningbo` das tabelas do PhysioNet/CinC Challenge 2021 "
          f"(`results/audit/chapman_source_boundary_check.csv`). Códigos comparados: {b_['codigos_comparados']}; "
          f"com contagem idêntica nas duas fontes: {b_['codigos_com_contagem_identica_nas_duas_fontes']}; "
          f"soma das diferenças absolutas: Shaoxing {b_['soma_abs_dif_shaoxing']}, Ningbo {b_['soma_abs_dif_ningbo']}.\n")
        bt = S["boundary_table"]
        w("Códigos com diferença ou de ritmo relevante:\n")
        keep = bt[(bt["dif_shaoxing"] != 0) | (bt["dif_ningbo"] != 0) | bt["abrev"].isin(["AF", "AFL", "SR", "SB", "STach", "SA", "SVT", "AT"])]
        w(md_table(keep.head(30), index=False))
        w("")
    if "supplementary" in S and len(S["supplementary"]):
        w("### 2.2 Códigos fora do dicionário oficial da Chapman\n")
        w(f"{S['records_with_supplementary_codes']} registros têm códigos que não constam de "
          "`ConditionNames_SNOMED-CT.csv`. Todos foram resolvidos pelas tabelas do CinC 2021 "
          "(dicionário complementar, commit fixado em `configs/default.yaml`). Quando o acrônimo coincide com "
          "um do dicionário oficial, o código oficial é diferente do usado nos cabeçalhos:\n")
        w(md_table(S["supplementary"], index=False))
        w("")
    if "ventricular" in S:
        w("### 2.3 Cobertura de ritmos ventriculares\n")
        v = S["ventricular"]
        w(md_table(v[v["n"] > 0], index=False) if (v["n"] > 0).any() else "Nenhum registro.")
        w("\nEnunciados de ritmo do PTB-XL (`scp_statements.csv`, `rhythm == 1`): "
          + ", ".join(S.get("ptbxl_rhythm_statements", [])) + ". Nenhum é ventricular.\n")
    w("\nDetalhe de `FORA_DE_TREINO` e `CONFLITO` (top 15 por base):\n")
    w(md_table(subtypes.groupby("base").head(15), index=False))
    w("")
    for b in freq:
        w(f"### Rótulos mais frequentes — {b} (top 25)\n")
        w(md_table(freq[b].head(25).rename_axis("rótulo").to_frame()))
        w("\nRótulos que acompanham AFIB: " + ", ".join(f"{k} ({v})" for k, v in S["bases"][b]["afib_with_other_top"]) + "\n")
        w(f"Coocorrência entre ritmos e modificadores — {b} (diagonal = total do rótulo; CSV completo em "
          f"`results/audit/{b}_rhythm_cooccurrence.csv`):\n")
        c = cooc[b]
        keep = [k for k in c.index if c.loc[k, k] >= 20]
        w(md_table(c.loc[keep, keep]))
        w("")
    w("## 3. Integridade do sinal\n")
    w(md_table(quality.rename_axis("verificação")))
    w("")
    for b in S["bases"]:
        sb = S["bases"][b]
        w(f"- **{b}**: fs = {sb['fs_values']}; n_amostras = {sb['n_samples_values']}; unidades = {sb['units']}; "
          f"ganho A/D = {sb['adc_gain']}; resolução A/D (bits) = {sb['adc_res']}")
        if sb["unknown_codes"]:
            w(f"  - códigos ausentes do dicionário: {sb['unknown_codes']}")
        if sb.get("read_errors"):
            w(f"  - erros de leitura: {sb['read_errors']}")
        w(f"  - registros com sinal inválido por grupo: {sb['invalid_by_group']} (lista em `results/audit/{b}_invalid_records.csv`)")
    if pq is not None:
        w("\nPTB-XL — anotações de qualidade do próprio PTB-XL (registros com o campo preenchido):\n")
        w(md_table(pq.rename_axis("grupo")))
        w(f"\n`validated_by_human`: {S['bases']['ptbxl']['validated_by_human']}")
    w("")
    w("## 4. Unidades e amplitude do QRS\n")
    w("Pico-a-pico mediano por janela de 1 s após passa-alta de 0,5 Hz, em mV, com a conversão lida do cabeçalho "
      "(ganho e baseline via `wfdb`). Registros com sinal inválido excluídos.\n")
    w(md_table(amp, index=False))
    w("\n![amplitude](../results/figures/audit_qrs_amplitude.png)\n")
    w("## 5. Idade e sexo por grupo e base\n")
    if "ptbxl_age_300" in S:
        w(f"PTB-XL codifica idade acima de 89 anos como 300 (anonimização): {S['ptbxl_age_300']} registros, "
          "tratados como 90 (= \"≥ 90\") em todas as estatísticas abaixo.\n")
    if "ningbo_age_0" in S:
        w(f"Ningbo: {S['ningbo_age_0']} registros com idade 0 e {S['ningbo_age_1_3']} com 1 a 3 anos; o 0 é tratado como "
          "idade ausente (`src.data.clean_age`).\n")
    w(md_table(demo, index=False, floatfmt="{:.1f}"))
    w("\nFaixas etárias (grupos usados no modelo):\n")
    w(md_table(agebins.rename_axis("faixa")))
    w("\nIdade máxima: " + ", ".join(f"{b} = {S['bases'][b]['age_max']:g} ({S['bases'][b]['age_ge_90']} registros ≥ 90)" for b in S["bases"]) + "\n")
    w("## 6. Identificação de paciente\n")
    for b, p in S["patients"].items():
        w(f"- **{b}**: " + "; ".join(f"{k} = {v}" for k, v in p.items()))
    w("")
    w("## 7. Duplicatas de sinal (hash SHA-1 das amostras digitais)\n")
    for k, v in S["duplicates"].items():
        w(f"- **{k}**: " + "; ".join(f"{a} = {bb}" for a, bb in v.items()))
    w("")
    if "cross_source_rhythm" in S:
        w("\nRitmo primário das cópias idênticas Shaoxing ↔ Ningbo (mesmo sinal digital, rótulo de cada fonte):\n")
        w(md_table(S["cross_source_rhythm"], index=False))
    if "flat_leads_by_source" in S:
        w(f"\nRegistros com ≥ 1 derivação plana (qualquer derivação), por fonte da Chapman: {S['flat_leads_by_source']}\n")
    w("## 8. Volume para o desenho experimental\n")
    w("Contagens após excluir registros com sinal inválido.\n")
    for k, v in S["viability"].items():
        w(f"- `{k}` = {v}")
    w("")
    interp = ROOT / "docs" / "_audit_reading.md"
    if interp.exists():
        w(interp.read_text(encoding="utf-8"))
    (ROOT / "docs" / "data_audit.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
