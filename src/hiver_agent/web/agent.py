"""Agent runtime shared by the web app: classify -> draft -> escalate.

Loads (or quickly trains) the TF-IDF intent model and the retrieval index once
per process and caches them. Safe to call from multiple threads.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Optional

from hiver_agent.classify.predict import IntentClassifier
from hiver_agent.data.io import load_jsonl
from hiver_agent.data.threads import build_threads
from hiver_agent.llm.client import get_llm_client
from hiver_agent.pipeline.run import SupportAgentPipeline
from hiver_agent.retrieve.draft import ReplyDrafter
from hiver_agent.retrieve.index import RetrievalIndex
from hiver_agent.schemas import GoldenExample, Message, Thread


def _find_root() -> Path:
    env = os.getenv("HIVER_ROOT")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd())
    candidates.append(Path("/app"))
    here = Path(__file__).resolve()
    candidates.extend(here.parents)
    for c in candidates:
        if (c / "data" / "sample" / "messages.jsonl").exists():
            return c
        if (c / "data" / "golden" / "golden.jsonl").exists():
            return c
    return Path.cwd()


def _threads_from_golden(path: Path) -> list[Thread]:
    threads: list[Thread] = []
    for raw in load_jsonl(path):
        g = GoldenExample.model_validate(raw)
        msgs = [
            Message(
                message_id=f"{g.example_id}-c",
                thread_id=g.thread_id,
                author="customer",
                role="customer",
                text=g.customer_text,
                created_at="",
            )
        ]
        if g.reference_reply:
            msgs.append(
                Message(
                    message_id=f"{g.example_id}-a",
                    thread_id=g.thread_id,
                    author="AppleSupport",
                    role="agent",
                    text=g.reference_reply,
                    created_at="",
                )
            )
        threads.append(
            Thread(
                thread_id=g.thread_id,
                messages=msgs,
                customer_text=g.customer_text,
                resolution_text=g.reference_reply or "",
                intent=g.intent,
            )
        )
    return threads


def _load_threads(root: Path) -> list[Thread]:
    sample = root / "data" / "sample" / "messages.jsonl"
    golden = root / "data" / "golden" / "golden.jsonl"
    if sample.exists():
        return build_threads(load_jsonl(sample))
    if golden.exists():
        return _threads_from_golden(golden)
    return []


def _xy(threads: list[Thread]) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    for t in threads:
        if t.customer_text and t.intent:
            texts.append(t.customer_text)
            labels.append(t.intent)
    return texts, labels


def _load_or_train(root: Path, threads: list[Thread]) -> IntentClassifier:
    model_path = root / "artifacts" / "tfidf_logreg.pkl"
    if model_path.exists():
        try:
            return IntentClassifier.load(model_path, method="tfidf")
        except Exception:
            pass
    texts, labels = _xy(threads)
    if not texts:
        clf = IntentClassifier("keyword")
        clf.fit(["help"], ["other"])
        return clf
    clf = IntentClassifier("tfidf").fit(texts, labels)
    try:
        clf.save(model_path)
    except OSError:
        pass
    return clf


class AgentRuntime:
    def __init__(self, classifier: IntentClassifier, index: RetrievalIndex) -> None:
        self.classifier = classifier
        self.index = index

    def analyze(self, text: str, dry_run: bool = True) -> dict[str, Any]:
        """Run the full pipeline. If a live LLM call fails, fall back to the
        deterministic dry-run drafter instead of failing the request."""
        llm_error: Optional[str] = None
        try:
            result = self._run(text, dry_run=dry_run)
        except Exception as exc:  # network / provider errors on the live path
            if dry_run:
                raise
            llm_error = f"{type(exc).__name__}: {exc}"[:300]
            result = self._run(text, dry_run=True)
        return {
            "intent": result.intent.intent,
            "confidence": result.intent.confidence,
            "method": result.intent.method,
            "scores": result.intent.scores,
            "draft": result.draft.text,
            "draft_sources": result.draft.sources,
            "draft_method": result.draft.method,
            "escalation_action": result.escalation.action,
            "escalation_reason": result.escalation.reason,
            "rules_fired": result.escalation.rules_fired,
            "dry_run": result.draft.dry_run,
            "llm_error": llm_error,
        }

    def _run(self, text: str, dry_run: bool):
        llm = get_llm_client(dry_run=dry_run)
        pipe = SupportAgentPipeline(self.classifier, ReplyDrafter(self.index, llm))
        return pipe.run("web", text)


_lock = threading.Lock()
_runtime: Optional[AgentRuntime] = None
_ready_error: Optional[str] = None


def ensure_runtime() -> AgentRuntime:
    global _runtime, _ready_error
    if _runtime is not None:
        return _runtime
    with _lock:
        if _runtime is not None:
            return _runtime
        try:
            root = _find_root()
            threads = _load_threads(root)
            clf = _load_or_train(root, threads)
            index = RetrievalIndex().build(threads)
            _runtime = AgentRuntime(clf, index)
            _ready_error = None
        except Exception as exc:  # pragma: no cover - surfaced via /health
            _ready_error = str(exc)
            raise
        return _runtime


def runtime_error() -> Optional[str]:
    return _ready_error


def runtime_ready() -> bool:
    return _runtime is not None
