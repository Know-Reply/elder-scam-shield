# Elder Scam Shield

Multi-agent protection system that detects elder fraud through behavioral analysis, social graph inference, and outbound interception. Built on Google ADK 2.0 with Gemini.

## The Problem

Elder fraud costs **$77.7 billion globally** (Nasdaq 2024). Japan's tokushu sagi losses hit **\u00a51.4 trillion** in 2025 -- a record. The FBI reports **$7.7 billion** in US elder fraud losses the same year, **up 37% YoY**. Every existing protection system classifies messages one at a time. None detect the multi-day trust-building campaigns that cause the largest losses.

## What Makes This Different

- **Behavioral velocity detection** -- flags trust-building patterns BEFORE any scam signal appears. The system detects danger at Day 4 of a 7-day attack, 3 days before the money ask, based on relationship velocity alone.
- **Social graph inference** -- builds contact networks from message history, cross-references identity claims across contacts, and structurally detects imposters who have no graph connection to anyone the user knows.
- **Elder abuse detection from trusted contacts** -- detects the same manipulation mechanics (isolation, financial control, authority escalation) regardless of whether the sender is a stranger or a known family member. References Japan's Elder Abuse Prevention Act (2006).
- **Outbound interception** -- catches the compliance signal ("I'll go to the bank tomorrow") between conversation and transaction. Blocks bank account numbers and transfer instructions leaving the user, not just scam messages arriving.

## Architecture

```
  Inbound Message
       |
       v
+-----------------+   message.classified   +----------------------+
|    Inbound      | ---------------------> |    Behavioral         |
|   Classifier    |   (facts + signals)    |     Analyzer          |
| gemini-3.1-     |                        | gemini-3.5-flash      |
|   flash-lite    |        +---------------+----------+-----------+
+-----------------+        |                          |
                           v                          v
                  +----------------+        sender.risk_updated
                  |  Graph Builder |                   |
                  |  (5-layer      |     +-------------+-------------+
                  |   inference)   |     v                           v
                  +-------+--------+ +------------------+ +-------------------+
                          |          |    Outbound       | |     Family        |
                          v          |   Interceptor     | |     Alerter       |
                  +----------------+ | gemini-3.1-       | | gemini-3.1-       |
                  | Corpus Search  | |   flash-lite      | |   flash-lite      |
                  | (22,979 entries)| +------------------+ +-------------------+
                  +----------------+        ^
                                            |
                                      Outbound Message
                                      (user's reply)
```

Four agents connected via A2A event routing. The Graph Builder and Corpus Search are shared tools, not agents.

## The Optimization Story (Track 2)

Six rounds of iterative hardening, each compounding on the last:

| Round | Focus | Key Outcome | Platform Tool |
|-------|-------|-------------|---------------|
| 1 | Basic classifier, 8-category taxonomy | F1 0.933 baseline | ADK agent definition |
| 2 | Behavioral velocity (BV-1..5) | Day 4 early detection, 3 days before money ask | Agent Evaluation |
| 3 | Corpus grounding (22,979 entries, 7 sources) | Evidence-backed classification | Vertex AI Search |
| 4 | Social graph validation | Imposter detection against contact network | Agent Simulation |
| 5 | Adaptive baselines + elder abuse signals (EA-1..4) | False positive reduction (6 to 5) | Memory Bank |
| 6 | Family safety dashboard | Human-in-the-loop proof of intervention | -- |

## Behavioral Sequence: The Hero Test

A trust-building scam over 7 days. The Behavioral Analyzer measures velocity (rate of change), not duration. A 3-day compressed attack triggers faster; a 30-day romance scam accumulates the same signals more slowly.

```
Day 1  "Grandma, it's Kenji"          risk: 0.18  (greeting from unknown number)
Day 2  "How are you feeling?"          risk: 0.32  (rapport building, credibility seeding)
Day 3  "I moved to Osaka for work"     risk: 0.50  (establishing backstory)
Day 4  "Things are tough financially"  risk: 0.75  ** FLAGGED -- trust-building pattern **
Day 5  "Can you help with rent?"       risk: 0.90  (financial request)
Day 6  "Here's my bank account"        risk: 0.95  (transaction details)
Day 7  Reply with bank transfer        BLOCKED by Outbound Interceptor
```

The system flags at **Day 4** -- before any explicit scam signal -- based on behavioral velocity alone.

