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
git checkout feat/applesupport-mvp   # or main if merged

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

## Layout

```
src/hiver_agent/     # package (classify, retrieve, escalate, eval, pipeline, cli)
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
This feature branch is the review surface for the take-home MVP.
