"""TF-IDF retrieval over historical agent resolutions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from hiver_agent.schemas import Thread


@dataclass
class RetrievedDoc:
    thread_id: str
    text: str
    intent: Optional[str]
    score: float


class RetrievalIndex:
    def __init__(self) -> None:
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=12000)
        self.doc_texts: list[str] = []
        self.meta: list[dict] = []
        self.matrix = None

    def build(self, threads: list[Thread]) -> "RetrievalIndex":
        docs: list[str] = []
        meta: list[dict] = []
        for t in threads:
            if not t.resolution_text:
                continue
            # index query side = customer text; doc = resolution
            docs.append(t.resolution_text)
            meta.append(
                {
                    "thread_id": t.thread_id,
                    "intent": t.intent,
                    "customer_text": t.customer_text,
                    "resolution_text": t.resolution_text,
                }
            )
        if not docs:
            # fallback empty
            self.doc_texts = []
            self.meta = []
            self.matrix = None
            return self
        self.doc_texts = docs
        self.meta = meta
        self.matrix = self.vectorizer.fit_transform(docs)
        return self

    def query(self, text: str, k: int = 3, intent: Optional[str] = None) -> list[RetrievedDoc]:
        if self.matrix is None or not self.doc_texts:
            return []
        q = self.vectorizer.transform([text])
        sims = cosine_similarity(q, self.matrix)[0]
        idxs = np.argsort(-sims)
        out: list[RetrievedDoc] = []
        for i in idxs:
            m = self.meta[i]
            if intent and m.get("intent") and m["intent"] != intent:
                # soft filter: skip mismatched if we still have room later
                continue
            out.append(
                RetrievedDoc(
                    thread_id=m["thread_id"],
                    text=m["resolution_text"],
                    intent=m.get("intent"),
                    score=float(sims[i]),
                )
            )
            if len(out) >= k:
                break
        # if intent filter too strict, fall back
        if not out:
            for i in idxs[:k]:
                m = self.meta[i]
                out.append(
                    RetrievedDoc(
                        thread_id=m["thread_id"],
                        text=m["resolution_text"],
                        intent=m.get("intent"),
                        score=float(sims[i]),
                    )
                )
        return out