## Social Graph: How Contact Networks Are Built

Five-layer inference builds the graph from communication, not manual entry:

1. **Message history** -- anyone with 3+ months of reciprocal messaging becomes a known contact. Frequency, reciprocity, and formality are tracked.
2. **Relationship extraction** -- when grandma's message says "Yuki is coming next week," the system infers a Yuki-grandma edge. When daughter says "I'll go with Yuki," the edge is corroborated from both sides.
3. **Cross-referencing** -- a sender mentioned by 2+ verified contacts is RECOGNIZED. A sender mentioned by 1 is CORROBORATED. A sender mentioned by nobody is UNCONNECTED.
4. **Community detection** -- contacts cluster into natural groups (family, neighborhood, medical, commercial) based on mutual references and formality patterns. Japanese keigo level encodes relationship hierarchy -- a "grandson" using honorific language instead of casual speech is structurally suspicious.
5. **Anomaly detection** -- claiming to be "Tanaka's son" means nothing if Tanaka's node has no edge to the sender. Graph distance determines trust: known contacts get risk reduction (-0.2), unconnected senders claiming relationships get risk boost (+0.3).

Confidence levels: VERIFIED > OBSERVED > ESTABLISHED > RECOGNIZED > CORROBORATED > INFERRED > CLAIMED > UNCONNECTED.

## Results

### The metric that matters: WHEN, not IF

Both systems eventually catch the scam. The question is when — and what happens if the scammer goes offline for the close.

```
"Did you catch the scam?"
  Traditional:        Yes (at Day 7, when "send me ¥500,000" arrives)
  Elder Scam Shield:  Yes (at Day 3, from behavioral velocity alone)

"Did you catch it BEFORE the money request?"
  Traditional:        No — only catches the explicit ask
  Elder Scam Shield:  Yes — flagged 3 days earlier

"What if the scammer calls grandma on the phone for the close?"
  Traditional:        Misses entirely — never sees the phone call
  Elder Scam Shield:  Already flagged — family was alerted at Day 3
```

This is the difference between catching a scam and **preventing** one. A system that flags at Day 7 is documenting a crime. A system that flags at Day 3 is preventing it.

### What changed: capability, not just accuracy

A single-message classifier -- no matter how good the model -- structurally cannot detect trust-building attacks. Each individual message in a 7-day scam sequence is genuinely safe. The improvement isn't a better F1 score. It's capabilities that didn't exist before:

| Capability | Traditional (single classifier) | Elder Scam Shield |
|---|---|---|
| Obvious scam detection | Yes | Yes |
| Multi-day trust-building detection | **Impossible** — no cross-message state | **Day 4 flag** (3 days before money ask) |
| Imposter detection | **No** — no contact network | **Yes** — graph distance, cross-referencing |
| Outbound interception | **No** — inbound only | **Yes** — catches compliance signals |
| Elder abuse from known contacts | **No** — trusted = whitelisted | **Yes** — EA signals detect manipulation |
| Evidence-backed classification | **No** — prompt-only | **Yes** — 22,979 corpus entries cited |
| Adaptive per-user baselines | **No** — population thresholds | **Yes** — learns each user's normal |

### Classification accuracy (80-case eval, live Gemini)

| Metric | Traditional | Elder Scam Shield | Delta |
|--------|-------------|-------------------|-------|
| F1 Score | 0.933 | **0.944** | +0.011 |
| Precision | 0.875 | **0.894** | +0.019 |
| Recall | 1.000 | **1.000** | 0.000 |
| False Positives | 6 | **5** | -1 |

The F1 improvement is modest because Gemini is already good at per-message classification. **The real gain is structural** -- 20 detection signals across 4 families (LG, BV, EA, CM) that operate across messages, contacts, and time. A single classifier cannot access these dimensions regardless of prompt quality.

## Demo

