"""Modelos AFIB vs. sinusal: regressão logística, Random Forest, LightGBM e CNN 1D compacta.

Os três primeiros usam os atributos de `src/features.py`; toda transformação (imputação,
padronização) fica dentro de um Pipeline do scikit-learn, ajustado só no treino.
A CNN recebe a janela pré-processada (2.400 amostras) e tem < 100 mil parâmetros.
"""
from __future__ import annotations

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ------------------------------------------------------------------ modelos de atributos
GRIDS = {
    "logreg": {"clf__C": [0.01, 0.1, 1.0, 10.0]},
    "random_forest": {"clf__max_depth": [8, 16, None], "clf__min_samples_leaf": [1, 5],
                      "clf__max_features": ["sqrt", 0.3]},
    "lightgbm": {"clf__num_leaves": [7, 15, 31], "clf__n_estimators": [150, 400],
                 "clf__min_child_samples": [20, 50]},
}


def make_feature_model(name: str, seed: int) -> Pipeline:
    imp = ("imp", SimpleImputer(strategy="median", add_indicator=True))
    if name == "logreg":
        return Pipeline([imp, ("sc", StandardScaler()),
                         ("clf", LogisticRegression(class_weight="balanced", max_iter=5000))])
    if name == "random_forest":
        return Pipeline([imp, ("clf", RandomForestClassifier(n_estimators=300, class_weight="balanced_subsample",
                                                             n_jobs=4, random_state=seed))])
    if name == "lightgbm":
        return Pipeline([imp, ("clf", LGBMClassifier(learning_rate=0.05, subsample=0.8, subsample_freq=1,
                                                     colsample_bytree=0.8, class_weight="balanced",
                                                     random_state=seed, n_jobs=4, verbose=-1))])
    raise ValueError(name)


class PlattCalibrator:
    """Calibração sigmoide de um escore, ajustada na validação (monotônica: não muda ranking)."""

    def fit(self, score, y):
        z = self._z(score).reshape(-1, 1)
        self.lr = LogisticRegression(C=1e6, max_iter=1000).fit(z, np.asarray(y).astype(int))
        return self

    @staticmethod
    def _z(s):
        s = np.clip(np.asarray(s, float), 1e-6, 1 - 1e-6)
        return np.log(s / (1 - s))

    def transform(self, score):
        return self.lr.predict_proba(self._z(score).reshape(-1, 1))[:, 1]


# ------------------------------------------------------------------ CNN 1D compacta
def _torch():
    import torch
    import torch.nn as nn

    return torch, nn


def build_cnn():
    torch, nn = _torch()

    def block(ci, co, k, s, pool):
        layers = [nn.Conv1d(ci, co, k, stride=s, padding=k // 2, bias=False), nn.BatchNorm1d(co), nn.ReLU()]
        if pool:
            layers.append(nn.MaxPool1d(2))
        return layers

    class CNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.body = nn.Sequential(*block(1, 16, 7, 2, False), *block(16, 24, 7, 2, True),
                                      *block(24, 32, 5, 2, True), *block(32, 48, 5, 1, True),
                                      *block(48, 64, 3, 1, False))
            self.drop = nn.Dropout(0.3)
            self.head = nn.Linear(64 * 3, 1)

        def forward(self, x):
            h = self.body(x)
            # média, desvio-padrão e máximo no tempo: o desvio carrega a variabilidade entre batimentos
            z = torch.cat([h.mean(-1), h.std(-1), h.amax(-1)], dim=1)
            return self.head(self.drop(z)).squeeze(-1)

    return CNN()


def n_params(model) -> int:
    return int(sum(p.numel() for p in model.parameters()))


def train_cnn(raw_train: np.ndarray, y_train: np.ndarray, seed: int, max_epochs: int = 40, patience: int = 6,
              batch: int = 64, log=print):
    """Treina a CNN. `raw_train`: (N, 2500) a 250 Hz, sem filtro; a cada época faz recorte aleatório
    de 2.400 + `preprocess_window` (mesma função da inferência) + ruído leve.
    Parada antecipada em 10% do treino (a validação fica intocada para a escolha do modelo)."""
    torch, nn = _torch()
    from sklearn.metrics import average_precision_score
    from sklearn.model_selection import train_test_split

    from src.preprocess import crop, preprocess_window

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    idx_tr, idx_es = train_test_split(np.arange(len(y_train)), test_size=0.10, stratify=y_train, random_state=seed)
    X_es = np.stack([preprocess_window(crop(raw_train[i])) for i in idx_es])[:, None, :]
    model = build_cnn()
    pos = y_train[idx_tr].mean()
    lossf = nn.BCEWithLogitsLoss(pos_weight=torch.tensor((1 - pos) / pos, dtype=torch.float32))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    best, best_state, bad = -1.0, None, 0
    for ep in range(max_epochs):
        model.train()
        order = rng.permutation(idx_tr)
        for s in range(0, len(order), batch):
            ii = order[s : s + batch]
            xb = np.stack([preprocess_window(crop(raw_train[i], mode="random", rng=rng)) for i in ii])
            xb = xb + rng.normal(0, 0.02, xb.shape).astype(np.float32)
            xb = torch.from_numpy(xb[:, None, :].astype(np.float32))
            yb = torch.from_numpy(y_train[ii].astype(np.float32))
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            opt.step()
        ap = average_precision_score(y_train[idx_es], predict_cnn(model, X_es))
        log(f"  cnn época {ep + 1}: AUPRC (parada antecipada, 10% do treino) = {ap:.4f}")
        if ap > best + 1e-4:
            best, bad = ap, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model, {"epocas": ep + 1, "auprc_parada": best, "n_parametros": n_params(model)}


def predict_cnn(model, X: np.ndarray, batch: int = 512) -> np.ndarray:
    torch, _ = _torch()
    model.eval()
    X = np.asarray(X, np.float32)
    if X.ndim == 2:
        X = X[:, None, :]
    out = []
    with torch.no_grad():
        for s in range(0, len(X), batch):
            out.append(torch.sigmoid(model(torch.from_numpy(X[s : s + batch]))).numpy())
    return np.concatenate(out)
