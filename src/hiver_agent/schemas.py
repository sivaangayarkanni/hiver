"""Pydantic models for messages, threads, predictions, and eval."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    message_id: str
    thread_id: str
    author: str
    role: Literal["customer", "agent", "system"] = "customer"
    text: str
    created_at: str
    in_reply_to: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Thread(BaseModel):
    thread_id: str
    messages: list[Message]
    customer_text: str = ""
    resolution_text: str = ""
    intent: Optional[str] = None
    labels: dict[str, Any] = Field(default_factory=dict)


class IntentPrediction(BaseModel):
    intent: str
    confidence: float
    method: str
    scores: dict[str, float] = Field(default_factory=dict)


class DraftReply(BaseModel):
    text: str
    sources: list[str] = Field(default_factory=list)
    method: str = "retrieval_llm"
    dry_run: bool = False


class EscalationDecision(BaseModel):
    action: Literal["auto_handle", "escalate"]
    reason: str
    confidence: float
    rules_fired: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    thread_id: str
    customer_text: str
    intent: IntentPrediction
    draft: DraftReply
    escalation: EscalationDecision


class GoldenExample(BaseModel):
    example_id: str
    thread_id: str
    customer_text: str
    intent: str
    should_escalate: bool
    escalate_reason: Optional[str] = None
    reference_reply: Optional[str] = None
    source: Literal["synthetic_seed", "human_labelled", "pattern_constructed"] = (
        "pattern_constructed"
    )
    notes: str = ""
