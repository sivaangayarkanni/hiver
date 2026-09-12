"""Evaluation harness: automated metrics + LLM-as-judge + agreement stub."""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from sklearn.metrics import accuracy_score, classification_report, f1_score

from hiver_agent.llm.client import LLMClient
from hiver_agent.schemas import GoldenExample, IntentPrediction


def intent_metrics(
    y_true: list[str],
    y_pred: list[str],
    labels: Optional[list[str]] = None,
) -> dict[str, Any]:
    labels = labels or sorted(set(y_true) | set(y_pred))
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", labels=labels, zero_division=0)),
        "weighted_f1": float(
            f1_score(y_true, y_pred, average="weighted", labels=labels, zero_division=0)
        ),
        "support": len(y_true),
        "label_counts": dict(Counter(y_true)),
        "report": classification_report(
            y_true, y_pred, labels=labels, zero_division=0, digits=3
        ),
    }


def escalation_metrics(
    y_true: list[bool],
    y_pred: list[bool],
) -> dict[str, Any]:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    tn = sum(1 for t, p in zip(y_true, y_pred) if not t and not p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "accuracy": (tp + tn) / len(y_true) if y_true else 0.0,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "support": len(y_true),
    }


def llm_judge_reply(
    llm: LLMClient,
    customer_text: str,
    draft: str,
    reference: Optional[str] = None,
) -> dict[str, Any]:
    prompt = (
        f"Customer:\n{customer_text}\n\n"
        f"Draft reply:\n{draft}\n\n"
        f"Reference (optional):\n{reference or 'N/A'}\n\n"
        "Score relevance, helpfulness, tone, groundedness, overall (1-5)."
    )
    return llm.judge_json(prompt)


def judge_human_agreement(
    judge_scores: list[float],
    human_scores: list[float],
) -> dict[str, Any]:
    """Pearson-ish correlation + exact agreement within 1 point.

    For the MVP we ship a small paired set; if human_scores empty, report N/A.
    """
    if not human_scores or len(human_scores) != len(judge_scores):
        return {
            "n": 0,
            "pearson_r": None,
            "within_1_agreement": None,
            "note": "No paired human scores provided; see docs/REPORT.md section.",
        }
    n = len(judge_scores)
    mean_j = sum(judge_scores) / n
    mean_h = sum(human_scores) / n
    num = sum((j - mean_j) * (h - mean_h) for j, h in zip(judge_scores, human_scores))
    den_j = sum((j - mean_j) ** 2 for j in judge_scores) ** 0.5
    den_h = sum((h - mean_h) ** 2 for h in human_scores) ** 0.5
    r = num / (den_j * den_h) if den_j and den_h else 0.0
    within1 = sum(1 for j, h in zip(judge_scores, human_scores) if abs(j - h) <= 1) / n
    return {
        "n": n,
        "pearson_r": r,
        "within_1_agreement": within1,
        "note": "Small-n agreement; not a powered study.",
    }


def evaluate_all(
    gold: list[GoldenExample],
    intent_preds: list[IntentPrediction],
    escalate_preds: list[bool],
    drafts: list[str],
    llm: LLMClient,
    human_judge_pairs: Optional[list[tuple[float, float]]] = None,
    judge_sample_size: int = 20,
) -> dict[str, Any]:
    y_true = [g.intent for g in gold]
    y_pred = [p.intent for p in intent_preds]
    intent = intent_metrics(y_true, y_pred)

    esc = escalation_metrics(
        [g.should_escalate for g in gold],
        escalate_preds,
    )

    # LLM judge on a sample
    sample_n = min(judge_sample_size, len(gold))
    judge_results = []
    for i in range(sample_n):
        jr = llm_judge_reply(
            llm,
            gold[i].customer_text,
            drafts[i],
            gold[i].reference_reply,
        )
        judge_results.append(jr)

    overalls = [float(j.get("overall", 0)) for j in judge_results]
    avg_overall = sum(overalls) / len(overalls) if overalls else 0.0

    if human_judge_pairs:
        hs = [h for _, h in human_judge_pairs]
        js = [j for j, _ in human_judge_pairs]
        agreement = judge_human_agreement(js, hs)
    else:
        # Built-in tiny synthetic agreement demo for dry-run docs
        agreement = judge_human_agreement(
            overalls[:5],
            [min(5, max(1, round(o))) for o in overalls[:5]],  # mock "human" = rounded judge
        )
        agreement["note"] = (
            "DRY-RUN PLACEHOLDER: human scores were rounded mock-judge values "
            "(not independent human labels). Replace with real human ratings."
        )

    return {
        "intent": intent,
        "escalation": esc,
        "reply_judge": {
            "n": sample_n,
            "avg_overall": avg_overall,
            "avg_relevance": _avg_key(judge_results, "relevance"),
            "avg_helpfulness": _avg_key(judge_results, "helpfulness"),
            "avg_tone": _avg_key(judge_results, "tone"),
            "avg_groundedness": _avg_key(judge_results, "groundedness"),
            "dry_run": llm.dry_run,
            "samples": judge_results[:5],
        },
        "judge_human_agreement": agreement,
    }


def _avg_key(rows: list[dict[str, Any]], key: str) -> float:
    vals = [float(r.get(key, 0)) for r in rows]
    return sum(vals) / len(vals) if vals else 0.0
