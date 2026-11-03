"""Deduplicação e divisão treino/validação/teste sem vazamento."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

SOURCE_PRIORITY = {"shaoxing": 0, "ptbxl": 1, "ningbo": 2}


def dedupe(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Mantém uma cópia por hash do sinal (preferindo Shaoxing, D16). Retorna (df, n_removidos)."""
    d = df.assign(_pri=df["source"].map(SOURCE_PRIORITY).fillna(9)).sort_values(["_pri", "record_id"])
    out = d.drop_duplicates("hash_all", keep="first").drop(columns="_pri").sort_values("record_id")
    return out, len(df) - len(out)


def split_records(df: pd.DataFrame, fracs=(0.70, 0.15, 0.15), seed: int = 0, stratify_col: str = "group") -> pd.Series:
    """Divisão estratificada por grupo (AFIB, bradi, taqui... ficam proporcionais). Retorna série 'split'."""
    a, b, c = fracs
    idx = df.index.to_numpy()
    tr, rest = train_test_split(idx, test_size=b + c, stratify=df[stratify_col], random_state=seed)
    va, te = train_test_split(rest, test_size=c / (b + c), stratify=df.loc[rest, stratify_col], random_state=seed)
    s = pd.Series("", index=df.index, name="split")
    s[tr], s[va], s[te] = "train", "val", "test"
    return s


def assert_disjoint(split_df: pd.DataFrame, cols=("record_id", "hash_all")) -> None:
    for c in cols:
        g = split_df.groupby(c)["split"].nunique()
        bad = g[g > 1]
        if len(bad):
            raise AssertionError(f"vazamento: {len(bad)} valores de {c} em mais de uma divisão")
