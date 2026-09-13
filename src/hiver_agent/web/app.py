"""Deployable FastAPI demo: classify → draft → escalate.

Serves a single-page UI at GET / and JSON at POST /api/analyze.
Default dry_run=True so Railway/Render work without an API key.
"""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

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
        llm = get_llm_client(dry_run=dry_run)
        pipe = SupportAgentPipeline(
            self.classifier, ReplyDrafter(self.index, llm)
        )
        result = pipe.run("web", text)
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
        }


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        ensure_runtime()
    except Exception:
        # First request will retry; /health reports not-ready.
        pass
    yield


app = FastAPI(
    title="Hiver AppleSupport agent",
    description="Classify → draft → escalate demo (dry-run by default).",
    version="0.1.0",
    lifespan=lifespan,
)


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    dry_run: bool = True


class AnalyzeResponse(BaseModel):
    intent: str
    confidence: float
    method: str
    scores: dict[str, float] = Field(default_factory=dict)
    draft: str
    draft_sources: list[str] = Field(default_factory=list)
    draft_method: str
    escalation_action: str
    escalation_reason: str
    rules_fired: list[str] = Field(default_factory=list)
    dry_run: bool


@app.get("/health")
def health() -> dict[str, Any]:
    ready = _runtime is not None
    if not ready:
        try:
            ensure_runtime()
            ready = True
        except Exception:
            ready = False
    payload: dict[str, Any] = {"ok": ready, "status": "ok" if ready else "not_ready"}
    if _ready_error and not ready:
        payload["error"] = _ready_error
    return payload


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    try:
        runtime = ensure_runtime()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"agent not ready: {exc}") from exc
    return AnalyzeResponse(**runtime.analyze(text, dry_run=req.dry_run))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hiver · AppleSupport agent</title>
  <style>
    :root {
      --bg: #0f1412;
      --bg-elev: #17201c;
      --ink: #e8efe9;
      --muted: #8fa196;
      --line: rgba(232, 239, 233, 0.1);
      --accent: #8fbf6a;
      --accent-ink: #10210c;
      --warn: #e0a36a;
      --warn-bg: rgba(224, 163, 106, 0.12);
      --ok: #7dcea0;
      --ok-bg: rgba(125, 206, 160, 0.12);
      --shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, rgba(143, 191, 106, 0.08), transparent 50%),
        radial-gradient(900px 500px at 110% 10%, rgba(224, 163, 106, 0.06), transparent 45%),
        var(--bg);
      color: var(--ink);
    }
    .wrap { max-width: 760px; margin: 0 auto; padding: 48px 20px 72px; }
    header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 28px; }
    .brand { display: flex; gap: 14px; align-items: center; }
    .mark {
      width: 40px; height: 40px; border-radius: 12px;
      background: linear-gradient(160deg, #b7d48e, #5e8f4a);
      display: grid; place-items: center;
      box-shadow: 0 8px 20px rgba(143, 191, 106, 0.25);
    }
    .mark svg { width: 22px; height: 22px; }
    h1 { font-size: 1.55rem; font-weight: 600; letter-spacing: -0.02em; margin: 0; }
    .sub { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; color: var(--muted); font-size: 0.88rem; margin-top: 4px; }
    .badge {
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
      border: 1px solid var(--line); border-radius: 999px;
      padding: 6px 10px; color: var(--accent); background: rgba(143, 191, 106, 0.08);
      white-space: nowrap;
    }
    .badge.live { color: var(--warn); background: var(--warn-bg); }
    .card {
      background: var(--bg-elev);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 22px;
      box-shadow: var(--shadow);
    }
    label { font-family: ui-sans-serif, system-ui, sans-serif; font-size: 0.78rem; color: var(--muted); letter-spacing: 0.04em; text-transform: uppercase; }
    textarea {
      width: 100%; margin-top: 10px; resize: vertical; min-height: 130px;
      background: #101714; color: var(--ink);
      border: 1px solid var(--line); border-radius: 14px;
      padding: 14px 14px; font-size: 1.05rem; line-height: 1.45;
      font-family: inherit; outline: none;
    }
    textarea:focus { border-color: rgba(143, 191, 106, 0.55); box-shadow: 0 0 0 3px rgba(143, 191, 106, 0.15); }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 16px; }
    .chip {
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.78rem; color: var(--ink);
      background: transparent; border: 1px solid var(--line);
      border-radius: 999px; padding: 6px 11px; cursor: pointer;
    }
    .chip:hover { border-color: var(--accent); color: var(--accent); }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    button.run {
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-weight: 600; font-size: 0.95rem;
      background: var(--accent); color: var(--accent-ink);
      border: 0; border-radius: 999px; padding: 11px 20px; cursor: pointer;
    }
    button.run:disabled { opacity: 0.55; cursor: wait; }
    button.run:hover:not(:disabled) { filter: brightness(1.06); }
    .hint { font-family: ui-sans-serif, system-ui, sans-serif; font-size: 0.78rem; color: var(--muted); }
    #status { min-height: 1.2em; margin-top: 12px; font-family: ui-sans-serif, system-ui, sans-serif; font-size: 0.85rem; color: var(--muted); }
    #status.err { color: #e08b7a; }
    #results { display: none; margin-top: 22px; }
    .grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
    @media (min-width: 640px) { .split { grid-template-columns: 1fr 1fr; } }
    .panel { background: #121a16; border: 1px solid var(--line); border-radius: 16px; padding: 16px 16px 14px; }
    .k { font-family: ui-sans-serif, system-ui, sans-serif; font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }
    .intent {
      font-size: 1.2rem; margin: 0 0 8px;
      font-variant: lining-nums;
    }
    .conf-bar { height: 6px; background: #243028; border-radius: 99px; overflow: hidden; }
    .conf-bar > span { display: block; height: 100%; background: var(--accent); width: 0; transition: width 0.35s ease; }
    .conf-num { font-family: ui-sans-serif, system-ui, sans-serif; font-size: 0.8rem; color: var(--muted); margin-top: 6px; }
    .action {
      display: inline-block; font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.78rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
      border-radius: 999px; padding: 5px 10px; margin-bottom: 8px;
    }
    .action.escalate { background: var(--warn-bg); color: var(--warn); }
    .action.auto_handle { background: var(--ok-bg); color: var(--ok); }
    .reason, .draft { margin: 0; line-height: 1.5; font-size: 1.02rem; }
    .draft { white-space: pre-wrap; }
    footer { margin-top: 28px; font-family: ui-sans-serif, system-ui, sans-serif; font-size: 0.75rem; color: var(--muted); }
    footer code { color: var(--ink); }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <div class="mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 3c1.2 2.4.6 4.4-.6 5.6C9.8 6.8 8 6.2 6.6 6.8 8.2 4.4 10.2 3.2 12 3z" fill="#10210c"/>
            <path d="M7 10.2c2.2-1.4 4.2-.8 5-0.2.8-.6 2.8-1.2 5 .2 1.6 1 2.6 2.8 2.6 4.8 0 3.6-3.1 6.2-7.6 6.2S4.4 18.6 4.4 15c0-2 .9-3.8 2.6-4.8z" fill="#10210c"/>
          </svg>
        </div>
        <div>
          <h1>AppleSupport agent</h1>
          <div class="sub">Hiver take-home · classify → draft → escalate</div>
        </div>
      </div>
      <div id="modeBadge" class="badge">Dry-run</div>
    </header>

    <div class="card">
      <label for="msg">Customer message</label>
      <textarea id="msg" placeholder="e.g. Battery draining after the iOS update…">Battery draining after iOS update — any tips?</textarea>
      <div class="chips">
        <button type="button" class="chip" data-text="I cannot sign in to my Apple ID — keeps saying locked for security reasons.">Apple ID locked</button>
        <button type="button" class="chip" data-text="iCloud storage full, can't backup photos.">iCloud full</button>
        <button type="button" class="chip" data-text="My iPhone was stolen last night. I need to lock it and wipe it.">Stolen iPhone</button>
        <button type="button" class="chip" data-text="There's an unauthorized charge on my App Store receipt. I want a refund.">Unauthorized charge</button>
      </div>
      <div class="row">
        <div class="hint">Uses the TF-IDF model + mock LLM unless you send <code>dry_run: false</code>.</div>
        <button class="run" id="runBtn" type="button">Run agent</button>
      </div>
      <div id="status"></div>
    </div>

    <div id="results">
      <div class="grid split" style="margin-top:0">
        <div class="panel">
          <div class="k">Intent + confidence</div>
          <p class="intent" id="intent"></p>
          <div class="conf-bar"><span id="confBar"></span></div>
          <div class="conf-num" id="confNum"></div>
        </div>
        <div class="panel">
          <div class="k">Escalation</div>
          <div id="action" class="action">—</div>
          <p class="reason" id="reason"></p>
        </div>
      </div>
      <div class="panel" style="margin-top:12px">
        <div class="k">Drafted reply</div>
        <p class="draft" id="draft"></p>
      </div>
    </div>

    <footer>
      Local / deploy start:
      <code>uvicorn hiver_agent.web.app:app --host 0.0.0.0 --port ${PORT:-8000}</code>
    </footer>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const msg = $("msg");
    const runBtn = $("runBtn");
    const status = $("status");
    const results = $("results");
    const badge = $("modeBadge");

    document.querySelectorAll(".chip").forEach((el) => {
      el.addEventListener("click", () => { msg.value = el.dataset.text; msg.focus(); });
    });

    async function run() {
      const text = msg.value.trim();
      if (!text) { status.className = "err"; status.textContent = "Enter a customer message."; return; }
      runBtn.disabled = true;
      status.className = "";
      status.textContent = "Running classify → draft → escalate…";
      try {
        const res = await fetch("/api/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, dry_run: true }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || res.statusText);
        results.style.display = "block";
        $("intent").textContent = data.intent.replaceAll("_", " ");
        const pct = Math.round((data.confidence || 0) * 100);
        $("confBar").style.width = pct + "%";
        $("confNum").textContent = (data.confidence || 0).toFixed(2) + " · " + (data.method || "");
        const act = data.escalation_action || "";
        $("action").textContent = act.replaceAll("_", " ");
        $("action").className = "action " + act;
        $("reason").textContent = data.escalation_reason || "";
        $("draft").textContent = data.draft || "";
        badge.textContent = data.dry_run ? "Dry-run" : "Live LLM";
        badge.className = data.dry_run ? "badge" : "badge live";
        status.textContent = "Done.";
      } catch (err) {
        status.className = "err";
        status.textContent = err.message || String(err);
      } finally {
        runBtn.disabled = false;
      }
    }
    runBtn.addEventListener("click", run);
    msg.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
    });
  </script>
</body>
</html>
"""
