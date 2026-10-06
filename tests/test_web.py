"""Web app tests.

Unit tests always run. API integration tests need a throwaway Postgres:

    TEST_DATABASE_URL=postgresql://postgres@localhost:5432/hiver_test pytest -q

WARNING: the integration fixture drops the app tables in that database.
"""

from __future__ import annotations

import os
import uuid

import pytest

from hiver_agent.web.auth import hash_password, verify_password
from hiver_agent.web.db import normalize_url


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$")
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "garbage")


def test_normalize_url_drops_provider_params():
    url = "postgres://u:p@host:6543/postgres?sslmode=require&supa=base-pooler.x"
    assert normalize_url(url) == "postgresql://u:p@host:6543/postgres?sslmode=require"


TEST_DB = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def client():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    from fastapi.testclient import TestClient

    with psycopg.connect(normalize_url(TEST_DB), autocommit=True) as conn:
        conn.execute(
            "DROP TABLE IF EXISTS ticket_events, tickets, sessions, users, schema_migrations CASCADE"
        )
    os.environ["DATABASE_URL"] = TEST_DB
    from hiver_agent.web import db
    from hiver_agent.web.app import app

    db.reset_pool()
    with TestClient(app) as c:
        yield c
    db.reset_pool()


def _login(c, email="demo@hiver.dev", password="hiver-demo-2026"):
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["user"]


def test_health_and_seed(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"
    _login(client)
    stats = client.get("/api/stats").json()
    assert stats["total"] >= 20  # auto-seeded demo tickets


def test_auth_required_and_signup(client):
    client.cookies.clear()
    assert client.get("/api/tickets").status_code == 401
    assert client.get("/api/auth/me").json() == {"user": None}
    email = f"t-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/signup", json={"name": "T", "email": email, "password": "short"})
    assert r.status_code == 422
    r = client.post("/api/auth/signup", json={"name": "Tess", "email": email, "password": "longenough1"})
    assert r.status_code == 201
    assert client.get("/api/auth/me").json()["user"]["email"] == email
    r = client.post("/api/auth/signup", json={"name": "Tess", "email": email.upper(), "password": "longenough1"})
    assert r.status_code == 409
    client.post("/api/auth/logout", json={})
    assert client.get("/api/auth/me").json() == {"user": None}


def test_ticket_lifecycle(client):
    me = _login(client)
    r = client.post(
        "/api/tickets",
        json={"customer_handle": "tester", "customer_text": "My iPhone was stolen, please help me lock it"},
    )
    assert r.status_code == 201, r.text
    t = r.json()["ticket"]
    assert t["customer_handle"] == "@tester"
    assert t["status"] == "escalated" and t["priority"] == "urgent"
    tid = t["id"]

    r = client.patch(f"/api/tickets/{tid}", json={"assignee_id": me["id"], "priority": "high"})
    assert r.status_code == 200
    assert r.json()["ticket"]["assignee_id"] == me["id"]
    assert client.patch(f"/api/tickets/{tid}", json={"status": "nope"}).status_code == 422
    assert client.patch(f"/api/tickets/{tid}", json={"assignee_id": 999999}).status_code == 422

    assert client.post(f"/api/tickets/{tid}/notes", json={"body": "  "}).status_code == 422
    assert client.post(f"/api/tickets/{tid}/notes", json={"body": "call back"}).status_code == 201
    assert client.post(f"/api/tickets/{tid}/reanalyze", json={}).status_code == 200

    r = client.post(f"/api/tickets/{tid}/reply", json={"text": "We've locked it for you.", "close": True})
    t = r.json()["ticket"]
    assert t["status"] == "closed" and t["reply_text"]
    kinds = [e["kind"] for e in t["events"]]
    for k in ("created", "agent", "assign", "note", "reply", "status"):
        assert k in kinds

    found = client.get("/api/tickets", params={"q": "@tester", "status": "closed"}).json()
    assert any(x["id"] == tid for x in found["items"])
    mine = client.get("/api/tickets", params={"assignee": "me"}).json()
    assert any(x["id"] == tid for x in mine["items"])
    assert client.get("/api/tickets/987654321").status_code == 404


def test_csrf_guards(client):
    _login(client)
    r = client.post("/api/tickets", content="x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    r = client.post(
        "/api/auth/logout", json={}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403
