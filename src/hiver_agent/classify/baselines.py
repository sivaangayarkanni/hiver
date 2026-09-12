"""Trivial and simple intent classification baselines."""

from __future__ import annotations

import pickle
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from hiver_agent.intents import INTENT_KEYWORDS, INTENT_NAMES, INTENTS
from hiver_agent.schemas import IntentPrediction


class MajorityBaseline:
    """Always predict the majority training intent (trivial baseline)."""

    def __init__(self) -> None:
        self.majority = "other"
        self.prior: dict[str, float] = {n: 1.0 / len(INTENT_NAMES) for n in INTENT_NAMES}

    def fit(self, texts: list[str], labels: list[str]) -> "MajorityBaseline":
        counts = Counter(labels)
        self.majority = counts.most_common(1)[0][0] if counts else "other"
        total = sum(counts.values()) or 1
        self.prior = {n: counts.get(n, 0) / total for n in INTENT_NAMES}
        return self

    def predict_one(self, text: str) -> IntentPrediction:
        return IntentPrediction(
            intent=self.majority,
            confidence=self.prior.get(self.majority, 0.0),
            method="majority",
            scores=dict(self.prior),
        )

    def predict(self, texts: list[str]) -> list[IntentPrediction]:
        return [self.predict_one(t) for t in texts]


class KeywordBaseline:
    """Score intents by keyword hits (trivial / weak baseline)."""

    def fit(self, texts: list[str], labels: list[str]) -> "KeywordBaseline":
        return self

    def predict_one(self, text: str) -> IntentPrediction:
        text_l = text.lower()
        scores: dict[str, float] = {}
        for intent, kws in INTENT_KEYWORDS.items():
            hits = sum(1 for kw in kws if kw in text_l)
            scores[intent] = float(hits)
        # soft preference for other when nothing matches
        if max(scores.values(), default=0) == 0:
            scores["other"] = 1.0
        total = sum(scores.values()) or 1.0
        probs = {k: v / total for k, v in scores.items()}
        # ensure all intents present
        for n in INTENT_NAMES:
            probs.setdefault(n, 0.0)
        best = max(probs, key=probs.get)
        return IntentPrediction(
            intent=best,
            confidence=probs[best],
            method="keyword",
            scores=probs,
        )

    def predict(self, texts: list[str]) -> list[IntentPrediction]:
        return [self.predict_one(t) for t in texts]


class TfidfLogRegClassifier:
    """Simple strong-ish baseline: TF-IDF + Logistic Regression."""

    def __init__(self) -> None:
        self.pipeline: Optional[Pipeline] = None
        self.labels_: list[str] = list(INTENT_NAMES)

    def fit(self, texts: list[str], labels: list[str]) -> "TfidfLogRegClassifier":
        self.labels_ = sorted(set(labels)) or list(INTENT_NAMES)
        self.pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        min_df=1,
                        max_features=8000,
                        lowercase=True,
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                    ),
                ),
            ]
        )
        self.pipeline.fit(texts, labels)
        return self

    def predict_one(self, text: str) -> IntentPrediction:
        if self.pipeline is None:
            raise RuntimeError("Model not fitted")
        proba = self.pipeline.predict_proba([text])[0]
        classes = list(self.pipeline.classes_)
        scores = {c: float(p) for c, p in zip(classes, proba)}
        for n in INTENT_NAMES:
            scores.setdefault(n, 0.0)
        best = max(scores, key=scores.get)
        return IntentPrediction(
            intent=best,
            confidence=scores[best],
            method="tfidf_logreg",
            scores=scores,
        )

    def predict(self, texts: list[str]) -> list[IntentPrediction]:
        return [self.predict_one(t) for t in texts]

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"pipeline": self.pipeline, "labels": self.labels_}, f)

    @classmethod
    def load(cls, path: str | Path) -> "TfidfLogRegClassifier":
        with Path(path).open("rb") as f:
            blob: dict[str, Any] = pickle.load(f)
        obj = cls()
        obj.pipeline = blob["pipeline"]
        obj.labels_ = blob.get("labels", list(INTENT_NAMES))
        return obj