Live at [shield.faxi.jp](https://shield.faxi.jp):

- **/shield** -- Overview with trust-building scam walkthrough, real eval results, and architecture explanation.
- **/simulator** -- Interactive "Can You Scam Grandma?" with live Gemini classification. Write a scam message, watch it get classified in real time.
- **/dashboard** -- Family safety dashboard with quarantine inbox, risk timeline, contact graph visualization, and protection summary.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | Google ADK 2.0 (Python) |
| Gate model | Gemini 3.1 Flash Lite |
| Analysis model | Gemini 3.5 Flash |
| Memory | Cloud Firestore |
| Corpus grounding | Vertex AI Search + local Jaccard fallback |
| Deployment | Google Cloud Run |
| Protocol | A2A (Agent-to-Agent) events |

## Data

22,979 corpus entries across 8 scam categories from 7 sources. 57% legitimate / 43% scam split. Signal weights derived from corpus analysis, not hand-tuned.

| Source | Entries | Type |
|--------|---------|------|
| zefang-liu/phishing-email-dataset | 17,514 | Real phishing + safe emails |
| BothBosu/scam-dialogue + multi-agent | 3,200 | Multi-turn phone/chat transcripts |
| cybersectony/PhishingEmailDetectionv2.0 | 1,254 | Real phishing + legitimate emails |
| antiphishing.jp | 203 | Real Japanese phishing reports |
| NPA SOS47 dialogues | 44 | Real police-published scam scripts |
| Synthetic NPA scenarios | 162 | Japanese scam scenarios (3 difficulty levels) |
| Synthetic edge cases | 12 | Bilingual, ambiguous test cases |

Full provenance chain in [DATA_PROVENANCE.md](data/DATA_PROVENANCE.md). NPA pattern re-tagging uses deterministic regex, not LLM inference.

## Family Alerter UX

The Family Alerter never uses the word "scam" in notifications. In Japanese elder care, telling a daughter "scam detected" triggers a panic confrontation. The mother feels surveilled, turns the system off, and the system causes the damage the scam would have.

Instead:
- Subject lines read "A new contact -- please review" not "Scam alert."
- Action scripts give concrete 30-second instructions: "Ask casually: who have you been talking to lately? Listen -- don't lead."
- Every alert asserts what the elder did NOT see: "Your mother did not see this message."
- Silent blocks include a monthly counter: "3rd block this month, all resolved."

This is dignity-preserving design. The elder's autonomy is never undermined.

## Adversarial Edge Cases

12 scenarios across 4 categories, developed with external review:

- **3 legitimate-looking scammy** -- real grandchild emergency in scam-shape language, legitimate bank fraud alert, family member asking for WiFi password
- **4 sophisticated evasions** -- 30-day slow-burn under velocity thresholds, family insider with phone access, cross-platform persona, LLM-cloned voice
- **3 system trust collapse** -- self-fulfilling fear loop, counter-system social engineering, held legitimate time-sensitive message
- **2 discipline collisions** -- elder requests to see held messages, held message costs critical access

7 are runnable tests. 3 are documented honest-fails with known limitations named. We document what we cannot catch.

## Quick Start

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=your-gemini-api-key
export GOOGLE_CLOUD_PROJECT=your-project-id
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

## Project Structure

```
agents/
  root_agent.py            # Root orchestrator with A2A event routing
  inbound_classifier.py    # Per-message signal extraction (20 signals)
  behavioral_analyzer.py   # Longitudinal sender profiling (BV + EA + LG)
  outbound_interceptor.py  # Outbound data interception
  family_alerter.py        # Bilingual family notification generation
  tools/
    graph_builder.py       # Social graph inference from message history
    social_graph.py        # Graph validation and imposter detection
    search_scam_corpus.py  # Corpus grounding (Vertex AI Search + local)
data/
  processed/               # 22,979-entry corpus (JSONL)
  raw/                     # Original source data
  DATA_PROVENANCE.md       # Full data transparency
  CORPUS_VALIDATION_REPORT.md
evals/
  scam_detection_full.evalset.json   # 80-case eval suite
  run_evaluation.py        # Eval runner
  results/                 # Eval results with metrics
scenarios/
  demo_7day.json           # 7-day romance scam demo scenario
  adversarial_edge_cases.json  # 12 adversarial scenarios
web/
  dashboard.html           # Family safety dashboard
  demo-walkthrough.html    # Shield overview page
  index.html               # Interactive scam simulator
app.py                     # FastAPI application (/shield, /simulator, /dashboard, /api/*)
```

## License

Apache 2.0 -- see [LICENSE](LICENSE).

## Built For

**Google for Startups AI Agents Challenge** -- Track 2: Optimize. APAC region.

Built by the team behind [Faxi](https://faxi.jp) -- an AI-powered fax-to-internet bridge for elderly Japanese users.
