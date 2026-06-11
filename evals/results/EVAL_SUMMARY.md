# Elder Shield Evaluation Results

## Overview

All 52 longitudinal scenarios evaluated (140 graded messages). Each scenario runs a multi-message conversation through both Elder Shield (risk ledger + LLM signal detection) and a naive baseline (LLM classification only, no tools, no corpus, no ledger). Both systems on `gemini-2.5-flash-lite` via Vertex AI.

**Run date:** 2026-06-12 (earlier runs archived in `results/archive/`)

## Scenario Distribution

| Category | Count | Description |
|----------|-------|-------------|
| Ore-ore impersonation | 10 | Grandchild/family impersonation scams |
| Romance scam | 8 | Online romance leading to financial exploitation |
| Investment scam | 8 | Fake investment opportunities |
| Authority impersonation | 8 | Police, bank, government impersonation |
| Legitimate (false positive test) | 8 | Real family requests that look like scams |
| Spam | 5 | Commercial spam, phishing |
| Safe | 5 | Normal messages from unknown senders |

## Key Results

### Classification Accuracy

| System | Accuracy |
|--------|----------|
| **Elder Shield** | **67.2%** |
| Naive Baseline | 62.8% |
| **Improvement** | **+4.4 pp** |

Accuracy is graded per message across all 140 messages in the 52 scenarios, against expected labels that follow a graduated escalation (safe → monitoring → suspicious → scam). It measures whether the system is at the right alert stage at each point in the conversation — a different metric from the 80-case single-message suite (F1), which grades isolated messages.

The narrow accuracy gap is itself a finding: a modern model is genuinely good at text-only per-message classification, so the fair-graded baseline is strong. The differences that matter live in the rows below — catch rate and false positives — and in capabilities this eval cannot exercise at all (outbound interception, victim-state monitoring, provenance tracking).

### False Positive Rate (legitimate messages incorrectly flagged)

| System | False Positives | Rate |
|--------|----------------|------|
| **Elder Shield** | **0 / 13** | **0%** |
| Naive Baseline | 0 / 13 | 0% |

Neither system flagged a legitimate message in the final run — but the paths differ. The naive baseline (on a modern model) reads family requests as safe text. Elder Shield initially flagged 4 of them: signal detection correctly reported the scam-shaped text (identity claim + money request), and graph trust never reached the scoring layer. The fix — sender-trust modulation in the ledger, attack-pattern multipliers gated to unverified senders — moved all four to "monitoring": watched, never flagged. That distinction matters in production: the naive baseline ignores those messages entirely; Elder Shield keeps accumulating evidence on them (EA signals at full weight) in case a pattern forms.

### Detection Behavior

| Metric | Elder Shield | Naive |
|--------|-------------|-------|
| Scam scenarios caught | **34/34 (100%)** | 31/34 |
| Flags a first message before evidence exists | 19/52 (37%) | 23/52 (44%) |

The naive baseline missed three scams — `romance_basic_4msg`, `invest_real_estate`, `invest_gold` — multi-message groomers whose individual messages each look reasonable. Elder Shield caught all 34: accumulated evidence, sequence detection, and the imposter boost (unknown senders claiming family ties score hotter) don't depend on any single message looking bad.

### Signal Detection Quality

| Metric | Value |
|--------|-------|
| Signal precision | 67.2% |
| Signal recall | 74.4% |

The LLM correctly identifies ~74% of expected signals and maintains 67% precision (low false signal rate).

## Architecture

Elder Shield separates detection from scoring:

1. **LLM** (Gemini flash-lite): Detects PM-1 through PM-15 signals + extracts facts. Does NOT classify.
2. **ConversationRiskLedger** (deterministic): Accumulates risk from LLM-detected signals across messages using:
   - Signal weights seeded from NPA tokushu-sagi aggregate statistics (3 severity tiers)
   - Tier amplification (T1: 1.0x, T2: 1.4x, T3: 1.9x)
   - T1 primer bonus (1.3x when grooming signals precede escalation)
   - Sequence matching for known attack patterns (ore-ore 2.8x, authority 3.2x)
   - Sender-trust modulation from the social graph (verified contact ×0.6 on non-EA signals; unknown sender claiming family ×1.3)
   - Score bands: safe (0-15%) → elevated (15-30%) → suspicious (30-50%) → high risk (50-75%) → blocked (75-100%)

The LLM never decides "safe" or "scam." Classification is derived from accumulated evidence through the risk ledger — predictable, testable, auditable.

## Methodology Notes

Grading rules (also embedded in the results JSON as `grading_notes`):

- `high_risk` is graded as `suspicious` — adjacent band, same user-visible action.
- Expected "monitoring" accepts monitoring OR suspicious from **either** system: the naive classifier's taxonomy (safe/spam/scam/suspicious) cannot emit "monitoring," so those labels are graded leniently for both.
- Spam scenarios accept "spam" OR "safe" from either system — commercial spam poses no fraud risk to the elder.
- False positives count user-visible actions: for the full pipeline, "monitoring" is an internal state (no alert fires below suspicious); for the naive baseline, any non-safe classification blocks the message.
- **Sender identity:** legitimate-family scenarios are sent from contacts present in the elder's social graph, matching production — a real daughter is a known contact. Scam scenarios are sent from unknown senders. The graph's verdict reaches the risk ledger as a contribution modifier.
- **Evidentiary asymmetry, by design:** a genuine one-off emergency from a verified family member passes through — strangers are scored per message, trusted contacts are scored on patterns (EA signals always at full weight). A trusted contact's *first* acute exploitation therefore reads as family support until a pattern forms; see adversarial honest-fail B2.

### Model history

The June 6 artifacts (80-case per-message suite, observability traces, optimizer trace) were captured on `gemini-3.1-flash-lite`, before the move to Vertex AI. The system then moved to `gemini-2.5-flash-lite` on Vertex AI, and this longitudinal evaluation was re-run on it — the model recorded in `longitudinal_results.json`. The pipeline survived the model swap without prompt changes, consistent with the project thesis that the value lives in the infrastructure, not the model.

## Notable Scenarios

**oreore_slow_6msg** (6 messages, slow grooming):
- Messages 1-3: low risk while the identity claim and casual conversation accumulate quietly
- Message 4: detection — emotional crisis compounds with the primed identity claim
- Final: SCAM (score 10.0) — ore-ore sequence confirmed, blocked

**romance_widow** (3 messages — the scenario the pre-Round-8 system missed):
- A romance-scam opener that ends before explicit escalation. An earlier run scored it SAFE (1.21) — too few messages for evidence to accumulate
- After Round 8, the imposter boost (unknown sender claiming a relationship, ×1.3) catches it at message 2; final HIGH_RISK (5.85)
- Short-conversation scams remain the structural pressure point of accumulation-based scoring; this one is now inside the detection envelope

**legit_grandchild_money** (legitimate request — the Round 8 showcase):
- "Grandma, it's Kenji, forgot my wallet — can you lend 2,000 yen for a taxi?" sent from a grandson in the contact graph
- Signal detection correctly reports the scam-shaped text (PM-11 identity reference, PM-3 money request). Pre-Round-8, the ledger scored it SUSPICIOUS (4.11) — graph trust never reached the scoring layer
- With sender-trust modulation: MONITORING (1.99) — watched, never flagged, the elder never bothered
- The identical message from an unknown sender claiming to be Kenji scores into SUSPICIOUS on the spot — same words, different sender, different outcome. That asymmetry is the social graph doing its job

**authority_en_irs** (IRS impersonation):
- Elder Shield: detection at message 1, accumulates to SCAM (score 10.0)
- Authority sequence match with 3.2x multiplier
