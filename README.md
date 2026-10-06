# Hiver AppleSupport AI Agent (SDE Intern Take-Home MVP)

Honest MVP of a Twitter/X-style **AppleSupport** agent that:

1. **Classifies** customer messages into ~11 intents  
2. **Drafts** replies grounded in historical resolutions (TF-IDF retrieval + OpenAI-compatible LLM)  
3. **Decides** auto-handle vs escalate with an explicit reason  
4. Ships a **golden eval set** (200 labelled examples) + **eval harness**  
5. Documents framing, baselines, failures, and what headline numbers mislead

> Sample data is **synthetic / pattern-constructed** from public Twitter support *styles* — not a dump of the Kaggle 3M “Customer Support on Twitter” dataset.

## ≤15 minute dry-run demo (no API key)

```bash
# 0) clone & enter
git clone https://github.com/sivaangayarkanni/hiver.git
cd hiver
git checkout main

# 1) Python 3.11+ venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2) prepare threads from sample JSONL
python -m hiver_agent prepare-data

# 3) train TF-IDF + LogisticRegression intent model
python -m hiver_agent train --method tfidf

# 4) end-to-end pipeline on 5 sample threads (mock LLM)
python -m hiver_agent run-pipeline --dry-run --limit 5

# 5) evaluate on golden set (automated metrics + mock LLM judge)
python -m hiver_agent evaluate --dry-run --judge-sample 20

# 6) tests
pytest -q
```

Optional single-call examples:

```bash
python -m hiver_agent classify -t "Battery draining after iOS update"
python -m hiver_agent draft -t "iCloud storage full, can't backup" --intent icloud_storage --dry-run
python -m hiver_agent escalate -t "My iPhone was stolen" --intent privacy_security --confidence 0.9
```

### Live LLM (optional)

```bash
export OPENAI_API_KEY=sk-...
# optional: export OPENAI_BASE_URL=https://api.openai.com/v1
# optional: export OPENAI_MODEL=gpt-4o-mini
python -m hiver_agent run-pipeline --live --limit 3
python -m hiver_agent evaluate --live --judge-sample 10
```

`--dry-run` / missing `OPENAI_API_KEY` uses fixture replies + mock judge — fully reproducible offline.


## Full-stack web app: shared AppleSupport inbox

The web app turns the agent into a working, Hiver-style **shared support inbox**
backed by Postgres:

- **Sign up / sign in** (email + password, scrypt hashes, DB-backed HttpOnly session cookies)
- **Inbox views**: active, assigned to me, unassigned, escalated, open (auto-handle), replied, closed, all — with search (`text`, `@handle`, `#id`), intent filter, pagination and live counts
- **New ticket** → the agent runs classify → draft → escalate and the result is stored (escalations land as `escalated` with `high`/`urgent` priority)
- **Ticket detail**: change status / priority / assignee, edit + save the grounded draft, **send reply** (or send & close), re-run the agent, internal notes, full activity timeline
- **Dashboard stats**: active, escalated, assigned to me, agent auto-handle rate
- **Agent playground** (`#/playground`, no login): the original stateless demo

**Demo login** (seeded automatically into an empty database): `demo@hiver.dev` / `hiver-demo-2026`
(also `maya@hiver.dev`, same password; override with `HIVER_DEMO_PASSWORD`).

### Stack

| Layer | What |
| --- | --- |
| Frontend | Dependency-free SPA (`src/hiver_agent/web/static/`: `index.html`, `app.js`, `styles.css`), hash routing |
| Backend | FastAPI (`src/hiver_agent/web/app.py`) — auth, tickets, stats, analyze |
| Database | Postgres via `psycopg` 3 + `psycopg_pool`; SQL migrations in `src/hiver_agent/web/migrations/` |
| Agent | Existing TF-IDF classifier + retrieval drafter + escalation rules (`agent.py` wraps them) |
| Hosting | Vercel Python runtime (`app/main.py` entrypoint), Postgres on Supabase (free plan, via the Vercel Marketplace) |

### Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # set DATABASE_URL to any Postgres
python -m hiver_agent db migrate
python -m hiver_agent db seed  # demo users + ~22 triaged tickets (skipped if users exist)
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000  → sign in with the demo login
```

Migrations and the demo seed also run automatically on the first request
(`HIVER_AUTO_MIGRATE=1`, `HIVER_AUTO_SEED=1` by default), so a fresh database just works.

### API (JSON; cookie auth; writes must be `application/json` and same-origin)

| Method | Path | |
| --- | --- | --- |
| GET | `/health` | agent + database status |
| POST | `/api/analyze` | stateless classify → draft → escalate (public) |
| POST | `/api/auth/signup` · `/api/auth/login` · `/api/auth/logout` | auth |
| GET | `/api/auth/me` | current user or `{"user": null}` |
| GET | `/api/meta` · `/api/users` · `/api/stats` | intents/statuses, teammates, dashboard counts |
| GET / POST | `/api/tickets` | list (`status`, `intent`, `assignee=me\|unassigned`, `q`, `limit`, `offset`) / create + triage |
| GET / PATCH | `/api/tickets/{id}` | detail with events / update `status`, `priority`, `assignee_id`, `draft` |
| POST | `/api/tickets/{id}/reply` · `/notes` · `/reanalyze` | send reply (`close` optional), internal note, re-run agent |

### Tests

```bash
pytest -q                                                   # unit tests
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/hiver_test pytest -q   # + API integration (drops app tables in that DB!)
```

### Deploy (Vercel)

1. `vercel link` (Framework preset: FastAPI; leave Install Command on auto so it uses `requirements.txt`).
2. Add a Postgres: `vercel integration add supabase --plan free` (or Neon) — this sets `POSTGRES_URL`
   for all environments. Any `DATABASE_URL` works too (`vercel env add DATABASE_URL`).
3. `vercel --prod`. The first request migrates and seeds the database; or run
   `python -m hiver_agent db seed` locally against the same URL.

Optional env: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` for live LLM drafts (falls back to the
dry-run drafter if the provider errors), `HIVER_DEMO_PASSWORD`, `SESSION_DAYS`.

Docker / Railway / Render still work (`Dockerfile`, `Procfile`, `railway.toml`) — just set `DATABASE_URL`.

## Layout

```
src/hiver_agent/     # package (classify, retrieve, escalate, eval, pipeline, cli, web)
src/hiver_agent/web/ # FastAPI app, auth, tickets repo, db + migrations, seed, static SPA
app/main.py          # Vercel / uvicorn entrypoint
data/sample/         # ~250 AppleSupport-style messages / ~110 threads (JSONL)
data/golden/         # 200 labelled golden examples
data/fixtures/       # tiny fixtures for tests
docs/REPORT.md       # framing, baselines, failures, misleading metrics, next week
DECISIONS.md         # 10–15 design decisions
CITATIONS.md         # borrowed ideas / libs
LABELING.md          # labelling guide for golden set
artifacts/           # generated models + eval outputs (gitignored pkl ok to regenerate)
```

## Intents (11)

`apple_id_login`, `billing_subscription`, `device_hardware`, `software_update`, `app_store`, `icloud_storage`, `battery_performance`, `connectivity`, `privacy_security`, `how_to`, `other`

## Escalation policy (short)

- Hard rules: security/stolen/phishing, legal/crisis language, high-risk billing refunds, hardware service cues, `other` / `privacy_security` intents  
- Soft gate: confidence below an intent-adjusted threshold → escalate with reason  

## Docs to read in review order

1. `README.md` (this file)  
2. `DECISIONS.md`  
3. `docs/REPORT.md`  
4. `LABELING.md` / `CITATIONS.md`

## License note

Take-home submission code; sample text is synthetic. Third-party libs retain their own licenses (see `CITATIONS.md`).

## PR note
`main` ships the take-home MVP plus the full-stack inbox (FastAPI + Postgres + SPA) deployable on Vercel.
