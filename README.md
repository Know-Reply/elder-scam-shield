# Elder Scam Shield

Multi-agent scam protection system that detects elder fraud through behavioral analysis, not keyword matching. Built on Google ADK 2.0.

## The Problem

Elder fraud is a **$77.7 billion global problem** (Nasdaq 2024). In Japan, tokushu sagi losses hit **¥1.4 trillion** in 2025 — a record high. The FBI reports **$7.7 billion** in US elder fraud the same year, **up 37% YoY**. Every system protecting these users today relies on per-message classification. None detect the multi-day trust-building campaigns that cause the largest losses.

A per-message classifier catches **1 of 7** messages in a romance scam sequence. Elder Scam Shield catches **7 of 7**.

## What Makes This Different

**Longitudinal behavioral analysis.** Every message updates a sender profile. When a sender claims Osaka on Day 1 and Tokyo on Day 3, the system flags the contradiction -- no single-message classifier can do this.

**Outbound interception.** Operates between conversation and transaction. Catches bank account numbers and transfer instructions leaving the user, not just scam messages arriving.

**Elder abuse detection from trusted contacts.** Detects financial control, isolation tactics, and authority escalation from known contacts -- the blind spot every spam filter has.

**"Never show content" design.** Does not warn; it shields. A warning on a fake grandchild plea gets acted on by elderly users. Scam content never reaches the user.

## Architecture

Four agents connected via A2A event routing, coordinated by a root orchestrator:

```
  Inbound Message
       |
       v
+-----------------+  message.classified  +----------------------+
|    Inbound      | ------------------> |    Behavioral         |
|   Classifier    |  (facts + signals)  |     Analyzer          |
| gemini-flash-lite|                     | gemini-2.5-flash      |
+-----------------+                     +----------+-----------+
                                                   |
                                     sender.risk_updated
                                                   |
       +-------------------------------------------+
       v                                           v
+-----------------+                     +----------------------+
|    Outbound     |  outbound.held      |      Family          |
|  Interceptor    | ------------------> |      Alerter         |
| gemini-flash-lite|                     | gemini-2.5-flash      |
+-----------------+                     +----------------------+
       ^
       |
  Outbound Message
  (user's reply)
```

**Inbound Classifier** -- per-message signal extraction across 20 detection signals. Fast gate model (gemini-3.1-flash-lite) keeps latency under 2s.

**Behavioral Analyzer** -- longitudinal sender profiles with 10 longitudinal signals (LG-1..10), 5 behavioral velocity signals (BV-1..5), and 4 elder abuse signals (EA-1..4). Detects contradictions, cross-references known contacts, tracks emotional progression.

**Outbound Interceptor** -- catches sensitive data leaving the user. Bank accounts, transfer instructions, PII in replies to flagged senders. Content is hashed for audit, never stored.

**Family Alerter** -- translates detections into actionable Japanese notifications for designated family members via the family safety dashboard.

## The Optimization Story (Track 2)

Six rounds of iterative hardening from baseline to production:

| Round | Focus | Outcome |
|-------|-------|---------|
| 1 | Basic classifier with 8-category taxonomy | F1 0.933 baseline |
| 2 | Behavioral velocity scoring (BV-1..5) | Day 4 early detection before any scam signal |
| 3 | Corpus grounding (22,979 entries, 7 sources) | Evidence-backed classification via Vertex AI Search |
| 4 | Social graph validation | Imposter detection against known contacts |
| 5 | Adaptive baselines + elder abuse signals | False positive reduction (6 -> 5) |
| 6 | Family safety dashboard | Human-in-the-loop proof of intervention |

### Behavioral Sequence: The Hero Test

A trust-building scam over 7 days — one of many timelines the system handles. The Behavioral Analyzer measures velocity (rate of change), not duration. A 3-day compressed attack triggers faster; a 30-day romance scam accumulates the same signals more slowly. This example shows the pattern:

