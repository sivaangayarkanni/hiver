"""Postgres access: connection pool, URL normalisation, and SQL migrations.

Works with any Postgres (local, Supabase, Neon, Render, Railway). The URL is
read from ``DATABASE_URL`` (preferred) or ``POSTGRES_URL`` (set automatically by
the Vercel Supabase/Neon integrations).

Serverless notes:
* Prepared statements are disabled (``prepare_threshold=None``) so the app works
  behind transaction-mode poolers (Supabase Supavisor :6543, PgBouncer, Neon).
* The pool starts empty and keeps at most a few connections per warm instance.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from importlib import resources
from typing import Any, Iterator, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# libpq connection parameters we pass through from the URL query string.
_LIBPQ_PARAMS = {
    "host", "hostaddr", "port", "dbname", "user", "password", "sslmode",
    "sslnegotiation", "sslrootcert", "sslcert", "sslkey", "connect_timeout",
    "application_name", "target_session_attrs", "options", "channel_binding",
    "gssencmode", "keepalives", "keepalives_idle", "keepalives_interval",
    "keepalives_count",
}

_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()
_schema_ready = False
_schema_lock = threading.Lock()


class DatabaseNotConfigured(RuntimeError):
    pass


def database_url() -> Optional[str]:
    for key in ("DATABASE_URL", "POSTGRES_URL"):
        val = os.getenv(key, "").strip()
        if val:
            return val
    return None


def normalize_url(url: str) -> str:
    """Drop provider-specific query params libpq would reject (e.g. Supabase's
    ``supa=base-pooler.x``) and accept the ``postgres://`` scheme."""
    parts = urlsplit(url)
    scheme = "postgresql" if parts.scheme in ("postgres", "postgresql") else parts.scheme
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k in _LIBPQ_PARAMS]
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            url = database_url()
            if not url:
                raise DatabaseNotConfigured(
                    "DATABASE_URL (or POSTGRES_URL) is not set — see .env.example"
                )
            _pool = ConnectionPool(
                conninfo=normalize_url(url),
                kwargs={"prepare_threshold": None, "row_factory": dict_row, "connect_timeout": 10},
                min_size=0,
                max_size=int(os.getenv("DB_POOL_MAX", "4")),
                max_idle=60,
                timeout=15,
                check=ConnectionPool.check_connection,
                open=True,
                name="hiver",
            )
    return _pool


@contextmanager
def connection() -> Iterator[psycopg.Connection[Any]]:
    """Yield a pooled connection inside a transaction (commit on success)."""
    with get_pool().connection() as conn:
        yield conn


def reset_pool() -> None:
    """Close the pool (used by tests and the CLI)."""
    global _pool, _schema_ready
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = None
        _schema_ready = False


# ---------------------------------------------------------------- migrations

def _migration_files() -> list[tuple[str, str]]:
    pkg = resources.files("hiver_agent.web") / "migrations"
    files = sorted(p for p in pkg.iterdir() if p.name.endswith(".sql"))
    return [(p.name, p.read_text(encoding="utf-8")) for p in files]


def migrate() -> list[str]:
    """Apply pending SQL migrations in order. Idempotent and concurrency-safe
    (serialised with a transaction-scoped advisory lock)."""
    applied: list[str] = []
    with connection() as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(724361)")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       version text PRIMARY KEY,
                       applied_at timestamptz NOT NULL DEFAULT now())"""
            )
            done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
            for name, sql in _migration_files():
                if name in done:
                    continue
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (name,))
                applied.append(name)
    return applied


def ensure_schema() -> None:
    """Run migrations (and optional demo seed) once per process.

    Controlled by ``HIVER_AUTO_MIGRATE`` (default on) so a fresh database works
    on the first request without a separate release step.
    """
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        if os.getenv("HIVER_AUTO_MIGRATE", "1").lower() not in ("0", "false", "no"):
            migrate()
            if os.getenv("HIVER_AUTO_SEED", "1").lower() not in ("0", "false", "no"):
                from hiver_agent.web.seed import seed_if_empty

                seed_if_empty()
        _schema_ready = True


def ping() -> bool:
    with connection() as conn:
        return conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
