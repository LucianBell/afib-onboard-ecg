"""Download, indexação e extração da derivação I das bases Chapman e PTB-XL.

Uso:
    python -m src.data download          # baixa os zips (com retomada) e extrai
    python -m src.data index             # monta índices + cache da derivação I (500 Hz, mV)
    python -m src.data all [--subset N]  # ambos; --subset N limita N registros por base

Saídas em data/interim/:
    {base}_index.parquet     metadados, rótulos, grupo e estatísticas de qualidade por registro
    {base}_leadI_500hz.npy   matriz (N, 5000) float32 em mV, NaN onde faltar amostra
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import wfdb
from joblib import Parallel, delayed
from scipy.signal import butter, sosfiltfilt

from src.config import ROOT, load_config
from src.labels import (
    assign_group,
    check_config_acronyms,
    chapman_source,
    load_chapman_dictionary,
    load_ptbxl_statements,
    load_supplementary_dictionary,
)


# ---------------------------------------------------------------- download
def sha256(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def download(cfg: dict) -> dict:
    zips = cfg["paths"]["zips"]
    zips.mkdir(parents=True, exist_ok=True)
    info = {}
    for key, d in cfg["datasets"].items():
        z = zips / d["zip"]
        if not (z.exists() and z.stat().st_size == d["expected_bytes"]):
            # curl -C - retoma downloads interrompidos; -f falha em erro HTTP
            subprocess.run(["curl", "-fL", "-C", "-", "--retry", "5", "-o", str(z), d["url"]], check=True)
        if z.stat().st_size != d["expected_bytes"]:
            raise RuntimeError(f"{z}: tamanho {z.stat().st_size} != esperado {d['expected_bytes']}")
        out = cfg["paths"]["raw"] / d["extract_dir"]
        if not out.exists():
            print(f"[{key}] extraindo {z.name} ...", flush=True)
            with zipfile.ZipFile(z) as zf:
                bad = zf.testzip()
                if bad:
                    raise RuntimeError(f"{z}: arquivo corrompido no zip: {bad}")
                zf.extractall(out)
        info[key] = {"zip": z.name, "bytes": z.stat().st_size, "sha256": sha256(z),
                     "version": d["version"], "url": d["url"]}
        marker = "ConditionNames_SNOMED-CT.csv" if key == "chapman" else "ptbxl_database.csv"
        info[key]["file_check"] = verify_sha256sums(find_root(out, marker))
        print(f"[{key}] ok {info[key]['bytes']} bytes sha256={info[key]['sha256'][:12]}", flush=True)
    sup = cfg["datasets"].get("chapman", {}).get("supplementary_dx_maps")
    if sup:
        sd = ROOT / sup["dir"]
        sd.mkdir(parents=True, exist_ok=True)
        for fname, url in sup["files"].items():
            subprocess.run(["curl", "-fsL", "--retry", "5", "-o", str(sd / fname), url], check=True)
        info["chapman"]["supplementary_dx_maps"] = {f: sha256(sd / f) for f in sup["files"]}
    res = cfg["paths"]["results"] / "audit"
    res.mkdir(parents=True, exist_ok=True)
    mp = res / "data_manifest.json"
    old = json.loads(mp.read_text()) if mp.exists() else {}
    mp.write_text(json.dumps({**old, **info}, indent=2))
    return info


def verify_sha256sums(root: Path) -> dict:
    """Confere cada arquivo contra o SHA256SUMS.txt distribuído pela PhysioNet."""
    sums = root / "SHA256SUMS.txt"
    if not sums.exists():
        return {"sha256sums": "ausente"}
    entries = [ln.split(maxsplit=1) for ln in sums.read_text().splitlines() if ln.strip()]
    entries = [(h, n.strip()) for h, n in entries if n.strip() != "SHA256SUMS.txt"]

    def check(h, n):
        f = root / n
        return "missing" if not f.exists() else ("ok" if sha256(f, 1 << 20) == h else "bad")

    out = Parallel(n_jobs=6, batch_size=256)(delayed(check)(h, n) for h, n in entries)
    bad = [n for (h, n), o in zip(entries, out) if o != "ok"]
    return {"files_listed": len(entries), "ok": out.count("ok"), "bad": out.count("bad"),
            "missing": out.count("missing"), "examples_not_ok": bad[:20]}


def find_root(base_dir: Path, marker: str) -> Path:
    hits = sorted(base_dir.rglob(marker))
    if not hits:
        raise FileNotFoundError(f"{marker} não encontrado em {base_dir}")
    return hits[0].parent


# ---------------------------------------------------------------- leitura de sinal
_SOS_HP = {}


def _highpass(fs: float, fc: float):
    key = (fs, fc)
    if key not in _SOS_HP:
        _SOS_HP[key] = butter(2, fc, btype="highpass", fs=fs, output="sos")
    return _SOS_HP[key]


def read_record(rec_path: str, n_expected: int, flat_std: float, hp_fc: float) -> tuple[np.ndarray, dict]:
    """Lê um registro WFDB, devolve derivação I em mV (n_expected amostras) e estatísticas.

    A conversão para mV usa ganho e baseline do próprio cabeçalho (via wfdb),
    nunca constantes da documentação.
    """
    st: dict = {"read_ok": False}
    lead = np.full(n_expected, np.nan, dtype=np.float32)
    try:
        rec = wfdb.rdrecord(rec_path, physical=False)
    except Exception as e:  # registro ilegível
        st["read_error"] = f"{type(e).__name__}: {e}"[:200]
        return lead, st
    d = rec.d_signal
    gain = np.asarray(rec.adc_gain, dtype=float)
    base = np.asarray(rec.baseline, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = (d.astype(np.float64) - base) / gain
    st.update(
        read_ok=True,
        fs=rec.fs,
        n_samples=int(d.shape[0]),
        n_leads=int(d.shape[1]),
        units=",".join(sorted(set(rec.units))),
        adc_gain=",".join(sorted({f"{g:g}" for g in gain})),
        adc_res=",".join(sorted({str(r) for r in rec.adc_res})),
        hash_all=hashlib.sha1(np.ascontiguousarray(d).tobytes()).hexdigest(),
    )
    names = [s.strip().upper() for s in rec.sig_name]
    st["has_lead_I"] = "I" in names
    if not st["has_lead_I"]:
        return lead, st
    i = names.index("I")
    x = p[:, i]
    st["hash_leadI"] = hashlib.sha1(np.ascontiguousarray(d[:, i]).tobytes()).hexdigest()
    st["nan_any"] = int(np.isnan(p).sum())
    st["nan_leadI"] = int(np.isnan(x).sum())
    stds = np.nanstd(p, axis=0)
    st["n_flat_leads"] = int((stds < flat_std).sum())
    st["leadI_std_mv"] = float(stds[i])
    st["leadI_flat"] = bool(stds[i] < flat_std)
    st["leadI_zero_frac"] = float(np.mean(d[:, i] == 0))
    st["leadI_raw_min_mv"] = float(np.nanmin(x)) if st["nan_leadI"] < len(x) else np.nan
    st["leadI_raw_max_mv"] = float(np.nanmax(x)) if st["nan_leadI"] < len(x) else np.nan
    # amplitude do QRS: mediana por segundo do pico-a-pico após passa-alta leve
    if st["nan_leadI"] == 0 and len(x) >= rec.fs:
        y = sosfiltfilt(_highpass(rec.fs, hp_fc), x)
        sec = int(rec.fs)
        segs = y[: len(y) // sec * sec].reshape(-1, sec)
        st["qrs_p2p_leadI_mv"] = float(np.median(segs.max(1) - segs.min(1)))
        # mesma medida na derivação de maior amplitude, como referência de escala
        yy = sosfiltfilt(_highpass(rec.fs, hp_fc), np.nan_to_num(p), axis=0)
        sg = yy[: len(yy) // sec * sec].reshape(-1, sec, yy.shape[1])
        st["qrs_p2p_maxlead_mv"] = float(np.median(sg.max(1) - sg.min(1), axis=0).max())
    m = min(n_expected, len(x))
    lead[:m] = x[:m]
    return lead, st


# ---------------------------------------------------------------- limpeza de metadados
def clean_age(df: pd.DataFrame) -> pd.Series:
    """Idade analisável. PTB-XL: 300 = anonimização de > 89 anos -> 90 ("≥ 90").
    Ningbo: 0 é código de ausência (247 registros com 0 e nenhum com 1-3 anos) -> NaN."""
    age = df["age"].astype(float).copy()
    if "source" in df:
        age[(df["source"] == "ptbxl") & (age == 300)] = 90
        age[(df["source"] == "ningbo") & (age == 0)] = np.nan
    return age


# ---------------------------------------------------------------- índices
def _parse_hea_comments(comments: list[str]) -> dict:
    out = {}
    for c in comments:
        if ":" in c:
            k, v = c.split(":", 1)
            out[k.strip().lstrip("#").strip()] = v.strip()
    return out


def chapman_index(cfg: dict, subset: int | None) -> pd.DataFrame:
    root = find_root(cfg["paths"]["raw"] / cfg["datasets"]["chapman"]["extract_dir"], "ConditionNames_SNOMED-CT.csv")
    code_to_acr, dic = load_chapman_dictionary(root / "ConditionNames_SNOMED-CT.csv")
    sup_cfg = cfg["datasets"]["chapman"]["supplementary_dx_maps"]
    sup_dir = ROOT / sup_cfg["dir"]
    sup = load_supplementary_dictionary([sup_dir / f for f in sup_cfg["files"]], code_to_acr)
    known = set(dic["Acronym Name"].str.strip()) | {a for v in sup.values() for a in v}
    bad = check_config_acronyms(cfg["labels"]["chapman"], known)
    if bad:
        raise ValueError(f"acrônimos do config ausentes no dicionário Chapman: {bad}")
    heas = sorted(root.rglob("*.hea"))
    if subset and subset < len(heas):
        rng = np.random.default_rng(cfg["seed"])
        heas = [heas[i] for i in sorted(rng.choice(len(heas), subset, replace=False))]
    rows = []
    for h in heas:
        try:
            hdr = wfdb.rdheader(str(h.with_suffix("")))
            meta = _parse_hea_comments(hdr.comments)
            hdr_ok, err = True, ""
        except Exception as e:
            meta, hdr_ok, err = {}, False, f"{type(e).__name__}: {e}"[:200]
        codes = [c.strip() for c in meta.get("Dx", "").split(",") if c.strip()]
        acr, unknown, supp = set(), [], []
        for c in codes:
            if c in code_to_acr:
                acr.update(code_to_acr[c])
            elif c in sup:
                acr.update(sup[c])
                supp.append(c)
            else:
                unknown.append(c)
        group, sub = assign_group(acr, cfg["labels"]["chapman"])
        age = pd.to_numeric(meta.get("Age"), errors="coerce")
        sex = {"male": "M", "female": "F"}.get(meta.get("Sex", "").lower(), None)
        rows.append(
            dict(record_id=h.stem, path=str(h.with_suffix("")), header_ok=hdr_ok, header_error=err,
                 dx_codes=",".join(codes), acronyms=",".join(sorted(acr)), unknown_codes=",".join(unknown),
                 supplementary_codes=",".join(supp), source=chapman_source(h.stem, cfg["datasets"]["chapman"]["shaoxing_last_record"]),
                 group=group, subtype=sub, age=age, sex=sex,
                 hea_keys=",".join(sorted(meta)), patient_id=None)
        )
    df = pd.DataFrame(rows)
    df.attrs["dictionary"] = str(root / "ConditionNames_SNOMED-CT.csv")
    return df


def ptbxl_index(cfg: dict, subset: int | None) -> pd.DataFrame:
    root = find_root(cfg["paths"]["raw"] / cfg["datasets"]["ptbxl"]["extract_dir"], "ptbxl_database.csv")
    stm = load_ptbxl_statements(root / "scp_statements.csv")
    bcfg = cfg["labels"]["ptbxl"]
    bad = check_config_acronyms(bcfg, set(stm.index))
    if bad:
        raise ValueError(f"enunciados do config ausentes em scp_statements.csv: {bad}")
    db = pd.read_csv(root / "ptbxl_database.csv", index_col="ecg_id")
    if subset and subset < len(db):
        db = db.sample(subset, random_state=cfg["seed"]).sort_index()
    rows = []
    for ecg_id, r in db.iterrows():
        scp = ast.literal_eval(r["scp_codes"])
        acr = set(scp)
        unknown = sorted(acr - set(stm.index))
        norm_ok = scp.get(bcfg["norm_statement"], -1) >= bcfg["norm_min_likelihood"]
        group, sub = assign_group(acr, bcfg, norm_ok=norm_ok)
        rows.append(
            dict(record_id=f"ptbxl_{ecg_id:05d}", path=str(root / r["filename_hr"]), header_ok=True, header_error="",
                 dx_codes=json.dumps(scp), acronyms=",".join(sorted(acr)), unknown_codes=",".join(unknown),
                 supplementary_codes="", source="ptbxl",
                 group=group, subtype=sub, age=r["age"], sex={0: "M", 1: "F"}.get(int(r["sex"]), None),
                 patient_id=str(int(r["patient_id"])), strat_fold=int(r["strat_fold"]),
                 validated_by_human=bool(r["validated_by_human"]), device=r["device"], site=r["site"],
                 baseline_drift=r["baseline_drift"], static_noise=r["static_noise"], burst_noise=r["burst_noise"],
                 electrodes_problems=r["electrodes_problems"], extra_beats=r["extra_beats"], pacemaker=r["pacemaker"])
        )
    return pd.DataFrame(rows)


def build(cfg: dict, base: str, subset: int | None = None) -> pd.DataFrame:
    interim = cfg["paths"]["interim"]
    interim.mkdir(parents=True, exist_ok=True)
    df = chapman_index(cfg, subset) if base == "chapman" else ptbxl_index(cfg, subset)
    n_exp = cfg["datasets"][base]["n_samples"]
    a = cfg["audit"]
    arr = np.lib.format.open_memmap(interim / f"{base}_leadI_500hz.npy", mode="w+", dtype=np.float32,
                                    shape=(len(df), n_exp))
    stats = []
    gen = Parallel(n_jobs=a["n_jobs"], return_as="generator", batch_size=64)(
        delayed(read_record)(p, n_exp, a["flat_std_mv"], a["amplitude_highpass_hz"]) for p in df["path"]
    )
    for k, (lead, st) in enumerate(gen):
        arr[k] = lead
        stats.append(st)
        if (k + 1) % 5000 == 0:
            print(f"[{base}] {k + 1}/{len(df)}", flush=True)
    arr.flush()
    df = pd.concat([df.reset_index(drop=True), pd.DataFrame(stats)], axis=1)
    df["row"] = np.arange(len(df))
    df.to_parquet(interim / f"{base}_index.parquet", index=False)
    print(f"[{base}] {len(df)} registros indexados", flush=True)
    return df


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "index", "all"])
    ap.add_argument("--bases", nargs="*", default=None, help="restringe a algumas bases")
    ap.add_argument("--subset", type=int, default=None, help="limita N registros por base (teste rápido)")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.bases:
        cfg["datasets"] = {k: v for k, v in cfg["datasets"].items() if k in args.bases}
    if args.cmd in ("download", "all"):
        download(cfg)
    if args.cmd in ("index", "all"):
        for base in cfg["datasets"]:
            build(cfg, base, args.subset)


if __name__ == "__main__":
    sys.exit(main())
