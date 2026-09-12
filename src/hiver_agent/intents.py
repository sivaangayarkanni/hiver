"""Canonical intent taxonomy derived from AppleSupport-style Twitter patterns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentDef:
    name: str
    description: str
    escalate_bias: float  # higher => more likely to escalate when uncertain


INTENTS: dict[str, IntentDef] = {
    "apple_id_login": IntentDef(
        "apple_id_login",
        "Apple ID sign-in, locked account, 2FA, forgot password.",
        escalate_bias=0.4,
    ),
    "billing_subscription": IntentDef(
        "billing_subscription",
        "Charges, refunds, Apple Music/iCloud+/App Store subscriptions.",
        escalate_bias=0.6,
    ),
    "device_hardware": IntentDef(
        "device_hardware",
        "Broken screen, buttons, overheating, physical damage.",
        escalate_bias=0.7,
    ),
    "software_update": IntentDef(
        "software_update",
        "iOS/macOS update failures, bugs after update, stuck updates.",
        escalate_bias=0.35,
    ),
    "app_store": IntentDef(
        "app_store",
        "Download/purchase failures, missing apps, app update issues.",
        escalate_bias=0.3,
    ),
    "icloud_storage": IntentDef(
        "icloud_storage",
        "iCloud storage full, sync, Photos/backup problems.",
        escalate_bias=0.35,
    ),
    "battery_performance": IntentDef(
        "battery_performance",
        "Battery drain, unexpected shutdowns, performance throttling.",
        escalate_bias=0.45,
    ),
    "connectivity": IntentDef(
        "connectivity",
        "Wi-Fi, Bluetooth, cellular, AirDrop, Continuity issues.",
        escalate_bias=0.3,
    ),
    "privacy_security": IntentDef(
        "privacy_security",
        "Privacy concerns, suspicious activity, Find My, lost device.",
        escalate_bias=0.85,
    ),
    "how_to": IntentDef(
        "how_to",
        "General product how-to / feature questions.",
        escalate_bias=0.15,
    ),
    "other": IntentDef(
        "other",
        "Unclear, multi-intent, or out-of-scope; prefer escalate.",
        escalate_bias=0.9,
    ),
}

INTENT_NAMES: list[str] = list(INTENTS.keys())

# Keyword cues for trivial baseline and weak supervision seed labels
INTENT_KEYWORDS: dict[str, list[str]] = {
    "apple_id_login": [
        "apple id",
        "password",
        "locked out",
        "two-factor",
        "2fa",
        "verification code",
        "sign in",
        "can't log in",
        "cant log in",
        "forgot password",
    ],
    "billing_subscription": [
        "charged",
        "refund",
        "subscription",
        "billing",
        "invoice",
        "apple music",
        "applecare",
        "payment",
        "receipt",
        "unauthorized charge",
    ],
    "device_hardware": [
        "screen cracked",
        "broken screen",
        "overheating",
        "home button",
        "power button",
        "speaker",
        "microphone",
        "camera broken",
        "dropped",
        "water damage",
    ],
    "software_update": [
        "ios update",
        "macos update",
        "update failed",
        "stuck updating",
        "software update",
        "after updating",
        "beta",
        "installing ios",
    ],
    "app_store": [
        "app store",
        "can't download",
        "cant download",
        "purchase failed",
        "app update",
        "missing purchase",
        "redeem code",
    ],
    "icloud_storage": [
        "icloud",
        "storage full",
        "backup failed",
        "photos not syncing",
        "icloud+",
        "not enough storage",
    ],
    "battery_performance": [
        "battery",
        "draining",
        "dies quickly",
        "performance",
        "slow",
        "shutdown",
        "battery health",
    ],
    "connectivity": [
        "wifi",
        "wi-fi",
        "bluetooth",
        "cellular",
        "airdrop",
        "no signal",
        "can't connect",
        "cant connect",
        "hotspot",
    ],
    "privacy_security": [
        "hacked",
        "stolen",
        "find my",
        "privacy",
        "suspicious",
        "phishing",
        "lost iphone",
        "unauthorized access",
        "security",
    ],
    "how_to": [
        "how do i",
        "how to",
        "where can i",
        "is there a way",
        "can i",
        "help me set up",
        "tutorial",
    ],
    "other": [],
}
