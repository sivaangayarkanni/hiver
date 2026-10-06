"""Demo seed data: two agents + ~22 tickets run through the real agent pipeline.

Runs automatically on first boot when the users table is empty
(``HIVER_AUTO_SEED``, default on) or manually via ``python -m hiver_agent db seed``.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from hiver_agent.web import db
from hiver_agent.web.agent import _find_root, _load_threads, ensure_runtime
from hiver_agent.web.auth import hash_password
from hiver_agent.web.tickets import create_ticket

DEMO_PASSWORD_ENV = "HIVER_DEMO_PASSWORD"
DEFAULT_DEMO_PASSWORD = "hiver-demo-2026"

DEMO_USERS = [
    ("demo@hiver.dev", "Demo Agent"),
    ("maya@hiver.dev", "Maya Iyer"),
]

HANDLES = [
    "@priya_codes", "@jmarsh", "@tomasz_k", "@leafygreen", "@nadia.r", "@benji_t",
    "@quietfox", "@arjunv", "@sophielin", "@k8_moss", "@raf_dev", "@helloimdan",
    "@mira.photo", "@oz_runner", "@lucasbr", "@anika.s", "@yuki_t", "@carlos.m",
    "@emmaw", "@devon_p", "@zara_k", "@sam_n",
]


def _pick_messages(per_intent: int = 2) -> list[str]:
    threads = _load_threads(_find_root())
    by_intent: dict[str, list[str]] = defaultdict(list)
    for t in threads:
        text = (t.customer_text or "").split("\n")[0].strip()
        if t.intent and text and len(by_intent[t.intent]) < per_intent:
            by_intent[t.intent].append(text)
    out: list[str] = []
    for i in range(per_intent):
        for intent in sorted(by_intent):
            if i < len(by_intent[intent]):
                out.append(by_intent[intent][i])
    return out


def seed(force: bool = False) -> dict[str, Any]:
    password = os.getenv(DEMO_PASSWORD_ENV) or DEFAULT_DEMO_PASSWORD
    runtime = ensure_runtime()
    now = datetime.now(timezone.utc)
    with db.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(724362)")
        n_users = conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"]
        if n_users and not force:
            return {"seeded": False, "reason": "database already has users"}

        user_ids: list[int] = []
        for email, name in DEMO_USERS:
            row = conn.execute(
                """INSERT INTO users (email, name, password_hash) VALUES (%s, %s, %s)
                   ON CONFLICT (lower(email)) DO UPDATE SET name = EXCLUDED.name
                   RETURNING id""",
                (email, name, hash_password(password)),
            ).fetchone()
            user_ids.append(row["id"])
        demo_id, maya_id = user_ids

        created = 0
        messages = _pick_messages()
        for i, text in enumerate(messages):
            analysis = runtime.analyze(text, dry_run=True)
            tid = create_ticket(
                customer_handle=HANDLES[i % len(HANDLES)],
                customer_text=text,
                channel="twitter",
                analysis=analysis,
                user_id=None,
                conn=conn,
            )
            # Spread tickets over the last ~3 days and give the inbox some history.
            ts = now - timedelta(hours=3 * (len(messages) - i), minutes=7 * i)
            conn.execute(
                "UPDATE tickets SET created_at = %s, updated_at = %s WHERE id = %s", (ts, ts, tid)
            )
            conn.execute("UPDATE ticket_events SET created_at = %s WHERE ticket_id = %s", (ts, tid))
            if i % 5 == 1 and analysis["escalation_action"] == "auto_handle":
                reply_text = (analysis["draft"] or "").replace("[dry-run] ", "")
                later = ts + timedelta(minutes=18)
                conn.execute(
                    """UPDATE tickets SET status='replied', reply_text=%s, replied_at=%s,
                              assignee_id=%s, updated_at=%s WHERE id=%s""",
                    (reply_text, later, demo_id, later, tid),
                )
                conn.execute(
                    """INSERT INTO ticket_events (ticket_id, user_id, kind, body, created_at)
                       VALUES (%s,%s,'reply',%s,%s), (%s,%s,'status','Status open → replied',%s)""",
                    (tid, demo_id, reply_text, later, tid, demo_id, later),
                )
            elif analysis["escalation_action"] == "escalate" and i % 3 == 0:
                conn.execute("UPDATE tickets SET assignee_id=%s WHERE id=%s", (maya_id, tid))
                conn.execute(
                    """INSERT INTO ticket_events (ticket_id, user_id, kind, body, created_at)
                       VALUES (%s,%s,'assign','Assigned to Maya Iyer',%s)""",
                    (tid, demo_id, ts + timedelta(minutes=5)),
                )
            created += 1
    return {"seeded": True, "users": [e for e, _ in DEMO_USERS], "tickets": created}


def seed_if_empty() -> dict[str, Any]:
    return seed(force=False)
