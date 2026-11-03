"""Carrega configs/default.yaml e resolve caminhos relativos à raiz do repositório."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "configs" / "default.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["paths"] = {k: ROOT / v for k, v in cfg["paths"].items()}
    return cfg
