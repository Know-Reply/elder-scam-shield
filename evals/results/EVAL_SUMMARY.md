# Elder Shield Evaluation Results

## Overview

51 of 52 longitudinal scenarios evaluated. Each scenario runs a multi-message conversation through both Elder Shield (risk ledger + LLM signal detection) and a naive baseline (LLM classification only, no tools, no corpus, no ledger).

**Run date:** 2026-06-09

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
| **Elder Shield** | **63.6%** |
| Naive Baseline | 34.7% |
| **Improvement** | **+28.9 pp** |

### False Positive Rate (legitimate messages incorrectly flagged)

| System | False Positives | Rate |
|--------|----------------|------|
| **Elder Shield** | **0 / 12** | **0%** |
| Naive Baseline | 5 / 12 | 42% |

Elder Shield never blocked a legitimate family request. The naive baseline flagged grandchild taxi money, family car emergencies, and real bank notifications as scams.

### Detection Behavior

| Metric | Elder Shield | Naive |
|--------|-------------|-------|
| Calls "scam" on first message | 35% | 75% |
| Scam scenarios eventually caught | 100% | 100% |

The naive baseline over-reacts — 75% of the time it calls "scam" on the very first message with no evidence accumulation. Elder Shield accumulates evidence across messages: safe at first, escalating through monitoring and suspicious to blocked as signals compound.

### Signal Detection Quality

| Metric | Value |
|--------|-------|
| Signal precision | 67.2% |
| Signal recall | 74.4% |

The LLM correctly identifies ~74% of expected signals and maintains 67% precision (low false signal rate).

## Architecture

Elder Shield separates detection from scoring:

1. **LLM** (Gemini flash-lite): Detects PM-1 through PM-13 signals + extracts facts. Does NOT classify.
2. **ConversationRiskLedger** (deterministic): Accumulates risk from LLM-detected signals across messages using:
   - Signal weights calibrated against NPA tokushu-sagi data (3 severity tiers)
   - Tier amplification (T1: 1.0x, T2: 1.4x, T3: 1.9x)
   - T1 primer bonus (1.3x when grooming signals precede escalation)
   - Sequence matching for known attack patterns (ore-ore 2.8x, authority 3.2x)
   - Score bands: safe (0-15%) → elevated (15-30%) → suspicious (30-50%) → high risk (50-75%) → blocked (75-100%)

The LLM never decides "safe" or "scam." Classification is derived from accumulated evidence through the risk ledger — predictable, testable, auditable.

## Notable Scenarios

**oreore_slow_6msg** (6 messages, slow grooming):
- Messages 1-3: SAFE — identity claim and casual conversation
- Message 4: Elder Shield detects at MONITORING — emotional crisis appears
- Message 6: BLOCKED — ore-ore sequence confirmed
- Naive: calls SCAM on message 0

**legit_grandchild_money** (legitimate request):
- "Grandma, forgot my wallet. Can you lend 2000 yen for taxi?"
- Elder Shield: SAFE (score 1.33) — correctly identifies mundane request
- Naive: SCAM — false positive that would block a real grandchild

**authority_en_irs** (IRS impersonation):
- Elder Shield: accumulates to SCAM (score 8.14) by message 3
- Shows authority sequence match with 3.2x multiplier
