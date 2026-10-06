"""Hiver AppleSupport shared inbox — FastAPI backend + single-page frontend.

Routes
  GET  /                      single-page app (static/index.html)
  GET  /health                liveness + agent + database status
  POST /api/analyze           stateless classify → draft → escalate playground
  /api/auth/*                 signup, login, logout, me
  /api/tickets*               shared inbox CRUD + reply / notes / re-run agent
  GET  /api/stats, /api/users, /api/meta

Data lives in Postgres (``DATABASE_URL`` / ``POSTGRES_URL``); see ``db.py``.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlsplit

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from hiver_agent.intents import INTENT_NAMES, INTENTS
from hiver_agent.web import auth, db, tickets
from hiver_agent.web.agent import ensure_runtime, runtime_error, runtime_ready

STATIC_DIR = Path(__file__).resolve().parent / "static"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        ensure_runtime()
    except Exception:
        pass  # first request retries; /health reports not-ready
    try:
        if db.database_url():
            db.ensure_schema()
    except Exception:
        pass  # surfaced by /health and API errors
    yield
    db.reset_pool()


app = FastAPI(
    title="Hiver AppleSupport inbox",
    description="Shared support inbox with an AI triage agent (classify → draft → escalate).",
    version="0.2.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------ errors

@app.exception_handler(db.DatabaseNotConfigured)
async def _db_not_configured(_req: Request, exc: db.DatabaseNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(psycopg.OperationalError)
async def _db_unavailable(_req: Request, _exc: psycopg.OperationalError):
    return JSONResponse(
        status_code=503, content={"detail": "Database is unavailable right now. Please retry."}
    )


@app.exception_handler(LookupError)
async def _not_found(_req: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={"detail": str(exc) or "not found"})


# ------------------------------------------------------------------ guards

def same_origin(request: Request) -> None:
    """Basic CSRF defence for cookie-authenticated writes: reject cross-site
    Origin headers and non-JSON bodies on state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if origin:
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if urlsplit(origin).netloc != host:
            raise HTTPException(status_code=403, detail="Cross-origin request blocked.")
    ctype = request.headers.get("content-type", "")
    if not ctype.startswith("application/json"):
        raise HTTPException(status_code=415, detail="Send requests as application/json.")


api = APIRouter(prefix="/api", dependencies=[Depends(same_origin)])


# ------------------------------------------------------------------ models

class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    dry_run: bool = True


class AnalyzeResponse(BaseModel):
    intent: str
    confidence: float
    method: str
    scores: dict[str, float] = Field(default_factory=dict)
    draft: str
    draft_sources: list[str] = Field(default_factory=list)
    draft_method: str
    escalation_action: str
    escalation_reason: str
    rules_fired: list[str] = Field(default_factory=list)
    dry_run: bool
    llm_error: Optional[str] = None


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=8, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=1, max_length=200)


class TicketCreate(BaseModel):
    customer_handle: str = Field(..., min_length=1, max_length=80)
    customer_text: str = Field(..., min_length=3, max_length=4000)
    channel: Literal["twitter", "email", "chat"] = "twitter"
    dry_run: bool = True

    @field_validator("customer_handle", "customer_text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field is required")
        return v


class TicketUpdate(BaseModel):
    status: Optional[Literal["open", "escalated", "replied", "closed"]] = None
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    assignee_id: Optional[int] = None
    draft: Optional[str] = Field(None, max_length=4000)


class ReplyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    close: bool = False

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Reply cannot be empty")
        return v


class NoteRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Note cannot be empty")
        return v


class RerunRequest(BaseModel):
    dry_run: bool = True


# ------------------------------------------------------------------ helpers

def _runtime():
    try:
        return ensure_runtime()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Agent not ready: {exc}") from exc


def _ticket_or_404(ticket_id: int) -> dict[str, Any]:
    t = tickets.get_ticket(ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Ticket #{ticket_id} not found")
    return t


# ------------------------------------------------------------------ public

@app.get("/health")
def health() -> dict[str, Any]:
    agent_ok = runtime_ready()
    if not agent_ok:
        try:
            ensure_runtime()
            agent_ok = True
        except Exception:
            agent_ok = False
    db_status = "not_configured"
    if db.database_url():
        try:
            db.ensure_schema()
            db_status = "ok" if db.ping() else "error"
        except Exception as exc:  # pragma: no cover - depends on network
            db_status = f"error: {type(exc).__name__}"
    ok = agent_ok and db_status == "ok"
    payload: dict[str, Any] = {
        "ok": ok,
        "status": "ok" if ok else "degraded",
        "agent": "ok" if agent_ok else "not_ready",
        "database": db_status,
    }
    if not agent_ok and runtime_error():
        payload["agent_error"] = runtime_error()
    return payload


@api.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    return AnalyzeResponse(**_runtime().analyze(text, dry_run=req.dry_run))


@api.get("/meta")
def meta() -> dict[str, Any]:
    from hiver_agent.llm.client import LLMClient

    return {
        "intents": [{"name": n, "description": INTENTS[n].description} for n in INTENT_NAMES],
        "statuses": list(tickets.STATUSES),
        "priorities": list(tickets.PRIORITIES),
        "live_llm_available": not LLMClient().dry_run,
    }


# ------------------------------------------------------------------ auth

@api.post("/auth/signup", status_code=201)
def signup(req: SignupRequest, request: Request, response: Response) -> dict[str, Any]:
    db.ensure_schema()
    with db.connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = %s", (req.email,)
        ).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        user = conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (%s, %s, %s) RETURNING id, email, name",
            (req.email, req.name, auth.hash_password(req.password)),
        ).fetchone()
    auth.create_session(response, request, user["id"])
    return {"user": auth.public_user(user)}


