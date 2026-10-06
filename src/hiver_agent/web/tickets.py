"""Ticket repository: persistence + workflow for the shared support inbox."""

from __future__ import annotations

from typing import Any, Optional

from psycopg.types.json import Jsonb

from hiver_agent.web import db

STATUSES = ("open", "escalated", "replied", "closed")
PRIORITIES = ("low", "normal", "high", "urgent")

_TICKET_COLS = """
    t.id, t.customer_handle, t.channel, t.customer_text, t.status, t.priority,
    t.intent, t.confidence, t.classifier, t.scores, t.draft, t.draft_method,
    t.draft_sources, t.escalation_action, t.escalation_reason, t.rules_fired,
    t.dry_run, t.assignee_id, a.name AS assignee_name, t.reply_text, t.replied_at,
    t.created_by, c.name AS created_by_name, t.created_at, t.updated_at
"""
_FROM = """
    FROM tickets t
    LEFT JOIN users a ON a.id = t.assignee_id
    LEFT JOIN users c ON c.id = t.created_by
"""


def _priority_for(analysis: dict[str, Any]) -> str:
    rules = " ".join(analysis.get("rules_fired") or [])
    if "security_pattern" in rules or "legal_or_crisis" in rules:
        return "urgent"
    if analysis.get("escalation_action") == "escalate":
        return "high"
    return "normal"


def _add_event(conn, ticket_id: int, user_id: Optional[int], kind: str, body: Optional[str] = None) -> None:
    conn.execute(
        "INSERT INTO ticket_events (ticket_id, user_id, kind, body) VALUES (%s, %s, %s, %s)",
        (ticket_id, user_id, kind, body),
    )


