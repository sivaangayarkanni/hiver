"""Unified intent classifier facade."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from hiver_agent.classify.baselines import (
    KeywordBaseline,
    MajorityBaseline,
    TfidfLogRegClassifier,
)
from hiver_agent.schemas import IntentPrediction

Method = Literal["majority", "keyword", "tfidf"]


class IntentClassifier:
    def __init__(self, method: Method = "tfidf") -> None:
        self.method = method
        if method == "majority":
            self.model: MajorityBaseline | KeywordBaseline | TfidfLogRegClassifier = (
                MajorityBaseline()
            )
        elif method == "keyword":
            self.model = KeywordBaseline()
        else:
            self.model = TfidfLogRegClassifier()

    def fit(self, texts: list[str], labels: list[str]) -> "IntentClassifier":
        self.model.fit(texts, labels)
        return self

    def predict_one(self, text: str) -> IntentPrediction:
        return self.model.predict_one(text)

    def predict(self, texts: list[str]) -> list[IntentPrediction]:
        return self.model.predict(texts)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        if isinstance(self.model, TfidfLogRegClassifier):
            self.model.save(path)
        else:
            # keyword/majority are stateless-ish; store method only
            path.write_text(self.method, encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, method: Optional[Method] = None) -> "IntentClassifier":
        path = Path(path)
        if method == "tfidf" or (method is None and path.suffix in {".pkl", ".joblib"}):
            clf = cls("tfidf")
            clf.model = TfidfLogRegClassifier.load(path)
            return clf
        m = method or "keyword"
        return cls(m)
