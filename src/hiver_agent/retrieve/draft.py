"""Draft customer replies grounded in retrieved historical resolutions."""

from __future__ import annotations

from hiver_agent.llm.client import LLMClient
from hiver_agent.retrieve.index import RetrievalIndex
from hiver_agent.schemas import DraftReply


SYSTEM_PROMPT = (
    "You are a helpful Apple Support social-media agent. "
    "Write a short, empathetic Twitter/X reply (max ~280–400 chars when possible). "
    "Ground advice in the provided historical resolutions. "
    "Do not invent order numbers, warranties, or account-specific facts. "
    "If unsafe/legal/security-sensitive, recommend official channels."
)


class ReplyDrafter:
    def __init__(self, index: RetrievalIndex, llm: LLMClient) -> None:
        self.index = index
        self.llm = llm

    def draft(
        self,
        customer_text: str,
        intent: str,
        k: int = 3,
    ) -> DraftReply:
        docs = self.index.query(customer_text, k=k, intent=intent)
        sources = [d.thread_id for d in docs]
        context = "\n\n".join(
            f"[source {d.thread_id} | score={d.score:.3f}]\n{d.text}" for d in docs
        ) or "(no historical resolutions retrieved)"

        user_prompt = (
            f"Intent: {intent}\n\n"
            f"Customer message:\n{customer_text}\n\n"
            f"Historical resolutions:\n{context}\n\n"
            "Draft the reply only."
        )
        text = self.llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            intent_hint=intent,
        )
        return DraftReply(
            text=text,
            sources=sources,
            method="retrieval_llm" if not self.llm.dry_run else "retrieval_mock",
            dry_run=self.llm.dry_run,
        )
