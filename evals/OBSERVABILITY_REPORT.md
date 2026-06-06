# Agent Observability Report

Generated: 2026-06-06  
Model: gemini-3.1-flash-lite via Vertex AI (global)  
Traces: 45 OpenTelemetry spans across 3 test cases  

## What We Traced

Three test cases through the Inbound Classifier with full OTel instrumentation:

1. **obvious_scam** — direct financial threat ("Send me $500 or I will sue")
2. **subtle_trust_builder** — Day 3 message with no explicit scam signals
3. **false_positive_grandson** — real grandson asking for tuition help

## What We Found

### Case 1: Obvious Scam — Clean Decision Path
- `search_scam_corpus` → found matches in advance-fee and billing-fraud categories
- Classification: **scam** (confidence 0.98)
- Signals: PM-1 (urgency), PM-3 (financial), PM-6 (legal threat)
- Decision was fast and confident — corpus evidence + multiple signals converge
- **No issues.** This is the easy case.

### Case 2: Subtle Trust-Builder — Correct Ambiguity
- `search_scam_corpus` → 0 matches (polite message doesn't match scam corpus)
- Classification: **safe** (confidence 0.95)
- Signals: none detected
- The classifier correctly identifies this as individually safe
- **Key insight:** Per-message classification CANNOT catch this. The danger is only visible across messages (Behavioral Analyzer territory).

### Case 3: False Positive Grandson — Where Reasoning Fails
- `search_scam_corpus` → found matches in impersonation category
- Classification: **suspicious** (confidence 0.65)
- Signals: PM-3 (financial mention), PM-11 (identity claim)
- **Failure analysis:** The classifier sees "grandchild + money" and flags it. It cannot verify the contact identity because `read_contact_list` returns empty (Firestore stubbed). In production, the Behavioral Analyzer would:
  1. Check the social graph → grandson is a verified contact (distance 0)
  2. Check adaptive baselines → this user's grandson messages monthly (normal)
  3. Apply graph risk modifier: -0.2 (known contact, long history)
  4. Result: SAFE (not suspicious)

## How We'd Fix the False Positive

The fix is architectural, not prompt-based:
- The **Inbound Classifier** correctly flags financial + identity signals
- The **Behavioral Analyzer** would clear it via graph validation + adaptive baselines
- This is exactly why a multi-agent system exists — the classifier is intentionally cautious, the analyzer provides context

## Platform Tool Usage

| Tool | What It Showed |
|---|---|
| **Agent Observability** (OTel) | 45 spans captured: tool calls, LLM requests/responses, token usage, timing |
| **Vertex AI integration** | All traces show `gcp.vertex.agent.*` attributes — running through Vertex, not AI Studio |
| **Tool call tracing** | Every `search_scam_corpus`, `write_classification`, `update_graph_from_message` call logged with args and responses |

## Span Statistics

- Total spans: 45 (15 per case)
- Tool calls per case: ~5 (search → classify → publish → graph_update)
- Average tokens per call: ~2,500 input, ~120 output
- Model: gemini-3.1-flash-lite via Vertex AI
