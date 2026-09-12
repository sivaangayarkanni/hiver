"""OpenAI-compatible chat client with dry-run / mock mode."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx


FIXTURE_REPLIES = {
    "apple_id_login": (
        "Sorry you're locked out of your Apple ID. Try iforgot.apple.com to reset "
        "your password, and make sure two-factor codes are coming through on a "
        "trusted device. If you're still stuck, we can escalate to a specialist."
    ),
    "billing_subscription": (
        "Thanks for flagging the charge. You can review subscriptions under "
        "Settings > [your name] > Subscriptions, and request a refund via "
        "reportaproblem.apple.com. If this looks unauthorized, say the word and "
        "we'll escalate with your order details."
    ),
    "device_hardware": (
        "Sorry about the hardware trouble. Check coverage at checkcoverage.apple.com "
        "and book a Genius Bar or Apple Authorized Service Provider visit. "
        "Because this may need physical service, we're flagging for escalation."
    ),
    "software_update": (
        "Updates can get stuck — connect to power and Wi‑Fi, free ~5GB storage, "
        "then try Settings > General > Software Update again. If it fails with an "
        "error code, reply with the code and we'll dig in."
    ),
    "app_store": (
        "For App Store download issues, confirm payment method, restart your device, "
        "and try again on Wi‑Fi. If a purchase is missing, check Purchased and "
        "reportaproblem.apple.com."
    ),
    "icloud_storage": (
        "When iCloud is full, backups and Photos sync pause. Manage storage under "
        "Settings > [your name] > iCloud > Manage Account Storage, or upgrade iCloud+. "
        "Delete old device backups you no longer need."
    ),
    "battery_performance": (
        "Battery drain after an update is common while indexing finishes. Check "
        "Settings > Battery for top apps, enable Low Power Mode, and review Battery "
        "Health. If capacity is very low, we can help with service options."
    ),
    "connectivity": (
        "Try toggling Airplane Mode, forgetting and re-joining the network, and "
        "resetting network settings if needed (Settings > General > Transfer or "
        "Reset iPhone > Reset > Reset Network Settings)."
    ),
    "privacy_security": (
        "If you suspect unauthorized access, change your Apple ID password now, "
        "review devices at appleid.apple.com, and enable Lost Mode via Find My. "
        "We're escalating this for priority security help."
    ),
    "how_to": (
        "Happy to help with that setup. The steps are usually under Settings for "
        "the feature you mentioned — reply with your device model and iOS version "
        "if you want more specific walkthroughs."
    ),
    "other": (
        "Thanks for reaching out. To help accurately, could you share your device "
        "model, software version, and a bit more detail? We're routing this for "
        "human review in case it's multi-issue."
    ),
}


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dry_run: bool = False,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.model = model if model is not None else os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.dry_run = dry_run or not self.api_key
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        intent_hint: Optional[str] = None,
    ) -> str:
        if self.dry_run:
            return self._mock_reply(messages, intent_hint=intent_hint)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def judge_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        if self.dry_run:
            # Deterministic mock judge: mid scores with mild variance from length
            score = 3 + (len(prompt) % 3)
            return {
                "relevance": score,
                "helpfulness": score,
                "tone": min(5, score + 1),
                "groundedness": score,
                "overall": score,
                "rationale": "dry-run mock judge (not a real LLM judgment)",
            }
        raw = self.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a strict eval judge. Reply with JSON only: "
                        '{"relevance":1-5,"helpfulness":1-5,"tone":1-5,'
                        '"groundedness":1-5,"overall":1-5,"rationale":"..."}'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        return json.loads(raw)

    def _mock_reply(
        self,
        messages: list[dict[str, str]],
        intent_hint: Optional[str] = None,
    ) -> str:
        blob = " ".join(m.get("content", "") for m in messages).lower()
        intent = intent_hint or "other"
        for name in FIXTURE_REPLIES:
            if name.replace("_", " ") in blob or name in blob:
                intent = name
                break
        base = FIXTURE_REPLIES.get(intent, FIXTURE_REPLIES["other"])
        return f"[dry-run] {base}"


def get_llm_client(dry_run: bool = False) -> LLMClient:
    return LLMClient(dry_run=dry_run)
