#!/usr/bin/env python3
"""Generate synthetic AppleSupport-style threads + golden eval set.

Constructed from public Twitter support *patterns* (short customer complaint +
agent troubleshooting reply). NOT scraped from the Kaggle Customer Support
on Twitter dataset. Clearly marked as pattern_constructed / synthetic_seed.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_OUT = ROOT / "data" / "sample" / "messages.jsonl"
GOLDEN_OUT = ROOT / "data" / "golden" / "golden.jsonl"
FIXTURES = ROOT / "data" / "fixtures"

random.seed(42)

TEMPLATES: dict[str, list[dict]] = {
    "apple_id_login": [
        {
            "customer": "I can't sign in to my Apple ID — keeps saying locked for security reasons. Need help ASAP @{handle}",
            "agent": "We're sorry you're locked out. Please visit iforgot.apple.com to reset your password and unlock your account. If two-factor codes aren't arriving, check a trusted device under appleid.apple.com. Let us know how it goes.",
            "escalate": False,
        },
        {
            "customer": "Forgot my Apple ID password and the recovery email is old. Any way to get back in?",
            "agent": "You can start at iforgot.apple.com and follow account recovery. It can take a few days if trusted devices aren't available. We're here if you get stuck on a specific step.",
            "escalate": False,
        },
        {
            "customer": "Someone changed my Apple ID password overnight. I think I've been hacked!!",
            "agent": "Please secure your account now: change the password from a trusted device if you can, review devices at appleid.apple.com, and sign out of unknown sessions. We're escalating this for priority security assistance.",
            "escalate": True,
            "escalate_reason": "Suspected account takeover",
        },
        {
            "customer": "2FA code never shows up on my iPhone. Can't log into iCloud on my Mac.",
            "agent": "Make sure the iPhone is online and that it's listed as a trusted device. Try Resend Code, or use a trusted phone number SMS. If neither works, account recovery via iforgot.apple.com is the path.",
            "escalate": False,
        },
    ],
    "billing_subscription": [
        {
            "customer": "I was charged twice for Apple Music this month. Please refund the duplicate!",
            "agent": "We're sorry about the duplicate charge. Review subscriptions in Settings > [your name] > Subscriptions and request a refund at reportaproblem.apple.com. Reply with the last 4 of the charge date if you need us to look further.",
            "escalate": True,
            "escalate_reason": "Refund request",
        },
        {
            "customer": "How do I cancel my iCloud+ subscription?",
            "agent": "On iPhone: Settings > [your name] > Subscriptions > iCloud+ > Cancel Subscription. Changes apply at the end of the billing period. Storage will revert to free 5GB after that.",
            "escalate": False,
        },
        {
            "customer": "Unauthorized charge from the App Store for $49.99. I didn't buy anything!",
            "agent": "Please change your Apple ID password and review Family Sharing purchases. Request a refund via reportaproblem.apple.com and we're escalating billing disputes like this to a specialist.",
            "escalate": True,
            "escalate_reason": "Unauthorized charge",
        },
        {
            "customer": "AppleCare+ auto-renewed and I don't want it. Can I get a refund?",
            "agent": "You can manage AppleCare in Settings or checkcoverage.apple.com. Refund eligibility depends on timing — start at reportaproblem.apple.com or chat with Apple Support billing.",
            "escalate": True,
            "escalate_reason": "Refund / AppleCare billing",
        },
    ],
    "device_hardware": [
        {
            "customer": "Dropped my iPhone and the screen is cracked. Touch still works though.",
            "agent": "Sorry about the drop. Check your coverage at checkcoverage.apple.com and schedule a Genius Bar or Apple Authorized Service Provider visit. Screen service pricing depends on AppleCare+ status.",
            "escalate": True,
            "escalate_reason": "Physical service needed",
        },
        {
            "customer": "iPhone overheating and shutting down while charging. Scary.",
            "agent": "Remove any thick case while charging, try a different cable/adapter, and see if it happens only while charging. If it continues, run diagnostics at an Apple Store — we're flagging for hardware review.",
            "escalate": True,
            "escalate_reason": "Potential hardware fault",
        },
        {
            "customer": "Volume buttons on my iPad stopped working after I dropped it.",
            "agent": "That often needs hardware service. Check coverage and book a visit. Avoid third-party repairs if you want to keep existing coverage options intact.",
            "escalate": True,
            "escalate_reason": "Hardware service",
        },
        {
            "customer": "MacBook fan is extremely loud even when idle. Is this normal?",
            "agent": "Some fan noise under load is normal, but constant high RPM at idle can mean dust, background processes, or a hardware issue. Check Activity Monitor for CPU hogs; if idle and loud, book diagnostics.",
            "escalate": False,
        },
    ],
    "software_update": [
        {
            "customer": "iOS update has been stuck on 'preparing' for 3 hours. Help?",
            "agent": "Keep the iPhone on power and Wi-Fi with enough free storage. Restart and retry. If still stuck, you can update via Finder/iTunes on a computer. Reply with any error code you see.",
            "escalate": False,
        },
        {
            "customer": "After updating to the latest iOS my apps keep crashing.",
            "agent": "Sorry for the hassle. Update apps in the App Store, restart your iPhone, and free some storage. If a specific app crashes, reinstall it. Still broken? Share the app name and we'll dig in.",
            "escalate": False,
        },
        {
            "customer": "macOS update failed with error 102. What now?",
            "agent": "Error 102 is often network/CDN related. Try a different network, free disk space, and download again from System Settings > General > Software Update. An Apple Store can reinstall if it keeps failing.",
            "escalate": False,
        },
        {
            "customer": "Should I install the iOS public beta on my only phone?",
            "agent": "Betas can be buggy — we recommend a secondary device and a fresh backup first. You can enroll via beta.apple.com and leave the beta later by installing the latest public release.",
            "escalate": False,
        },
    ],
    "app_store": [
        {
            "customer": "Can't download apps from the App Store — spins forever.",
            "agent": "Check your payment method, switch to Wi-Fi, restart your device, and try again. If it persists, sign out of the App Store and back in under Media & Purchases.",
            "escalate": False,
        },
        {
            "customer": "I paid for an app but it's not in Purchased. Missing purchase!",
            "agent": "Confirm you're signed into the same Apple ID used for the purchase. Check Purchased in the App Store profile. Still missing? Use reportaproblem.apple.com with the order.",
            "escalate": False,
        },
        {
            "customer": "Redeem code for App Store says invalid. It's brand new.",
            "agent": "Codes can be region-locked or already redeemed. Double-check for typos and that the storefront matches the code region. If it still fails, share a redacted photo of the card via support chat.",
            "escalate": False,
        },
        {
            "customer": "App updates fail with 'unable to download' on iPad.",
            "agent": "Free some storage, pause other downloads, and retry on Wi-Fi. Resetting all settings can help as a last step (doesn't erase content).",
            "escalate": False,
        },
    ],
    "icloud_storage": [
        {
            "customer": "iCloud storage full — can't backup my iPhone. Options?",
            "agent": "Go to Settings > [your name] > iCloud > Manage Account Storage. Delete old backups and large Photos. Or upgrade iCloud+. Backups resume once enough space is free.",
            "escalate": False,
        },
        {
            "customer": "Photos not syncing to iCloud even though I have space.",
            "agent": "Confirm iCloud Photos is on, the device is charging on Wi-Fi, and Low Data Mode is off. Open Photos and pull to refresh; large libraries can take time.",
            "escalate": False,
        },
        {
            "customer": "iCloud backup failed overnight again. Error says not enough storage.",
            "agent": "Your plan may be full — manage storage or upgrade. You can also exclude large apps from the backup under iCloud Backup > [device].",
            "escalate": False,
        },
        {
            "customer": "How do I download all my iCloud Drive files before canceling?",
            "agent": "On a Mac signed into iCloud, open iCloud Drive in Finder and copy files locally. On Windows use iCloud for Windows. Ensure downloads finish before canceling the plan.",
            "escalate": False,
        },
    ],
    "battery_performance": [
        {
            "customer": "Battery draining like crazy after the update. 100% to 20% in 2 hours!",
            "agent": "Post-update indexing can spike drain for a day or two. Check Settings > Battery for top consumers, enable Low Power Mode, and review Battery Health. If an app dominates, update or offload it.",
            "escalate": False,
        },
        {
            "customer": "iPhone dies at 30% suddenly. Battery health shows 74%.",
            "agent": "At that health level, unexpected shutdowns are more common. Consider a battery service — checkcoverage.apple.com for pricing and AppleCare status.",
            "escalate": False,
        },
        {
            "customer": "My iPhone got really slow. Is it throttling because of battery?",
            "agent": "iOS may manage performance for aging batteries. Check Settings > Battery > Battery Health & Charging. A battery replacement often restores performance if peak capacity is low.",
            "escalate": False,
        },
        {
            "customer": "Apple Watch battery only lasts half a day now.",
            "agent": "Check watchOS is updated, reduce Always On Display / wake on wrist raise, and look at which apps use background refresh. If capacity is low, Apple can replace the battery.",
            "escalate": False,
        },
    ],
    "connectivity": [
        {
            "customer": "iPhone won't connect to Wi-Fi at home but other devices work fine.",
            "agent": "Forget the network, restart the router and iPhone, then rejoin. If needed: Settings > General > Transfer or Reset iPhone > Reset > Reset Network Settings.",
            "escalate": False,
        },
        {
            "customer": "Bluetooth keeps dropping with my AirPods.",
            "agent": "Put AirPods in the case, reset them (button on back until light flashes), forget the device on iPhone, then re-pair. Also update iOS/firmware.",
            "escalate": False,
        },
        {
            "customer": "AirDrop not showing my friend's iPhone nearby.",
            "agent": "Both need Wi-Fi + Bluetooth on, AirDrop set to Everyone for 10 Minutes (or Contacts Only with the person in Contacts), and devices close together. Airplane Mode toggles can help.",
            "escalate": False,
        },
        {
            "customer": "No cellular signal after traveling. SIM is fine I think.",
            "agent": "Toggle Airplane Mode, check carrier settings updates, and confirm the SIM/eSIM line is active with your carrier. Reset Network Settings if it persists.",
            "escalate": False,
        },
    ],
    "privacy_security": [
        {
            "customer": "My iPhone was stolen. Can you track it? Find My was on!",
            "agent": "Mark as Lost in Find My (iCloud.com/find) immediately, change your Apple ID password, and report to local authorities. Activation Lock stays on with your Apple ID. Escalating for stolen-device guidance.",
            "escalate": True,
            "escalate_reason": "Stolen device",
        },
        {
            "customer": "Got a phishing email that looks like Apple asking for my password.",
            "agent": "Don't click or sign in via that email. Apple won't ask for your password by email. Forward suspicious messages to reportphishing@apple.com and change your password if you interacted.",
            "escalate": True,
            "escalate_reason": "Phishing / security",
        },
        {
            "customer": "Strange devices showing up on my Apple ID. Worried about privacy.",
            "agent": "Remove unknown devices at appleid.apple.com, change your password, and enable two-factor if it's not on. We're escalating account security cases like this.",
            "escalate": True,
            "escalate_reason": "Unknown devices",
        },
        {
            "customer": "How do I see which apps have access to my location and mic?",
            "agent": "Settings > Privacy & Security — review Location Services, Microphone, Camera, and Tracking. You can switch access per app anytime.",
            "escalate": False,
        },
    ],
    "how_to": [
        {
            "customer": "How do I set up Focus modes so work chats don't buzz at night?",
            "agent": "Settings > Focus > add a Focus (e.g. Sleep/Work). Choose allowed people/apps and a schedule. You can also link it to Lock Screen filters.",
            "escalate": False,
        },
        {
            "customer": "Where can I find screenshots on my Mac?",
            "agent": "By default they're saved to Desktop. Hold Control when capturing to copy to clipboard instead, or change the location via Screenshot app Options.",
            "escalate": False,
        },
        {
            "customer": "How to share my Wi-Fi password from iPhone to a friend nearby?",
            "agent": "Both need Bluetooth/Wi-Fi on and be signed into iCloud with the friend in Contacts. When they join your network, you should get a prompt to share the password.",
            "escalate": False,
        },
        {
            "customer": "Is there a way to schedule texts to send later on iPhone?",
            "agent": "In Messages you can tap + > More > Send Later (iOS featuring scheduling) or use Shortcuts. Availability depends on your iOS version — check Messages compose tools.",
            "escalate": False,
        },
    ],
    "other": [
        {
            "customer": "This is ridiculous. Your products and support are the worst. Fix everything.",
            "agent": "We're sorry you're frustrated. If you share the device model and the specific issue, we can help or connect you with the right team.",
            "escalate": True,
            "escalate_reason": "Unclear / venting — needs human",
        },
        {
            "customer": "Need help with something but not sure how to explain. DM?",
            "agent": "We can start here — tell us the product and what you expected vs what happened. For account-sensitive details, we'll move you to a secure channel.",
            "escalate": True,
            "escalate_reason": "Insufficient detail",
        },
        {
            "customer": "My issue spans billing AND my phone won't turn on after a drop. Help.",
            "agent": "Multi-issue cases are best with a specialist. For power issues try a force restart; for billing use reportaproblem.apple.com. We're escalating the combined case.",
            "escalate": True,
            "escalate_reason": "Multi-intent",
        },
        {
            "customer": "Can you comment on rival brand rumors for me?",
            "agent": "We're here for Apple product support rather than rumor discussion — happy to help with any Apple device or service question though!",
            "escalate": True,
            "escalate_reason": "Out of scope",
        },
    ],
}

HANDLES = ["AppleSupport"]
DEVICES = ["iPhone 13", "iPhone 14", "iPhone 15", "iPad Pro", "MacBook Air", "Apple Watch"]
IOS = ["iOS 17", "iOS 18", "iPadOS 17", "macOS Sonoma", "watchOS 10"]


def vary(text: str, rng: random.Random) -> str:
    """Light lexical variation so examples aren't exact duplicates."""
    swaps = [
        ("Help?", "Any advice?"),
        ("Please", "Pls"),
        ("I can't", "I cannot"),
        ("Can't", "Cant"),
        ("thanks", "thx"),
        ("iPhone", rng.choice(["iPhone", "my iPhone", "this iPhone"])),
    ]
    out = text
    if rng.random() < 0.4:
        for a, b in swaps:
            if a in out and rng.random() < 0.5:
                out = out.replace(a, b, 1)
    if rng.random() < 0.3:
        out = out + " " + rng.choice(
            [
                f"Device: {rng.choice(DEVICES)}.",
                f"On {rng.choice(IOS)}.",
                "Please help.",
                "",
            ]
        )
    return out.strip()


