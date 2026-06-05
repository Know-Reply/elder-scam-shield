# Elder Scam Shield

Multi-agent scam protection for elderly Japanese users, built on Google ADK.

## The Problem

Elder fraud in Japan hit **¥324 billion** in 2025 — a **4.5x year-over-year increase** across 42,900 cases. Existing defenses classify messages one at a time. They catch obvious scams but miss trust-building attacks where a scammer spends days posing as a grandchild before requesting money.

A single-message classifier catches **1 of 7** messages in a romance scam sequence. Elder Scam Shield catches **7 of 7** with zero false positives on legitimate mail.

## Architecture

Four agents connected via A2A events:

```
  Inbound Message
       │
       ▼
┌──────────────┐   message.classified   ┌─────────────────────┐
│   Inbound    │ ─────────────────────▶ │    Behavioral       │
│  Classifier  │   (facts + signals)    │     Analyzer        │
│   [SENSE]    │                        │ [INTERPRET + JUDGE] │
└──────────────┘                        └─────────┬───────────┘
                                                  │
                                    sender.risk_updated
                                                  │
       ┌──────────────────────────────────────────┤
       ▼                                          ▼
┌──────────────┐                        ┌─────────────────────┐
│   Outbound   │   outbound.held        │      Family         │
│ Interceptor  │ ─────────────────────▶ │      Alerter        │
│   [JUDGE]    │                        │     [CREATE]        │
└──────────────┘                        └─────────────────────┘
       ▲
       │
  Outbound Message
  (user's reply)
```

**Inbound Classifier** — detects 13 per-message signals grounded in NPA tokushu-sagi taxonomy. Extracts stated facts from every message, even safe ones.

**Behavioral Analyzer** — builds longitudinal sender profiles. Detects contradictions (claimed Osaka, then Tokyo), cross-references against known contacts (grandson is Takeshi, not Kenji), tracks emotional progression and financial mention timing.

**Outbound Interceptor** — catches sensitive data leaving the user. Bank account numbers, transfer instructions, PII in replies to flagged senders. Content is hashed for audit, never stored.

**Family Alerter** — translates detections into warm, actionable Japanese notifications for designated family members.

## What Makes This Different

1. **Sender profile contradiction detection** — extracts facts from every message, builds profiles, catches when stories don't add up. Per-message classifiers cannot do this.
2. **Outbound interception** — catches the victim sending bank details out, not just blocking scam messages in. Operates at the communication layer, between conversation and transaction.
3. **Cross-modal signal correlation** — sees both the conversation and the spending in one system. Banks see transactions but not conversations. Email providers see the reverse.
4. **"Never show the content"** — does not warn; it shields. A warning on a fake grandchild plea gets acted on by elderly users. We prevent scam content from reaching the user entirely.

## Quick Start

```bash
pip install google-adk google-cloud-firestore
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_API_KEY=your-gemini-api-key
adk run agents/
```

## Demo

Live demo: [shield.faxi.jp/demo](https://shield.faxi.jp/demo)

Walks through a 7-day romance scam sequence — from first "grandma, it's Kenji" through location contradictions and contact mismatch to the final blocked money request — with agent reasoning traces visible at each step.

## Tech Stack

| Component | Technology |
|---|---|
| Agent framework | Google ADK 2.0 (Python) |
| LLM | Gemini 2.0 Flash / Gemini 2.5 Pro |
| Memory Bank | Cloud Firestore |
| Deployment | Google Cloud Run |
| Grounding | Vertex AI |
| Protocol | A2A (Agent-to-Agent) |

## Data Sources

- [Romance scam dialogue dataset](https://arxiv.org/html/2512.16280v1) — 250 seven-day conversations
- [Scam call conversation dataset](https://www.kaggle.com/datasets/teeconnie/scam-and-non-scam-call-conversation-dataset) — multi-turn scam vs legitimate
- [Fraud email corpus](https://www.kaggle.com/datasets/rtatman/fraudulent-email-corpus) — Nigerian-style fraud emails
- [NPA tokushu sagi statistics](https://www.nippon.com/en/japan-data/h02424/) — ¥324B losses, pattern taxonomy
- [Elder exploitation risk profiles](https://catalog.data.gov/dataset/exploring-elder-financial-exploitation-victimization-identifying-unique-risk-profiles-2009-0e58c) — 8,800 confirmed cases
- [Scam vulnerability study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9358277/) — psychosocial characteristics of elderly Japanese victims

## Built For

**Google for Startups AI Agents Challenge** — Track 2: Optimize (harden existing agent for production). APAC region.

Built by the team behind [Faxi](https://faxi.jp) — an AI-powered fax-to-internet bridge for elderly Japanese users.

## License

Apache 2.0 — see [LICENSE](LICENSE).
