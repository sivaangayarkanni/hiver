-- Hiver shared support inbox: users, sessions, tickets, activity.

CREATE TABLE IF NOT EXISTS users (
    id            bigserial PRIMARY KEY,
    email         text NOT NULL,
    name          text NOT NULL,
    password_hash text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email));

CREATE TABLE IF NOT EXISTS sessions (
    token_hash text PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

CREATE TABLE IF NOT EXISTS tickets (
    id                bigserial PRIMARY KEY,
    customer_handle   text NOT NULL,
    channel           text NOT NULL DEFAULT 'twitter',
    customer_text     text NOT NULL,
    status            text NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open', 'escalated', 'replied', 'closed')),
    priority          text NOT NULL DEFAULT 'normal'
                      CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    intent            text,
    confidence        double precision,
    classifier        text,
    scores            jsonb NOT NULL DEFAULT '{}'::jsonb,
    draft             text,
    draft_method      text,
    draft_sources     jsonb NOT NULL DEFAULT '[]'::jsonb,
    escalation_action text,
    escalation_reason text,
    rules_fired       jsonb NOT NULL DEFAULT '[]'::jsonb,
    dry_run           boolean NOT NULL DEFAULT true,
    assignee_id       bigint REFERENCES users(id) ON DELETE SET NULL,
    reply_text        text,
    replied_at        timestamptz,
    created_by        bigint REFERENCES users(id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tickets_status_updated_idx ON tickets (status, updated_at DESC);
CREATE INDEX IF NOT EXISTS tickets_intent_idx ON tickets (intent);
CREATE INDEX IF NOT EXISTS tickets_assignee_idx ON tickets (assignee_id);

CREATE TABLE IF NOT EXISTS ticket_events (
    id         bigserial PRIMARY KEY,
    ticket_id  bigint NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    user_id    bigint REFERENCES users(id) ON DELETE SET NULL,
    kind       text NOT NULL,
    body       text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ticket_events_ticket_idx ON ticket_events (ticket_id, created_at);

-- On Supabase the public schema is exposed through the Data API (PostgREST).
-- This app talks to Postgres directly, so lock the tables down for API roles:
-- RLS on with no policies + revoke grants. No-op on vanilla Postgres.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticket_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON users, sessions, tickets, ticket_events, schema_migrations FROM %I', r);
        END IF;
    END LOOP;
END $$;
