"""Build support threads from flat message JSONL."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from hiver_agent.schemas import Message, Thread


def _as_message(raw: dict[str, Any]) -> Message:
    role = raw.get("role")
    if role not in ("customer", "agent", "system"):
        author = (raw.get("author") or "").lower()
        if "applesupport" in author or author.startswith("agent"):
            role = "agent"
        else:
            role = "customer"
    return Message(
        message_id=str(raw["message_id"]),
        thread_id=str(raw["thread_id"]),
        author=str(raw.get("author", "unknown")),
        role=role,
        text=str(raw.get("text", "")).strip(),
        created_at=str(raw.get("created_at", "")),
        in_reply_to=raw.get("in_reply_to"),
        meta={k: v for k, v in raw.items() if k not in {
            "message_id", "thread_id", "author", "role", "text",
            "created_at", "in_reply_to",
        }},
    )


def customer_message_text(messages: list[Message]) -> str:
    parts = [m.text for m in messages if m.role == "customer" and m.text]
    return "\n".join(parts).strip()


def resolution_text(messages: list[Message]) -> str:
    """Prefer last agent reply as historical resolution grounding."""
    agent_msgs = [m.text for m in messages if m.role == "agent" and m.text]
    if not agent_msgs:
        return ""
    return agent_msgs[-1].strip()


def build_threads(raw_messages: list[dict[str, Any]]) -> list[Thread]:
    by_thread: dict[str, list[Message]] = defaultdict(list)
    for raw in raw_messages:
        msg = _as_message(raw)
        by_thread[msg.thread_id].append(msg)

    threads: list[Thread] = []
    for thread_id, msgs in sorted(by_thread.items()):
        msgs = sorted(msgs, key=lambda m: (m.created_at, m.message_id))
        intent = None
        labels: dict[str, Any] = {}
        for m in msgs:
            if "intent" in m.meta and m.meta["intent"]:
                intent = m.meta["intent"]
            if "labels" in m.meta and isinstance(m.meta["labels"], dict):
                labels.update(m.meta["labels"])
        threads.append(
            Thread(
                thread_id=thread_id,
                messages=msgs,
                customer_text=customer_message_text(msgs),
                resolution_text=resolution_text(msgs),
                intent=intent,
                labels=labels,
            )
        )
    return threads
