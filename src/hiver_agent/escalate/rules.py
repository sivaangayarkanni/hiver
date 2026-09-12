"""Rule-based escalation with confidence threshold."""

from __future__ import annotations

import re

from hiver_agent.intents import INTENTS
from hiver_agent.schemas import EscalationDecision, IntentPrediction

SECURITY_PATTERNS = [
    r"\bhack(ed|ing)?\b",
    r"\bstolen\b",
    r"\bunauthorized\b",
    r"\bphishing\b",
    r"\blost (my )?(iphone|ipad|mac|device)\b",
    r"\bfraud\b",
]
HARDWARE_SERVICE = [
    r"\bcracked\b",
    r"\bwater damage\b",
    r"\bwon't turn on\b",
    r"\bwont turn on\b",
    r"\bgenius bar\b",
]
BILLING_HIGH_RISK = [
    r"\bunauthorized charge\b",
    r"\brefund\b",
    r"\blawyer\b",
    r"\bbetter business bureau\b",
    r"\bbbb\b",
]
TOXIC_OR_LEGAL = [
    r"\bsue\b",
    r"\blegal action\b",
    r"\bkill myself\b",
    r"\bthreat\b",
]


def _any_match(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return p
    return None


def decide_escalation(
    customer_text: str,
    intent_pred: IntentPrediction,
    *,
    confidence_threshold: float = 0.28,
) -> EscalationDecision:
    """Decide auto-handle vs escalate with an explicit reason."""
    text = customer_text or ""
    rules: list[str] = []
    reasons: list[str] = []

    intent = intent_pred.intent
    conf = float(intent_pred.confidence)
    bias = INTENTS.get(intent).escalate_bias if intent in INTENTS else 0.5

    # Hard rules
    if m := _any_match(SECURITY_PATTERNS, text):
        rules.append(f"security_pattern:{m}")
        reasons.append("Security / account-takeover language detected")
    if m := _any_match(TOXIC_OR_LEGAL, text):
        rules.append(f"legal_or_crisis:{m}")
        reasons.append("Legal or crisis language — human required")
    if intent == "privacy_security":
        rules.append("intent:privacy_security")
        reasons.append("Privacy/security intents always escalate")
    if intent == "device_hardware" and _any_match(HARDWARE_SERVICE, text):
        rules.append("hardware_service_needed")
        reasons.append("Likely needs physical service / Genius Bar")
    if intent == "billing_subscription" and _any_match(BILLING_HIGH_RISK, text):
        rules.append("billing_high_risk")
        reasons.append("High-risk billing / refund dispute")
    if intent == "other":
        rules.append("intent:other")
        reasons.append("Unclear/other intent — prefer human")

    # Confidence gate (adjusted by intent escalate bias)
    adjusted_threshold = max(0.25, confidence_threshold * (0.7 + 0.6 * bias))
    if conf < adjusted_threshold:
        rules.append(f"low_confidence:{conf:.2f}<{adjusted_threshold:.2f}")
        reasons.append(
            f"Classifier confidence {conf:.2f} below threshold {adjusted_threshold:.2f}"
        )

    if rules:
        return EscalationDecision(
            action="escalate",
            reason="; ".join(reasons) if reasons else "Rule triggered",
            confidence=conf,
            rules_fired=rules,
        )

    return EscalationDecision(
        action="auto_handle",
        reason=(
            f"Intent '{intent}' with confidence {conf:.2f}; "
            "no hard escalation rules fired"
        ),
        confidence=conf,
        rules_fired=[],
    )