def create_ticket(
    *,
    customer_handle: str,
    customer_text: str,
    channel: str,
    analysis: dict[str, Any],
    user_id: Optional[int],
    conn=None,
) -> int:
    status = "escalated" if analysis.get("escalation_action") == "escalate" else "open"

    def _do(c) -> int:
        row = c.execute(
            """INSERT INTO tickets (customer_handle, channel, customer_text, status, priority,
                   intent, confidence, classifier, scores, draft, draft_method, draft_sources,
                   escalation_action, escalation_reason, rules_fired, dry_run, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                customer_handle, channel, customer_text, status, _priority_for(analysis),
                analysis.get("intent"), analysis.get("confidence"), analysis.get("method"),
                Jsonb(analysis.get("scores") or {}), analysis.get("draft"),
                analysis.get("draft_method"), Jsonb(analysis.get("draft_sources") or []),
                analysis.get("escalation_action"), analysis.get("escalation_reason"),
                Jsonb(analysis.get("rules_fired") or []), bool(analysis.get("dry_run", True)),
                user_id,
            ),
        ).fetchone()
        tid = row["id"]
        _add_event(c, tid, user_id, "created", f"Ticket created from {channel}")
        _add_event(
            c, tid, None, "agent",
            f"Agent classified as {analysis.get('intent')} "
            f"({float(analysis.get('confidence') or 0):.2f}) → "
            f"{(analysis.get('escalation_action') or '').replace('_', ' ')}: "
            f"{analysis.get('escalation_reason') or ''}",
        )
        return tid

    if conn is not None:
        return _do(conn)
    with db.connection() as c:
        return _do(c)


def list_tickets(
    *,
    user_id: int,
    status: Optional[str] = None,
    intent: Optional[str] = None,
    assignee: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    where, params = [], []
    if status == "active":
        where.append("t.status IN ('open','escalated')")
    elif status:
        where.append("t.status = %s")
        params.append(status)
    if intent:
        where.append("t.intent = %s")
        params.append(intent)
    if assignee == "me":
        where.append("t.assignee_id = %s")
        params.append(user_id)
    elif assignee == "unassigned":
        where.append("t.assignee_id IS NULL")
    if q:
        where.append("(t.customer_text ILIKE %s OR t.customer_handle ILIKE %s OR t.id::text = %s)")
        like = f"%{q}%"
        params += [like, like, q.lstrip("#")]
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with db.connection() as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM tickets t {clause}", params).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT {_TICKET_COLS} {_FROM} {clause}
                ORDER BY CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                                         WHEN 'normal' THEN 2 ELSE 3 END,
                         t.updated_at DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        ).fetchall()
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_ticket(ticket_id: int) -> Optional[dict[str, Any]]:
    with db.connection() as conn:
        t = conn.execute(f"SELECT {_TICKET_COLS} {_FROM} WHERE t.id = %s", (ticket_id,)).fetchone()
        if t is None:
            return None
        t["events"] = conn.execute(
            """SELECT e.id, e.kind, e.body, e.created_at, e.user_id, u.name AS user_name
                 FROM ticket_events e LEFT JOIN users u ON u.id = e.user_id
                WHERE e.ticket_id = %s ORDER BY e.created_at, e.id""",
            (ticket_id,),
        ).fetchall()
    return t


def _exists(conn, ticket_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, status, priority, assignee_id, draft FROM tickets WHERE id = %s FOR UPDATE",
        (ticket_id,),
    ).fetchone()
    if row is None:
        raise LookupError("ticket not found")
    return row


def update_ticket(ticket_id: int, user_id: int, changes: dict[str, Any]) -> None:
    with db.connection() as conn:
        cur = _exists(conn, ticket_id)
        sets, params = [], []
        if "status" in changes and changes["status"] != cur["status"]:
            sets.append("status = %s")
            params.append(changes["status"])
            _add_event(conn, ticket_id, user_id, "status", f"Status {cur['status']} → {changes['status']}")
        if "priority" in changes and changes["priority"] != cur["priority"]:
            sets.append("priority = %s")
            params.append(changes["priority"])
            _add_event(conn, ticket_id, user_id, "priority", f"Priority {cur['priority']} → {changes['priority']}")
        if "assignee_id" in changes and changes["assignee_id"] != cur["assignee_id"]:
            aid = changes["assignee_id"]
            name = None
            if aid is not None:
                u = conn.execute("SELECT name FROM users WHERE id = %s", (aid,)).fetchone()
                if u is None:
                    raise ValueError("assignee does not exist")
                name = u["name"]
            sets.append("assignee_id = %s")
            params.append(aid)
            _add_event(conn, ticket_id, user_id, "assign", f"Assigned to {name}" if name else "Unassigned")
        if "draft" in changes and changes["draft"] != cur["draft"]:
            sets.append("draft = %s")
            params.append(changes["draft"])
            _add_event(conn, ticket_id, user_id, "draft", "Draft edited")
        if sets:
            sets.append("updated_at = now()")
            conn.execute(f"UPDATE tickets SET {', '.join(sets)} WHERE id = %s", params + [ticket_id])


def reply(ticket_id: int, user_id: int, text: str, close: bool = False) -> None:
    with db.connection() as conn:
        cur = _exists(conn, ticket_id)
        status = "closed" if close else "replied"
        conn.execute(
            """UPDATE tickets SET reply_text = %s, replied_at = now(), status = %s,
                      assignee_id = COALESCE(assignee_id, %s), updated_at = now()
                WHERE id = %s""",
            (text, status, user_id, ticket_id),
        )
        _add_event(conn, ticket_id, user_id, "reply", text)
        if cur["status"] != status:
            _add_event(conn, ticket_id, user_id, "status", f"Status {cur['status']} → {status}")


def add_note(ticket_id: int, user_id: int, body: str) -> None:
    with db.connection() as conn:
        _exists(conn, ticket_id)
        _add_event(conn, ticket_id, user_id, "note", body)
        conn.execute("UPDATE tickets SET updated_at = now() WHERE id = %s", (ticket_id,))


def apply_analysis(ticket_id: int, user_id: int, analysis: dict[str, Any]) -> None:
    with db.connection() as conn:
        _exists(conn, ticket_id)
        conn.execute(
            """UPDATE tickets SET intent=%s, confidence=%s, classifier=%s, scores=%s, draft=%s,
                      draft_method=%s, draft_sources=%s, escalation_action=%s,
                      escalation_reason=%s, rules_fired=%s, dry_run=%s, updated_at=now()
                WHERE id=%s""",
            (
                analysis.get("intent"), analysis.get("confidence"), analysis.get("method"),
                Jsonb(analysis.get("scores") or {}), analysis.get("draft"),
                analysis.get("draft_method"), Jsonb(analysis.get("draft_sources") or []),
                analysis.get("escalation_action"), analysis.get("escalation_reason"),
                Jsonb(analysis.get("rules_fired") or []), bool(analysis.get("dry_run", True)),
                ticket_id,
            ),
        )
        _add_event(
            conn, ticket_id, user_id, "agent",
            f"Agent re-run: {analysis.get('intent')} ({float(analysis.get('confidence') or 0):.2f}) → "
            f"{(analysis.get('escalation_action') or '').replace('_', ' ')}",
        )


def stats(user_id: int) -> dict[str, Any]:
    with db.connection() as conn:
        by_status = {
            r["status"]: r["n"]
            for r in conn.execute("SELECT status, count(*) AS n FROM tickets GROUP BY status")
        }
        by_intent = conn.execute(
            """SELECT intent, count(*) AS n FROM tickets
                WHERE status IN ('open','escalated') AND intent IS NOT NULL
                GROUP BY intent ORDER BY n DESC, intent"""
        ).fetchall()
        mine = conn.execute(
            "SELECT count(*) AS n FROM tickets WHERE assignee_id = %s AND status IN ('open','escalated')",
            (user_id,),
        ).fetchone()["n"]
        agg = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE escalation_action = 'auto_handle') AS auto_handle
                 FROM tickets"""
        ).fetchone()
    total = agg["total"] or 0
    return {
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "active": by_status.get("open", 0) + by_status.get("escalated", 0),
        "mine": mine,
        "total": total,
        "auto_handle_rate": (agg["auto_handle"] / total) if total else 0.0,
        "active_by_intent": by_intent,
    }


def list_users() -> list[dict[str, Any]]:
    with db.connection() as conn:
        return conn.execute("SELECT id, name, email FROM users ORDER BY name").fetchall()