def main() -> None:
    rng = random.Random(42)
    messages = []
    golden = []
    thread_idx = 0
    base_time = datetime(2024, 6, 1, 12, 0, 0)

    # Build ~100 threads from templates with variation
    intents = list(TEMPLATES.keys())
    target_threads = 110
    while thread_idx < target_threads:
        intent = intents[thread_idx % len(intents)]
        tmpl = rng.choice(TEMPLATES[intent])
        thread_idx += 1
        tid = f"T{thread_idx:04d}"
        t0 = base_time + timedelta(hours=thread_idx * 3, minutes=rng.randint(0, 50))
        cust_text = vary(tmpl["customer"].replace("{handle}", "AppleSupport"), rng)
        agent_text = tmpl["agent"]

        cust_id = f"M{thread_idx:04d}C"
        agent_id = f"M{thread_idx:04d}A"
        messages.append(
            {
                "message_id": cust_id,
                "thread_id": tid,
                "author": f"customer_{thread_idx}",
                "role": "customer",
                "text": cust_text,
                "created_at": t0.isoformat() + "Z",
                "in_reply_to": None,
                "intent": intent,
            }
        )
        # occasional follow-up customer ping
        if rng.random() < 0.25:
            t1 = t0 + timedelta(minutes=20)
            follow = rng.choice(
                [
                    "Still waiting on this…",
                    "Any update?",
                    "Tried that, still broken.",
                    "Thanks — that helped partially.",
                ]
            )
            follow_id = f"M{thread_idx:04d}C2"
            messages.append(
                {
                    "message_id": follow_id,
                    "thread_id": tid,
                    "author": f"customer_{thread_idx}",
                    "role": "customer",
                    "text": follow,
                    "created_at": t1.isoformat() + "Z",
                    "in_reply_to": cust_id,
                    "intent": intent,
                }
            )
            messages.append(
                {
                    "message_id": agent_id,
                    "thread_id": tid,
                    "author": "AppleSupport",
                    "role": "agent",
                    "text": agent_text,
                    "created_at": (t1 + timedelta(minutes=8)).isoformat() + "Z",
                    "in_reply_to": follow_id,
                    "intent": intent,
                }
            )
        else:
            messages.append(
                {
                    "message_id": agent_id,
                    "thread_id": tid,
                    "author": "AppleSupport",
                    "role": "agent",
                    "text": agent_text,
                    "created_at": (t0 + timedelta(minutes=12)).isoformat() + "Z",
                    "in_reply_to": cust_id,
                    "intent": intent,
                }
            )

    # Golden set: 180 labelled examples (mix of thread customers + paraphrases)
    g_idx = 0
    # First: one golden per thread from customer text
    by_thread = {}
    for m in messages:
        if m["role"] == "customer" and m["thread_id"] not in by_thread:
            by_thread[m["thread_id"]] = m

    for tid, m in by_thread.items():
        intent = m["intent"]
        # find template escalate flag approximately
        esc = intent in ("privacy_security", "other") or "hack" in m["text"].lower() or "stolen" in m["text"].lower()
        # refine using template match
        for tmpl in TEMPLATES[intent]:
            # loose: if shared keywords
            if tmpl.get("escalate"):
                key = tmpl["customer"][:40].split()[0].lower()
                if key.lower() in m["text"].lower() or any(
                    w in m["text"].lower()
                    for w in ["refund", "unauthorized", "stolen", "hacked", "cracked", "phishing"]
                ):
                    esc = True
                    break
        # hardware cracked etc
        if intent == "device_hardware" and any(
            w in m["text"].lower() for w in ["cracked", "overheating", "dropped", "volume buttons"]
        ):
            esc = True
        if intent == "billing_subscription" and any(
            w in m["text"].lower() for w in ["refund", "unauthorized", "charged twice", "auto-renewed"]
        ):
            esc = True

        g_idx += 1
        # reference = agent reply in thread
        agent = next(
            (x for x in messages if x["thread_id"] == tid and x["role"] == "agent"),
            None,
        )
        golden.append(
            {
                "example_id": f"G{g_idx:04d}",
                "thread_id": tid,
                "customer_text": m["text"],
                "intent": intent,
                "should_escalate": bool(esc),
                "escalate_reason": "pattern rule" if esc else None,
                "reference_reply": agent["text"] if agent else None,
                "source": "pattern_constructed",
                "notes": "Constructed from AppleSupport-style public Twitter support patterns; not scraped Kaggle rows.",
            }
        )

    # Extra paraphrased golden examples to reach >=150 (target 200)
    paraphrases = {
        "apple_id_login": [
            ("Locked out of Apple ID after too many password tries.", False),
            ("Reset password link in email expired — still can't log in.", False),
            ("I think my Apple ID was hacked, password changed without me.", True),
        ],
        "billing_subscription": [
            ("Please refund an App Store purchase I didn't authorize.", True),
            ("How do I turn off Apple Music auto renew?", False),
            ("Family member bought something on my card without asking.", True),
        ],
        "device_hardware": [
            ("Screen has green lines after I dropped my phone.", True),
            ("iPhone won't turn on after water splash.", True),
            ("Trackpad on MacBook clicking weirdly.", False),
        ],
        "software_update": [
            ("Software update verification failed every time.", False),
            ("Phone bricked itself mid-iOS install — apple logo forever.", True),
            ("Is it safe to update to the newest iOS today?", False),
        ],
        "app_store": [
            ("App Store asks for payment even for free apps.", False),
            ("Purchase failed but money was held on my card.", True),
            ("Can't update Instagram — error looping.", False),
        ],
        "icloud_storage": [
            ("Need to free iCloud space without deleting photos forever.", False),
            ("Messages in iCloud not syncing across devices.", False),
            ("Backup is 40GB and I only have 50GB plan — tips?", False),
        ],
        "battery_performance": [
            ("Battery health 78% — should I replace it?", False),
            ("Phone hot and draining while idle overnight.", False),
            ("Shutdowns at 40% battery after latest update.", False),
        ],
        "connectivity": [
            ("Wi-Fi works then drops every 10 minutes.", False),
            ("CarPlay disconnects randomly over USB.", False),
            ("Personal Hotspot not visible to laptop.", False),
        ],
        "privacy_security": [
            ("Lost iPhone in taxi, Find My shows offline.", True),
            ("Suspicious Apple login alert from another country.", True),
            ("How to turn off personalized ads?", False),
        ],
        "how_to": [
            ("How do I use Live Voicemail on iPhone?", False),
            ("Can I mirror iPhone to a non-Apple TV?", False),
            ("Steps to create a Child Account in Family Sharing?", False),
        ],
        "other": [
            ("Not sure what category this is — phone acts weird sometimes.", True),
            ("I want to complain to corporate about wait times.", True),
            ("Multiple issues: Wi-Fi and also a weird charge.", True),
        ],
    }

    while g_idx < 200:
        intent = rng.choice(intents)
        text, esc = rng.choice(paraphrases[intent])
        text = vary(text, rng)
        g_idx += 1
        # synthetic reference from first template agent
        ref = TEMPLATES[intent][0]["agent"]
        golden.append(
            {
                "example_id": f"G{g_idx:04d}",
                "thread_id": f"SYN{g_idx:04d}",
                "customer_text": text,
                "intent": intent,
                "should_escalate": bool(esc),
                "escalate_reason": "labelled escalate" if esc else None,
                "reference_reply": ref,
                "source": "synthetic_seed",
                "notes": "High-quality synthetic seed for golden set; see LABELING.md.",
            }
        )

    SAMPLE_OUT.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_OUT.parent.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    with SAMPLE_OUT.open("w", encoding="utf-8") as f:
        for row in messages:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with GOLDEN_OUT.open("w", encoding="utf-8") as f:
        for row in golden:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # small fixture for unit tests / dry-run
    fixture_msgs = messages[:12]
    with (FIXTURES / "mini_messages.jsonl").open("w", encoding="utf-8") as f:
        for row in fixture_msgs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"messages={len(messages)} threads≈{thread_idx} golden={len(golden)}")
    print(f"wrote {SAMPLE_OUT}")
    print(f"wrote {GOLDEN_OUT}")


if __name__ == "__main__":
    main()
