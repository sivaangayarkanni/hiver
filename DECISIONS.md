# Design decisions (MVP)

1. **Synthetic sample over full Kaggle download** — Reproducible in ≤15 minutes without Kaggle credentials; patterns mirror public Twitter support threads. Tradeoff: distribution shift vs real AppleSupport traffic.

2. **11 intents, not 30+** — Enough for routing + escalation bias, small enough to label and explain. `other` is a first-class bucket that defaults toward escalate.

3. **TF-IDF + LogisticRegression as primary classifier** — Strong simple baseline for short texts; trains in seconds; no embedding API required for dry-run. Embeddings+LR left as a next-week option.

4. **Majority + keyword as trivial baselines** — Forces the report to show lift over naïve policies reviewers expect.

5. **Retrieval = TF-IDF over historical agent resolutions** — Grounding without a vector DB. Query is customer text; documents are past agent replies.

6. **LLM drafts only after retrieval** — Prompt includes top-k resolutions; reduces hallucination vs “write a helpful Apple reply” alone. Dry-run uses intent-keyed fixtures.

7. **OpenAI-compatible client via env vars** — `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`, `OPENAI_MODEL` (default `gpt-4o-mini`) so reviewers can point at any compatible gateway.

8. **`--dry-run` default for pipeline/eval** — Reviewers must not need a paid key to smoke-test. Missing key also forces mock mode.

9. **Escalation = rules + confidence threshold** — Interpretable for a support-ops audience; intent `escalate_bias` scales the threshold. Not a learned ranker (yet).

10. **Golden set 200, mix of thread-derived + paraphrases** — Meets 150–250 requirement; clearly marked `pattern_constructed` / `synthetic_seed` so metrics aren’t mistaken for production A/B results.

11. **LLM-as-judge on a sample (default 20)** — Cost/latency control; reports average rubric scores. Dry-run judge is deterministic mock — labelled as such in outputs.

12. **Judge–human agreement section is honest about small-n / placeholder** — Dry-run pairs mock-human = rounded judge; live path expects real ratings later.

13. **Package under `src/hiver_agent` + `python -m hiver_agent`** — Matches assignment packaging constraints; Typer CLI for subcommands.

14. **JSONL everywhere** — Easy to `head`, diff, and stream; no DB for the offline pipeline/eval (the web inbox uses Postgres, see 16).

15. **Prefer feature branch `feat/applesupport-mvp` + PR** — Clean review surface on an empty repo without force-pushing main history games.

## Full-stack inbox (v0.2)

16. **Postgres for the web inbox, JSONL stays for the ML pipeline** — Tickets, users, sessions and activity need concurrent, durable writes; the training/eval data stays as reviewable JSONL.

17. **Keep FastAPI, deploy on Vercel's Python runtime** — The agent is Python (scikit-learn); Vercel runs FastAPI natively, so no rewrite into Next.js was needed. `app/main.py` is the zero-config entrypoint and adds `src/` to `sys.path` because Vercel installs `requirements.txt`, not the project.

18. **Plain SQL migrations + `psycopg` (no ORM)** — Four tables, a dozen queries; a tiny migration runner with an advisory lock keeps it explicit and safe for concurrent serverless cold starts. Prepared statements are disabled so transaction-mode poolers (Supabase :6543, PgBouncer, Neon) work.

19. **Own email/password auth with DB sessions instead of a hosted auth provider** — No extra vendor or browser-based setup; scrypt hashes, random session tokens stored only as SHA-256, HttpOnly + SameSite=Lax cookies, and a same-origin/JSON-only guard on writes as CSRF defence.

20. **Dependency-free frontend** — The original demo was a single HTML page; the inbox keeps that design language and ships as three static files, so there is no Node build step in a Python repo.

21. **Supabase tables locked down for the Data API** — The app connects as the DB owner; RLS is enabled with no policies and grants are revoked from `anon`/`authenticated`, so the auto-exposed PostgREST API cannot read users or tickets.

22. **Auto-migrate + seed on first request** — A fresh database is usable on the first page load (demo users and ~22 tickets triaged by the real agent), controllable via `HIVER_AUTO_MIGRATE` / `HIVER_AUTO_SEED`.
