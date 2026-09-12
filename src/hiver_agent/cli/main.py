"""Typer CLI: python -m hiver_agent <command>."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from hiver_agent import __version__

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Hiver AppleSupport agent MVP")
console = Console()

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SAMPLE = ROOT / "data" / "sample" / "messages.jsonl"
DEFAULT_GOLDEN = ROOT / "data" / "golden" / "golden.jsonl"
DEFAULT_MODEL = ROOT / "artifacts" / "tfidf_logreg.pkl"
DEFAULT_THREADS = ROOT / "artifacts" / "threads.jsonl"


@app.callback()
def _main() -> None:
    """AppleSupport AI Twitter support agent (Hiver take-home MVP)."""


@app.command("version")
def version() -> None:
    console.print(f"hiver-agent {__version__}")


@app.command("prepare-data")
def prepare_data(
    input_path: Path = typer.Option(DEFAULT_SAMPLE, "--input", "-i"),
    output_path: Path = typer.Option(DEFAULT_THREADS, "--output", "-o"),
) -> None:
    """Build threads from message JSONL."""
    from hiver_agent.data.io import load_jsonl, save_jsonl
    from hiver_agent.data.threads import build_threads

    raw = load_jsonl(input_path)
    threads = build_threads(raw)
    rows = [t.model_dump() for t in threads]
    # serialize messages properly
    for r in rows:
        r["messages"] = [m if isinstance(m, dict) else m for m in r["messages"]]
    n = save_jsonl(output_path, rows)
    console.print(f"Wrote {n} threads → {output_path}")


@app.command("train")
def train(
    input_path: Path = typer.Option(DEFAULT_SAMPLE, "--input", "-i"),
    model_path: Path = typer.Option(DEFAULT_MODEL, "--model", "-m"),
    method: str = typer.Option("tfidf", "--method", help="majority|keyword|tfidf"),
) -> None:
    """Train intent classifier baseline."""
    from hiver_agent.classify.predict import IntentClassifier
    from hiver_agent.data.io import load_jsonl
    from hiver_agent.data.threads import build_threads

    threads = build_threads(load_jsonl(input_path))
    texts, labels = [], []
    for t in threads:
        if t.customer_text and t.intent:
            texts.append(t.customer_text)
            labels.append(t.intent)
    if not texts:
        raise typer.Exit("No labelled customer texts found in sample.")
    clf = IntentClassifier(method=method)  # type: ignore[arg-type]
    clf.fit(texts, labels)
    if method == "tfidf":
        clf.save(model_path)
        console.print(f"Trained {method} on {len(texts)} examples → {model_path}")
    else:
        console.print(f"Fitted {method} on {len(texts)} examples (stateless save skipped)")


@app.command("classify")
def classify(
    text: str = typer.Option(..., "--text", "-t"),
    model_path: Path = typer.Option(DEFAULT_MODEL, "--model", "-m"),
    method: str = typer.Option("tfidf", "--method"),
) -> None:
    """Classify a single customer message."""
    from hiver_agent.classify.predict import IntentClassifier

    if method == "tfidf" and model_path.exists():
        clf = IntentClassifier.load(model_path, method="tfidf")
    else:
        # fit keyword/majority on the fly from sample for demo
        from hiver_agent.data.io import load_jsonl
        from hiver_agent.data.threads import build_threads

        threads = build_threads(load_jsonl(DEFAULT_SAMPLE))
        texts = [t.customer_text for t in threads if t.customer_text and t.intent]
        labels = [t.intent for t in threads if t.customer_text and t.intent]
        clf = IntentClassifier(method=method)  # type: ignore[arg-type]
        clf.fit(texts, labels)
    pred = clf.predict_one(text)
    console.print_json(pred.model_dump_json())


@app.command("draft")
def draft(
    text: str = typer.Option(..., "--text", "-t"),
    intent: str = typer.Option("how_to", "--intent"),
    dry_run: bool = typer.Option(True, "--dry-run/--live"),
    sample: Path = typer.Option(DEFAULT_SAMPLE, "--sample"),
) -> None:
    """Retrieve historical resolutions and draft a reply."""
    from hiver_agent.data.io import load_jsonl
    from hiver_agent.data.threads import build_threads
    from hiver_agent.llm.client import get_llm_client
    from hiver_agent.retrieve.draft import ReplyDrafter
    from hiver_agent.retrieve.index import RetrievalIndex

    threads = build_threads(load_jsonl(sample))
    index = RetrievalIndex().build(threads)
    drafter = ReplyDrafter(index, get_llm_client(dry_run=dry_run))
    result = drafter.draft(text, intent)
    console.print_json(result.model_dump_json())


@app.command("escalate")
def escalate_cmd(
    text: str = typer.Option(..., "--text", "-t"),
    intent: str = typer.Option("how_to", "--intent"),
    confidence: float = typer.Option(0.7, "--confidence"),
) -> None:
    """Decide auto-handle vs escalate."""
    from hiver_agent.escalate.rules import decide_escalation
    from hiver_agent.schemas import IntentPrediction

    pred = IntentPrediction(intent=intent, confidence=confidence, method="cli")
    decision = decide_escalation(text, pred)
    console.print_json(decision.model_dump_json())


@app.command("evaluate")
def evaluate(
    golden: Path = typer.Option(DEFAULT_GOLDEN, "--golden", "-g"),
    sample: Path = typer.Option(DEFAULT_SAMPLE, "--sample"),
    model_path: Path = typer.Option(DEFAULT_MODEL, "--model", "-m"),
    dry_run: bool = typer.Option(True, "--dry-run/--live"),
    out: Path = typer.Option(ROOT / "artifacts" / "eval_report.json", "--out"),
    judge_sample: int = typer.Option(20, "--judge-sample"),
) -> None:
    """Run automated metrics + LLM-as-judge on golden set."""
    from hiver_agent.classify.predict import IntentClassifier
    from hiver_agent.data.io import load_jsonl, save_jsonl
    from hiver_agent.data.threads import build_threads
    from hiver_agent.escalate.rules import decide_escalation
    from hiver_agent.eval.harness import evaluate_all
    from hiver_agent.llm.client import get_llm_client
    from hiver_agent.retrieve.draft import ReplyDrafter
    from hiver_agent.retrieve.index import RetrievalIndex
    from hiver_agent.schemas import GoldenExample

    gold = [GoldenExample.model_validate(r) for r in load_jsonl(golden)]
    threads = build_threads(load_jsonl(sample))
    train_texts = [t.customer_text for t in threads if t.customer_text and t.intent]
    train_labels = [t.intent for t in threads if t.customer_text and t.intent]

    # baselines
    results = {}
    for method in ("majority", "keyword", "tfidf"):
        clf = IntentClassifier(method=method)  # type: ignore[arg-type]
        clf.fit(train_texts, train_labels)
        if method == "tfidf":
            clf.save(model_path)
        preds = clf.predict([g.customer_text for g in gold])
        from hiver_agent.eval.harness import intent_metrics

        results[method] = intent_metrics(
            [g.intent for g in gold], [p.intent for p in preds]
        )

    # primary model path for escalation + drafts
    clf = IntentClassifier.load(model_path, method="tfidf")
    llm = get_llm_client(dry_run=dry_run)
    index = RetrievalIndex().build(threads)
    drafter = ReplyDrafter(index, llm)

    intent_preds = []
    esc_preds = []
    drafts = []
    for g in gold:
        ip = clf.predict_one(g.customer_text)
        intent_preds.append(ip)
        esc = decide_escalation(g.customer_text, ip)
        esc_preds.append(esc.action == "escalate")
        drafts.append(drafter.draft(g.customer_text, ip.intent).text)

    full = evaluate_all(
        gold, intent_preds, esc_preds, drafts, llm, judge_sample_size=judge_sample
    )
    full["baselines"] = {
        k: {kk: vv for kk, vv in v.items() if kk != "report"} for k, v in results.items()
    }
    full["baselines_reports"] = {k: v["report"] for k, v in results.items()}

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(full, indent=2), encoding="utf-8")
    console.print(f"[green]Eval written → {out}[/green]")
    table = Table(title="Intent baselines (accuracy / macro-F1)")
    table.add_column("method")
    table.add_column("accuracy")
    table.add_column("macro_f1")
    for method, m in full["baselines"].items():
        table.add_row(method, f"{m['accuracy']:.3f}", f"{m['macro_f1']:.3f}")
    console.print(table)
    console.print(
        f"Escalation F1={full['escalation']['f1']:.3f} | "
        f"Judge avg overall={full['reply_judge']['avg_overall']:.2f} "
        f"(dry_run={full['reply_judge']['dry_run']})"
    )


@app.command("run-pipeline")
def run_pipeline(
    text: Optional[str] = typer.Option(None, "--text", "-t"),
    input_path: Optional[Path] = typer.Option(None, "--input", "-i", help="JSONL of texts"),
    sample: Path = typer.Option(DEFAULT_SAMPLE, "--sample"),
    model_path: Path = typer.Option(DEFAULT_MODEL, "--model", "-m"),
    dry_run: bool = typer.Option(True, "--dry-run/--live"),
    limit: int = typer.Option(5, "--limit"),
    out: Path = typer.Option(ROOT / "artifacts" / "pipeline_out.jsonl", "--out"),
) -> None:
    """End-to-end classify + draft + escalate (dry-run by default)."""
    from hiver_agent.classify.predict import IntentClassifier
    from hiver_agent.data.io import load_jsonl, save_jsonl
    from hiver_agent.data.threads import build_threads
    from hiver_agent.llm.client import get_llm_client
    from hiver_agent.pipeline.run import SupportAgentPipeline
    from hiver_agent.retrieve.draft import ReplyDrafter
    from hiver_agent.retrieve.index import RetrievalIndex

    threads = build_threads(load_jsonl(sample))
    train_texts = [t.customer_text for t in threads if t.customer_text and t.intent]
    train_labels = [t.intent for t in threads if t.customer_text and t.intent]
    if model_path.exists():
        clf = IntentClassifier.load(model_path, method="tfidf")
    else:
        clf = IntentClassifier("tfidf").fit(train_texts, train_labels)
        clf.save(model_path)

    llm = get_llm_client(dry_run=dry_run)
    pipe = SupportAgentPipeline(
        clf, ReplyDrafter(RetrievalIndex().build(threads), llm)
    )

    jobs: list[tuple[str, str]] = []
    if text:
        jobs.append(("cli", text))
    elif input_path:
        for row in load_jsonl(input_path)[:limit]:
            jobs.append((str(row.get("thread_id", row.get("example_id", "x"))), row.get("customer_text") or row.get("text", "")))
    else:
        # demo: first N customer threads from sample
        for t in threads[:limit]:
            if t.customer_text:
                jobs.append((t.thread_id, t.customer_text))

    results = [pipe.run(tid, txt).model_dump() for tid, txt in jobs]
    save_jsonl(out, results)
    for r in results:
        console.rule(r["thread_id"])
        console.print(f"[bold]Intent[/bold]: {r['intent']['intent']} ({r['intent']['confidence']:.2f})")
        console.print("[bold]Action[/bold]: ", end=""); console.print(f"{r['escalation']['action']} — {r['escalation']['reason']}", markup=False)
        console.print("[bold]Draft[/bold]: ", end=""); console.print(r["draft"]["text"], markup=False)
    console.print(f"Wrote {len(results)} results → {out}")


if __name__ == "__main__":
    app()
