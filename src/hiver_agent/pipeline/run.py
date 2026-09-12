"""End-to-end classify → retrieve/draft → escalate pipeline."""

from __future__ import annotations

from hiver_agent.classify.predict import IntentClassifier
from hiver_agent.escalate.rules import decide_escalation
from hiver_agent.retrieve.draft import ReplyDrafter
from hiver_agent.schemas import PipelineResult


class SupportAgentPipeline:
    def __init__(
        self,
        classifier: IntentClassifier,
        drafter: ReplyDrafter,
        confidence_threshold: float = 0.28,
    ) -> None:
        self.classifier = classifier
        self.drafter = drafter
        self.confidence_threshold = confidence_threshold

    def run(self, thread_id: str, customer_text: str) -> PipelineResult:
        intent = self.classifier.predict_one(customer_text)
        draft = self.drafter.draft(customer_text, intent.intent)
        esc = decide_escalation(
            customer_text,
            intent,
            confidence_threshold=self.confidence_threshold,
        )
        return PipelineResult(
            thread_id=thread_id,
            customer_text=customer_text,
            intent=intent,
            draft=draft,
            escalation=esc,
        )
