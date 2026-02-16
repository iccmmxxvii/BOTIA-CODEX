from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass
class ModelStatus:
    healthy: bool
    n_samples: int
    last_trained: str | None
    metrics: dict[str, float]
    reason: str


class EpisodeModel:
    def __init__(self, model_path: str = "model.joblib", meta_path: str = "model_meta.json") -> None:
        self.model_path = Path(model_path)
        self.meta_path = Path(meta_path)
        self.pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(max_iter=500)),
            ]
        )
        self.feature_cols: list[str] = []
        self.metrics: dict[str, float] = {}
        self.last_trained: str | None = None
        self.n_samples: int = 0
        self.is_fitted = False
        self._load()

    def _load(self) -> None:
        if self.model_path.exists() and self.meta_path.exists():
            self.pipeline = joblib.load(self.model_path)
            meta = json.loads(self.meta_path.read_text())
            self.feature_cols = meta.get("feature_cols", [])
            self.metrics = meta.get("metrics", {})
            self.last_trained = meta.get("last_trained")
            self.n_samples = int(meta.get("n_samples", 0))
            self.is_fitted = True

    def _save(self) -> None:
        joblib.dump(self.pipeline, self.model_path)
        self.meta_path.write_text(
            json.dumps(
                {
                    "feature_cols": self.feature_cols,
                    "metrics": self.metrics,
                    "last_trained": self.last_trained,
                    "n_samples": self.n_samples,
                },
                indent=2,
            )
        )

    def train(self, x: pd.DataFrame, y: pd.Series, max_samples: int = 2000) -> dict[str, float]:
        if x.empty or y.empty:
            return {}
        if len(x) > max_samples:
            x = x.iloc[-max_samples:].copy()
            y = y.iloc[-max_samples:].copy()

        self.feature_cols = list(x.columns)
        split = int(len(x) * 0.8)
        if split < 50 or len(x) - split < 20:
            self.pipeline.fit(x, y)
            probs = self.pipeline.predict_proba(x)[:, 1]
            preds = (probs >= 0.5).astype(int)
            metrics = {
                "accuracy": float(accuracy_score(y, preds)),
                "brier": float(brier_score_loss(y, probs)),
                "log_loss": float(log_loss(y, probs, labels=[0, 1])),
            }
            if len(np.unique(y)) > 1:
                metrics["roc_auc"] = float(roc_auc_score(y, probs))
        else:
            x_train, y_train = x.iloc[:split], y.iloc[:split]
            x_test, y_test = x.iloc[split:], y.iloc[split:]
            self.pipeline.fit(x_train, y_train)
            probs = self.pipeline.predict_proba(x_test)[:, 1]
            preds = (probs >= 0.5).astype(int)
            metrics = {
                "accuracy": float(accuracy_score(y_test, preds)),
                "brier": float(brier_score_loss(y_test, probs)),
                "log_loss": float(log_loss(y_test, probs, labels=[0, 1])),
            }
            if len(np.unique(y_test)) > 1:
                metrics["roc_auc"] = float(roc_auc_score(y_test, probs))

        self.metrics = metrics
        self.n_samples = len(x)
        self.last_trained = datetime.now(timezone.utc).isoformat()
        self.is_fitted = True
        self._save()
        return metrics

    def predict_p_up(self, feat: dict[str, float]) -> float | None:
        if not self.is_fitted or not self.feature_cols:
            return None
        frame = pd.DataFrame([feat])
        for col in self.feature_cols:
            if col not in frame:
                frame[col] = 0.0
        frame = frame[self.feature_cols]
        prob = float(self.pipeline.predict_proba(frame)[0, 1])
        return prob

    def status(self, stale_hours: int = 6) -> ModelStatus:
        if not self.is_fitted:
            return ModelStatus(False, self.n_samples, self.last_trained, self.metrics, "not trained")
        if self.n_samples < 200:
            return ModelStatus(False, self.n_samples, self.last_trained, self.metrics, "n_samples < 200")

        if self.last_trained:
            dt = datetime.fromisoformat(self.last_trained)
            if datetime.now(timezone.utc) - dt > timedelta(hours=stale_hours):
                return ModelStatus(False, self.n_samples, self.last_trained, self.metrics, "stale model")

        brier = self.metrics.get("brier", 1.0)
        ll = self.metrics.get("log_loss", 1.0)
        if brier > 0.30 or ll > 0.72:
            return ModelStatus(False, self.n_samples, self.last_trained, self.metrics, "poor calibration")

        return ModelStatus(True, self.n_samples, self.last_trained, self.metrics, "ok")
