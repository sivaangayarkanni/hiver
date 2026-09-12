# Report — AppleSupport AI Twitter agent MVP

## Framing

**Problem.** Public social support channels get high volume of short, messy customer posts. A useful agent must (a) route by intent, (b) draft a grounded reply, and (c) know when to stop and escalate.

**Scope of this MVP.** Offline, reproducible pipeline on a **synthetic** AppleSupport-style corpus (~110 threads / ~250 messages) plus a **200-example golden set**. Not a production deployment, not trained on the full Kaggle Customer Support on Twitter dump.

**Success for the take-home.** A reviewer can clone, `pip install`, and run dry-run train → pipeline → evaluate in ≤15 minutes, then read this report + `DECISIONS.md`.

## Method (one paragraph)

We train intent classifiers on labelled customer text from the sample threads. The primary model is **TF-IDF (1–2 grams) + Logistic Regression**. At inference we predict intent + confidence, retrieve top-k historical agent resolutions by TF-IDF cosine similarity, draft a reply with an OpenAI-compatible LLM (or fixture mock), then apply **rule-based escalation** (security/billing/hardware/legal cues + confidence threshold adjusted by intent risk bias).

## Baselines (≥2)

Evaluated on the **200 golden examples** (same train sample for fitting; golden includes paraphrases held out as threads `SYN*`). Figures below are from a dry-run `python -m hiver_agent evaluate` on this box — **re-run locally to regenerate** `artifacts/eval_report.json`.

| Method | Role | Accuracy (golden) | Macro-F1 (golden) |
|--------|------|-------------------|-------------------|
| Majority | Trivial baseline | 0.080 | 0.013 |
| Keyword hits | Trivial / weak baseline | 0.790 | 0.807 |
| TF-IDF + LR | Simple primary model | 0.800 | 0.806 |

**Escalation (rules + confidence):** accuracy=0.690, precision=0.556, recall=0.961, F1=0.705 (n=200).

**LLM-as-judge (dry-run mock, n=20):** avg overall=4.05 — **not a real LLM score**.

Note: **Keyword ≈ TF-IDF** on this seed because templates are cue-phrase heavy; lift over majority is real, lift over keywords is small — expected and called out in the misleading-metrics section.

These numbers were measured on 2026-09-12 via `python -m hiver_agent evaluate --dry-run` on the checked-in synthetic golden set.

Escalation (rules + confidence) is scored as binary F1 against `should_escalate` labels. Reply quality uses LLM-as-judge (rubric 1–5) on a sample of 20; in `--dry-run` the judge is a **mock** and must not be cited as model quality.

## Top 5 failure modes (observed / expected on this seed)

1. **Multi-intent posts → `other` or wrong primary** — e.g. billing + hardware in one tweet; taxonomy forces a single label.  
2. **Login vs security confusion** — “password changed / hacked” should be `privacy_security`, but login keywords pull `apple_id_login`.  
3. **Battery vs software_update** — “slow after update” straddles two intents; keyword overlap.  
4. **Escalation false negatives on polite refund asks** — if wording omits “refund/unauthorized”, billing may auto-handle incorrectly.  
5. **Retrieval mismatch on paraphrases** — SYN* golden lines aren’t in the retrieval index as customers; drafts lean on nearest template resolutions (OK for MVP, weak for faithfulness).

## What is misleading about my headline number?

**Any accuracy / F1 on this golden set overstates readiness for real AppleSupport traffic.** Reasons:

- Train and golden share the **same template family** (pattern_constructed + light paraphrases). This is closer to a **consistency check** than an i.i.d. test on organic tweets.  
- Synthetic lexical diversity is limited; TF-IDF memorizes cue phrases that real users paraphrase more wildly.  
- Escalation labels follow the **same rule spirit** as the escalation module → agreement is partly **circular**.  
- Dry-run “LLM judge” scores are **fixtures**, not GPT judgments — never headline them.  
- No temporal split, no author split, no live A/B, no CSAT. A number like “0.8 macro-F1” here means “fits our seed,” not “solves support.”

**Honest use of the number:** track regressions while iterating on taxonomy/rules; replace with human-labelled organic data before any launch claim.

## Judge–human agreement

`evaluate` reports Pearson-r and within-1 agreement. In dry-run, “human” scores are **rounded mock-judge values** (placeholder). For a real section: rate 30 drafts on the same 1–5 overall rubric, then re-run with paired scores. Expect modest correlation; do not claim alignment from n&lt;30.

## Next week

1. Replace/augment golden with **≥150 human-labelled organic** tweets (even if sampled from publicly shared screenshots / research dumps with license check).  
2. Add **embeddings + LR / linear SVM** baseline and confusion-matrix driven taxonomy merges.  
3. Learned escalation head (logistic on intent probs + regex features) with calibrated thresholds per intent.  
4. True LLM judge + 2-annotator agreement study; publish κ and disagreement examples.  
5. Hardening: PII scrubbing, jailbreak-style user text, and “do not invent coverage” eval unit tests.  
6. Tiny Streamlit or CLI review UI for ops to accept/edit drafts before send.

## Reproducibility

```bash
python -m hiver_agent prepare-data
python -m hiver_agent train --method tfidf
python -m hiver_agent evaluate --dry-run --judge-sample 20
# see artifacts/eval_report.json
```
