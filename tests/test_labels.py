from src.config import load_config
from src.labels import assign_group

CFG = load_config()
CH = CFG["labels"]["chapman"]
PT = CFG["labels"]["ptbxl"]


def g(acr, base=CH, norm_ok=None):
    return assign_group(set(acr), base, norm_ok=norm_ok)[0]


def test_chapman_basic_groups():
    assert g({"AFIB"}) == "AFIB"
    assert g({"AFIB", "STTC"}) == "AFIB"
    assert g({"AFIB", "VPB"}) == "AFIB"
    assert g({"SR"}) == "SINUS_NORMAL"
    assert g({"SR", "TWC"}) == "SINUS_OUTRO"
    assert g({"SB"}) == "SINUS_BRADY"
    assert g({"SR", "SB"}) == "SINUS_BRADY"
    assert g({"ST", "STTC"}) == "SINUS_TACHY"
    assert g({"SA"}) == "SINUS_ARRITMIA"


def test_chapman_conflicts_and_out_of_training():
    assert g({"AFIB", "SR"}) == "CONFLITO"
    assert g({"AFIB", "1AVB"}) == "CONFLITO"
    assert g({"SB", "ST"}) == "CONFLITO"
    assert g({"AF"}) == "FORA_DE_TREINO"
    assert g({"SR", "AF"}) == "CONFLITO"
    assert g({"SR", "1AVB"}) == "FORA_DE_TREINO"
    assert g({"SB", "VPB"}) == "FORA_DE_TREINO"
    assert g({"TWC"}) == "SEM_RITMO"
    assert g(set()) == "SEM_RITMO"


def test_ptbxl_groups():
    assert g({"SR", "NORM"}, PT, norm_ok=True) == "SINUS_NORMAL"
    assert g({"SR", "NORM"}, PT, norm_ok=False) == "SINUS_OUTRO"
    assert g({"SR", "NORM", "LVH"}, PT, norm_ok=True) == "SINUS_OUTRO"
    assert g({"AFIB", "NDT"}, PT) == "AFIB"
    assert g({"SBRAD", "NORM"}, PT, norm_ok=True) == "SINUS_BRADY"
    assert g({"STACH"}, PT) == "SINUS_TACHY"
    assert g({"AFLT"}, PT) == "FORA_DE_TREINO"
    assert g({"SR", "PVC"}, PT) == "FORA_DE_TREINO"
    assert g({"SR", "BIGU"}, PT) == "FORA_DE_TREINO"
    assert g({"AFIB", "BIGU"}, PT) == "AFIB"
    assert g({"NORM", "PVC"}, PT) == "FORA_DE_TREINO"
