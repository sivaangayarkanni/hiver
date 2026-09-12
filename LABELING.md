# Golden set labelling guide

## Purpose

The golden set (`data/golden/golden.jsonl`, **200 examples**) evaluates:

| Field | Meaning |
|-------|---------|
| `intent` | One of the 11 canonical intents in `src/hiver_agent/intents.py` |
| `should_escalate` | Whether a human should take over before / instead of auto-reply |
| `reference_reply` | Optional high-quality reply for judge grounding (not exact-match scored) |
| `source` | `pattern_constructed` (from sample threads) or `synthetic_seed` (extra paraphrases) |

**All examples in this MVP are constructed** from public AppleSupport-style Twitter patterns. They are **not** scraped rows from the Kaggle Customer Support on Twitter dataset. Treat them as a seed; replace/augment with human labels for production claims.

## Intent decision rules

1. Label the **primary** customer ask (first clear problem).  
2. If two intents are equally strong → `other` and `should_escalate=true`.  
3. Suspected account takeover / stolen device → `privacy_security` (even if login keywords appear).  
4. Pure how-to with no failure → `how_to`.  
5. Update *stuck/failed* → `software_update`; “phone slow after update” with battery focus → prefer `battery_performance` if battery is the complaint.

## Escalation decision rules

Mark `should_escalate=true` when any apply:

- Security, theft, phishing, unknown devices on Apple ID  
- Unauthorized charges / refund disputes / legal threats  
- Clear need for physical service (cracked screen, water damage, won’t power on)  
- Self-harm / crisis language (route to human; do not automate advice)  
- Multi-intent or too vague to safely auto-reply  
- Otherwise `false` for standard troubleshooting that an agent template can answer

## Quality bar for new labels

- Customer text should look like a real social post (typos OK, ≤280–400 chars typical).  
- Avoid leaking PII; use fake names/ids only.  
- Every example needs `intent` + `should_escalate`.  
- Spot-check 10% with a second annotator; target ≥0.7 Cohen’s κ before claiming human-quality eval.

## Regenerating seeds

```bash
python scripts/generate_sample_data.py
```

Then manually edit golden rows you disagree with — do not silently overwrite human labels.
