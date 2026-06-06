# Elder Shield

Multi-agent protection system that detects elder fraud through behavioral analysis, social graph inference, and outbound interception. Built on Google ADK 2.0 with Gemini.

## The Problem

Elder fraud costs **$77.7 billion globally** (Nasdaq 2024). Japan's tokushu sagi losses hit **\u00a51.4 trillion** in 2025 -- a record. The FBI reports **$7.7 billion** in US elder fraud losses the same year, **up 37% YoY**. Every existing protection system classifies messages one at a time. None detect the multi-day trust-building campaigns that cause the largest losses.

## What Makes This Different

- **Behavioral velocity detection** -- flags trust-building patterns BEFORE any scam signal appears. The system detects danger at Day 4 of a 7-day attack, 3 days before the money ask, based on relationship velocity alone.
- **Social graph inference** -- builds contact networks from message history, cross-references identity claims across contacts, and structurally detects imposters who have no graph connection to anyone the user knows.
- **Elder abuse detection from trusted contacts** -- detects the same manipulation mechanics (isolation, financial control, authority escalation) regardless of whether the sender is a stranger or a known family member. References Japan's Elder Abuse Prevention Act (2006).
- **Outbound interception** -- catches the compliance signal ("I'll go to the bank tomorrow") between conversation and transaction. Blocks bank account numbers and transfer instructions leaving the user, not just scam messages arriving.

## Architecture: 8-Step Hardened Pipeline

The key insight: move intelligence OUT of the model and INTO pre-processing infrastructure. By the time Gemini sees the message, it already has metadata signals, extracted entities, corpus matches, and graph validation as context. The model confirms pre-computed signals — it doesn't reason from scratch.

```
  Inbound Message
       |
  ┌────┴─────────────────── PRE-LLM (no API calls) ─────────────────────┐
  │ Step 1: Linguistic Analysis                                          │
  │   → style fingerprint, manipulation density (urgency/guilt/flattery) │
  │ Step 2: Entity Extraction                                            │
  │   → names, relationships, amounts, locations, deadlines              │
  │ Step 3: Corpus Search (TF-IDF, 22,979 entries)                       │
  │   → similar known scams with relevance scores                        │
  │ Step 4: Social Graph Validation                                      │
  │   → graph distance, imposter detection, trust modifier               │
  └──────────────────────────────┬────────────────────────────────────────┘
                                 │ pre-computed context
                                 v
  ┌──────────────────── LLM (Gemini Flash Lite) ─────────────────────────┐
  │ Step 5: Per-Message Classification                                   │
  │   → given pre-computed evidence, what's your judgment?               │
  └──────────────────────────────┬────────────────────────────────────────┘
                                 │ classification + extracted facts
                                 v
  ┌──────────────────── POST-CLASSIFICATION ─────────────────────────────┐
  │ Step 6: Sender Profile Update (fact accumulation, graph building)     │
  │ Step 7: Behavioral Velocity Scoring (cross-message pattern analysis) │
  │ Step 8: Decision Synthesis (compound risk + evidence chain + routing) │
  │   → PASS / MONITOR / FLAG / BLOCK                                    │
  │   → Outbound Interceptor armed / Family Alerter triggered            │
  └──────────────────────────────────────────────────────────────────────┘
```

Steps 1-4 run **before the LLM** — pure infrastructure, no API calls, ~50ms total. This is what enables running on the cheapest Gemini model: the model's job is simpler because the infrastructure did the heavy lifting.

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
  Pre-ADK:        Yes (at Day 7, when "send me ¥500,000" arrives)
  Elder Shield:  Yes (at Day 3, from behavioral velocity alone)

"Did you catch it BEFORE the money request?"
  Pre-ADK:        No — only catches the explicit ask
  Elder Shield:  Yes — flagged 3 days earlier

"What if the scammer calls grandma on the phone for the close?"
  Pre-ADK:        Misses entirely — never sees the phone call
  Elder Shield:  Already flagged — family was alerted at Day 3
```

This is the difference between catching a scam and **preventing** one. A system that flags at Day 7 is documenting a crime. A system that flags at Day 3 is preventing it.

### What changed: capability, not just accuracy

A single-message classifier -- no matter how good the model -- structurally cannot detect trust-building attacks. Each individual message in a 7-day scam sequence is genuinely safe. The improvement isn't a better F1 score. It's capabilities that didn't exist before:

| Capability | Pre-ADK Tuning | Elder Shield |
|---|---|---|
| Obvious scam detection | Yes | Yes |
| Multi-day trust-building detection | **Impossible** — no cross-message state | **Day 4 flag** (3 days before money ask) |
| Imposter detection | **No** — no contact network | **Yes** — graph distance, cross-referencing |
| Outbound interception | **No** — inbound only | **Yes** — catches compliance signals |
| Elder abuse from known contacts | **No** — trusted = whitelisted | **Yes** — EA signals detect manipulation |
| Evidence-backed classification | **No** — prompt-only | **Yes** — 22,979 corpus entries cited |
| Adaptive per-user baselines | **No** — population thresholds | **Yes** — learns each user's normal |

### We optimized the system, not just the model

Both systems below run on the **same model** (gemini-3.1-flash-lite) at the **same cost**. The difference is entirely in the infrastructure we built around it:

| | Pre-ADK Tuning | Tuned Elder Shield |
|---|---|---|
| **Model** | gemini-3.1-flash-lite | gemini-3.1-flash-lite |
| **Per-message F1** | 0.933 | 0.923 |
| **Recall (scams caught)** | 1.000 | **1.000** |
| **Early detection** | Day 7 only | **Day 3** |
| **Imposter detection** | No | **Yes** |
| **Outbound interception** | No | **Yes** |
| **Elder abuse detection** | No | **Yes** |
| **Evidence-backed** | No | **Yes (22,979 corpus)** |

Per-message F1 drops 0.01 — because each hardening round moved intelligence OUT of the model and INTO the infrastructure (corpus search, social graph, adaptive baselines, signal weights). The model's job got simpler. The system got smarter.

This is the ADK optimization story: we didn't need a bigger model. We needed better tools, better data, and better architecture. The cheapest Gemini model now does what the most expensive model couldn't do alone — detect trust-building attacks 3 days before the money request.

### Corpus search: from zero matches to evidence-backed

Upgraded from Jaccard bag-of-words to dual TF-IDF (word + character n-gram). Japanese queries that returned zero results now find relevant corpus matches:

| Query | Before (Jaccard) | After (TF-IDF) |
|---|---|---|
| Japanese ore-ore sagi | 0.111 relevance | **0.297** (+168%) |
| Japanese billing scam | 0 matches | **0.518** (new) |
| Subtle trust-building | 0 matches | **0.264** (new) |
| Romance pattern | 0 matches | **0.136** (new) |
| Japanese safe message | 0 matches | **0.521** (new) |

5 of 7 test queries went from zero corpus evidence to relevant matches. The classifier's grounding went from "my prompt says so" to "this matches confirmed cases in our corpus."

## Demo

Live at [shield.faxi.jp](https://shield.faxi.jp):

- **/shield** -- Overview with trust-building scam walkthrough, real eval results, and architecture explanation.
- **/simulator** -- Interactive "Test the Shield" — send messages and watch the protection system respond in real time via live Gemini.
- **/dashboard** -- Family safety dashboard with quarantine inbox, risk timeline, contact graph visualization, and protection summary.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | Google ADK 2.0 (Python) |
| Model (all agents) | Gemini 3.1 Flash Lite — cheapest model, infrastructure does the heavy lifting |
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
