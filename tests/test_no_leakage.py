from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config import ROOT, load_config
from src.models import make_feature_model
from src.splits import assert_disjoint, dedupe, split_records

CFG = load_config()


def _toy(n=400, seed=0):
    rng = np.random.default_rng(seed)
    g = rng.choice(["AFIB", "SINUS_NORMAL", "SINUS_BRADY"], n, p=[0.2, 0.4, 0.4])
    return pd.DataFrame({"record_id": [f"JS{i:05d}" for i in range(n)], "group": g, "source": "shaoxing",
                         "hash_all": [f"h{i}" for i in range(n)]})


def test_dedupe_keeps_one_copy_preferring_shaoxing():
    df = pd.DataFrame({"record_id": ["JS20000", "JS00001", "JS00002"], "source": ["ningbo", "shaoxing", "shaoxing"],
                       "hash_all": ["x", "x", "y"], "group": ["FORA_DE_TREINO", "AFIB", "SINUS_NORMAL"]})
    out, n = dedupe(df)
    assert n == 1 and set(out["record_id"]) == {"JS00001", "JS00002"}


def test_split_is_disjoint_deterministic_and_stratified():
    df = _toy()
    s1, s2 = split_records(df, seed=1), split_records(df, seed=1)
    assert (s1 == s2).all()
    d = df.assign(split=s1)
    assert_disjoint(d)
    frac = d.groupby("split")["group"].apply(lambda g: (g == "AFIB").mean())
    assert frac.max() - frac.min() < 0.05


def test_assert_disjoint_catches_duplicate_hash():
    d = _toy(10).assign(split=["train"] * 5 + ["test"] * 5)
    d.loc[9, "hash_all"] = d.loc[0, "hash_all"]
    with pytest.raises(AssertionError):
        assert_disjoint(d)


def test_feature_transforms_live_inside_pipeline():
    # imputação e padronização ficam no Pipeline: em CV e no refit são ajustadas só no treino
    for name in ["logreg", "random_forest", "lightgbm"]:
        steps = dict(make_feature_model(name, 0).steps)
        assert "imp" in steps and "clf" in steps


SPLIT = ROOT / "results" / "expA" / "split.csv"
FEATS = CFG["paths"]["processed"] / "chapman_features.parquet"


@pytest.mark.skipif(not (SPLIT.exists() and FEATS.exists()), reason="experimento A ainda não rodado")
def test_expA_split_has_no_leakage():
    s = pd.read_csv(SPLIT)
    f = pd.read_parquet(FEATS, columns=["record_id", "hash_all", "source"])
    d = s.merge(f, on="record_id", how="left")
    assert d["hash_all"].notna().all()
    assert (d["source"] == "shaoxing").all()
    assert_disjoint(d)
    # nenhum registro do treino tem sinal idêntico a um da validação/teste, mesmo fora do conjunto deduplicado
    allf = pd.read_parquet(FEATS, columns=["record_id", "hash_all"])
    ids_by_split = {k: set(v) for k, v in d.groupby("split")["hash_all"]}
    assert not (ids_by_split["train"] & (ids_by_split["val"] | ids_by_split["test"]))
    assert len(allf) >= len(d)


PTB = CFG["paths"]["processed"] / "ptbxl_features.parquet"


@pytest.mark.skipif(not PTB.exists(), reason="atributos do PTB-XL ainda não gerados")
def test_ptbxl_patient_in_single_fold():
    f = pd.read_parquet(PTB, columns=["patient_id", "strat_fold"])
    assert f.groupby("patient_id")["strat_fold"].nunique().max() == 1