```
Day 1  "Grandma, it's Kenji"          risk: 0.15  (greeting from unknown number)
Day 2  "How are you feeling?"          risk: 0.25  (rapport building)
Day 3  "I moved to Osaka for work"     risk: 0.40  (establishing backstory)
Day 4  "Things are tough financially"  risk: 0.75  ** FLAGGED -- trust-building pattern **
Day 5  "Can you help with rent?"       risk: 0.90  (financial request)
Day 6  "Here's my bank account"        risk: 0.95  (transaction details)
Day 7  Reply with bank transfer        BLOCKED by Outbound Interceptor
```

The system flags at **Day 4** -- before any explicit scam signal -- based on behavioral velocity alone.

## Results

80-case eval suite (55 Japanese + 20 English + 5 edge cases):

| Metric | Baseline | Optimized |
|--------|----------|-----------|
| F1 Score | 0.933 | **0.944** |
| Precision | 0.895 | **0.894** |
| Recall | 0.971 | **1.000** |
| False Positives | 6 | **5** |

Recall of 1.000 means zero scams missed in the eval suite. The precision trade-off (one additional false positive class) is acceptable -- a blocked legitimate message is recoverable; a successful scam is not.

## Demo

Live at [shield.faxi.jp](https://shield.faxi.jp):

- **/shield** -- overview with trust-building scam walkthrough and real eval results
- **/simulator** -- interactive "Can You Scam Grandma?" with live Gemini classification
- **/dashboard** -- family safety dashboard with quarantine inbox, risk timeline, contact graph

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | Google ADK 2.0 (Python) |
| Gate model | Gemini 3.1 Flash Lite |
| Analysis model | Gemini 2.5 Flash |
| Memory | Cloud Firestore |
| Corpus grounding | Vertex AI Search + local Jaccard fallback |
| Deployment | Google Cloud Run |
| Protocol | A2A (Agent-to-Agent) events |

## Data Sources

22,979 corpus entries from 7 sources with full provenance:

| Source | Type | Entries |
|--------|------|---------|
| [antiphishing.jp](https://www.antiphishing.jp/) | Real phishing reports (JP) | 730 |
| [NPA SOS47 dialogues](https://www.npa.go.jp/) | Real police transcripts (JP) | 44 |
| [Romance scam dialogues](https://arxiv.org/html/2512.16280v1) | Academic dataset | 250 |
| [Scam call conversations](https://www.kaggle.com/datasets/teeconnie/scam-and-non-scam-call-conversation-dataset) | Kaggle dataset | ~2,000 |
| [Fraud email corpus](https://www.kaggle.com/datasets/rtatman/fraudulent-email-corpus) | Kaggle dataset | ~4,000 |
| Generated edge cases | Synthetic (JP + EN) | ~15,900 |
| Legitimate messages | Synthetic baselines | ~100 |

8-category taxonomy organized by attack mechanics, not surface keywords.

## Quick Start

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=your-gemini-api-key
export GOOGLE_CLOUD_PROJECT=your-project-id
adk run agents/
```

## Project Structure

```
agents/
  root_agent.py           # Root orchestrator with A2A event routing
  inbound_classifier.py   # Per-message signal extraction
  behavioral_analyzer.py  # Longitudinal sender profiling
  outbound_interceptor.py # Outbound data interception
  family_alerter.py       # Family notification generation
  tools/                  # Shared agent tools
data/
  processed/              # 22,979-entry corpus
  raw/                    # Original source data
evals/
  scam_detection_full.evalset.json  # 80-case eval suite
  run_evaluation.py       # Eval runner
  results/                # Eval results with metrics
web/
  index.html              # Family safety dashboard
scenarios/
  demo_7day.json          # 7-day romance scam demo scenario
```

## License

Apache 2.0 -- see [LICENSE](LICENSE).

## Built For

**Google for Startups AI Agents Challenge** -- Track 2: Optimize. APAC region.

Built by the team behind [Faxi](https://faxi.jp) -- an AI-powered fax-to-internet bridge for elderly Japanese users.