@api.post("/auth/login")
def login(req: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    db.ensure_schema()
    with db.connection() as conn:
        user = conn.execute(
            "SELECT id, email, name, password_hash FROM users WHERE lower(email) = %s",
            (req.email.strip().lower(),),
        ).fetchone()
    if user is None or not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    auth.create_session(response, request, user["id"])
    return {"user": auth.public_user(user)}


@api.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    auth.destroy_session(request, response)
    return {"ok": True}


@api.get("/auth/me")
def me(request: Request) -> dict[str, Any]:
    """Current user, or ``{"user": null}`` when signed out (no 401 noise)."""
    db.ensure_schema()
    user = auth.optional_user(request)
    return {"user": auth.public_user(user) if user else None}


# ------------------------------------------------------------------ inbox

@api.get("/users")
def users(_user: dict = Depends(auth.current_user)) -> dict[str, Any]:
    return {"items": tickets.list_users()}


@api.get("/stats")
def stats(user: dict = Depends(auth.current_user)) -> dict[str, Any]:
    return tickets.stats(user["id"])


@api.get("/tickets")
def list_tickets(
    user: dict = Depends(auth.current_user),
    status: Optional[Literal["open", "escalated", "replied", "closed", "active"]] = None,
    intent: Optional[str] = Query(None, max_length=40),
    assignee: Optional[Literal["me", "unassigned"]] = None,
    q: Optional[str] = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    if intent and intent not in INTENTS:
        raise HTTPException(status_code=422, detail=f"Unknown intent '{intent}'")
    return tickets.list_tickets(
        user_id=user["id"], status=status, intent=intent, assignee=assignee,
        q=(q or "").strip() or None, limit=limit, offset=offset,
    )


@api.post("/tickets", status_code=201)
def create_ticket(req: TicketCreate, user: dict = Depends(auth.current_user)) -> dict[str, Any]:
    analysis = _runtime().analyze(req.customer_text, dry_run=req.dry_run)
    handle = req.customer_handle
    if req.channel == "twitter" and not handle.startswith("@"):
        handle = "@" + handle
    tid = tickets.create_ticket(
        customer_handle=handle, customer_text=req.customer_text, channel=req.channel,
        analysis=analysis, user_id=user["id"],
    )
    return {"ticket": _ticket_or_404(tid), "llm_error": analysis.get("llm_error")}


@api.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, _user: dict = Depends(auth.current_user)) -> dict[str, Any]:
    return {"ticket": _ticket_or_404(ticket_id)}


@api.patch("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int, req: TicketUpdate, user: dict = Depends(auth.current_user)
) -> dict[str, Any]:
    changes = req.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    for key in ("status", "priority"):
        if key in changes and changes[key] is None:
            raise HTTPException(status_code=422, detail=f"{key} cannot be null")
    try:
        tickets.update_ticket(ticket_id, user["id"], changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ticket": _ticket_or_404(ticket_id)}


@api.post("/tickets/{ticket_id}/reply")
def reply(ticket_id: int, req: ReplyRequest, user: dict = Depends(auth.current_user)) -> dict[str, Any]:
    tickets.reply(ticket_id, user["id"], req.text, close=req.close)
    return {"ticket": _ticket_or_404(ticket_id)}


@api.post("/tickets/{ticket_id}/notes", status_code=201)
def add_note(ticket_id: int, req: NoteRequest, user: dict = Depends(auth.current_user)) -> dict[str, Any]:
    tickets.add_note(ticket_id, user["id"], req.body)
    return {"ticket": _ticket_or_404(ticket_id)}


@api.post("/tickets/{ticket_id}/reanalyze")
def reanalyze(
    ticket_id: int, req: RerunRequest, user: dict = Depends(auth.current_user)
) -> dict[str, Any]:
    t = _ticket_or_404(ticket_id)
    analysis = _runtime().analyze(t["customer_text"], dry_run=req.dry_run)
    tickets.apply_analysis(ticket_id, user["id"], analysis)
    return {"ticket": _ticket_or_404(ticket_id), "llm_error": analysis.get("llm_error")}


app.include_router(api)


# ------------------------------------------------------------------ frontend

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
