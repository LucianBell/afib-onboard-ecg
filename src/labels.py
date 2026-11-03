"""Mapeamento de rótulos das duas bases para os grupos do projeto.

Os códigos SNOMED CT da Chapman são lidos de ConditionNames_SNOMED-CT.csv e os
enunciados SCP do PTB-XL de scp_statements.csv. Nada é codificado de memória:
o config só lista acrônimos, que são resolvidos contra esses arquivos.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

SINUS_FAMILY = {"SINUS", "SINUS_BRADY", "SINUS_TACHY", "SINUS_ARRITMIA"}


def load_chapman_dictionary(path: Path) -> tuple[dict[str, list[str]], pd.DataFrame]:
    """Retorna {código SNOMED: [acrônimos]} e a tabela original.

    Alguns códigos aparecem em mais de um acrônimo no arquivo (ex.: SAAWR/WAVN),
    por isso o valor é uma lista.
    """
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    code_to_acr: dict[str, list[str]] = defaultdict(list)
    for _, r in df.iterrows():
        code_to_acr[r["Snomed_CT"].strip()].append(r["Acronym Name"].strip())
    return dict(code_to_acr), df


def load_supplementary_dictionary(paths: list[Path], primary: dict[str, list[str]]) -> dict[str, list[str]]:
    """Códigos das tabelas do CinC 2021 que não estão no dicionário oficial da Chapman.

    Só entra código ausente do oficial. Se a abreviação coincidir com um acrônimo oficial,
    o nome por extenso precisa ser o mesmo conceito (checado pelo chamador na auditoria).
    """
    df = pd.concat([pd.read_csv(p, dtype=str) for p in paths])
    out: dict[str, list[str]] = {}
    for _, r in df.iterrows():
        code = r["SNOMEDCTCode"].strip()
        if code not in primary:
            out.setdefault(code, []).append(r["Abbreviation"].strip())
    return out


def load_ptbxl_statements(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    df.index = df.index.str.strip()
    return df


def check_config_acronyms(base_cfg: dict, known: set[str]) -> list[str]:
    """Acrônimos do config que não existem no dicionário da base (erro de configuração)."""
    listed = set(base_cfg["primary"]) | set(base_cfg["ectopy"]) | set(base_cfg["av_block"]) | set(
        base_cfg["preexcitation"]
    )
    return sorted(listed - known)


def chapman_source(record_id: str, last_shaoxing: int) -> str:
    """Fonte do registro da Chapman: o cabeçalho não informa; a fronteira foi inferida na auditoria."""
    return "shaoxing" if int(record_id[2:]) <= last_shaoxing else "ningbo"


def assign_group(acronyms: set[str], base_cfg: dict, norm_ok: bool | None = None) -> tuple[str, str]:
    """Atribui (grupo, subtipo) a um registro a partir do conjunto de acrônimos.

    Regras (registradas em docs/decisions.md):
    - sem ritmo primário -> SEM_RITMO (ou FORA_DE_TREINO se houver ectopia/bloqueio AV)
    - AFIB junto de outro ritmo primário, ou de bloqueio AV (PR não existe em AFIB) -> CONFLITO
    - AFIB com pré-excitação -> FORA_DE_TREINO; AFIB com ectopia -> AFIB
    - ritmo fora de treino junto de outro ritmo -> CONFLITO; sozinho -> FORA_DE_TREINO
    - família sinusal: bradi + taqui juntas -> CONFLITO; com ectopia/bloqueio AV/pré-excitação
      -> FORA_DE_TREINO; com arritmia sinusal -> SINUS_ARRITMIA; SR+SB -> SINUS_BRADY;
      SR+ST -> SINUS_TACHY; SR sem outro diagnóstico (Chapman) ou com NORM certo e sem outro
      enunciado (PTB-XL) -> SINUS_NORMAL; demais SR -> SINUS_OUTRO
    """
    primary = base_cfg["primary"]
    prim = sorted(a for a in acronyms if a in primary)
    groups = {primary[a] for a in prim}
    ect = acronyms & set(base_cfg["ectopy"])
    avb = acronyms & set(base_cfg["av_block"])
    pre = acronyms & set(base_cfg["preexcitation"])
    norm = base_cfg.get("norm_statement")
    other = acronyms - set(prim) - ect - avb - pre - ({norm} if norm else set())

    if not prim:
        if ect or avb or pre:  # ritmo de base não informado, mas há ectopia/bloqueio
            return "FORA_DE_TREINO", "SEM_RITMO_BASE+" + ("BAV" if avb else ("PRE_EXCITACAO" if pre else "ECTOPIA"))
        return "SEM_RITMO", ""
    if "AFIB" in groups:
        if len(groups) > 1:
            return "CONFLITO", "+".join(prim)
        if avb:
            return "CONFLITO", "AFIB+" + "+".join(sorted(avb))
        if pre:
            return "FORA_DE_TREINO", "AFIB_PREEXCITADA"
        return "AFIB", ""
    if "FORA_DE_TREINO" in groups:
        if len(prim) > 1 and groups != {"FORA_DE_TREINO"}:
            return "CONFLITO", "+".join(prim)
        return "FORA_DE_TREINO", "+".join(prim)
    # família sinusal
    if {"SINUS_BRADY", "SINUS_TACHY"} <= groups:
        return "CONFLITO", "+".join(prim)
    if avb or pre or ect:
        sub = "BAV" if avb else ("PRE_EXCITACAO" if pre else "ECTOPIA")
        return "FORA_DE_TREINO", sub
    if "SINUS_ARRITMIA" in groups:
        return "SINUS_ARRITMIA", ""
    if "SINUS_BRADY" in groups:
        return "SINUS_BRADY", ""
    if "SINUS_TACHY" in groups:
        return "SINUS_TACHY", ""
    if norm is None:  # Chapman
        return ("SINUS_NORMAL", "") if not other else ("SINUS_OUTRO", "")
    return ("SINUS_NORMAL", "") if (norm_ok and not other) else ("SINUS_OUTRO", "")
