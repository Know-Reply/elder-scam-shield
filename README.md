# Elder Shield

Multi-agent protection system that detects elder fraud through behavioral analysis, social graph inference, and outbound interception. Built on Google ADK 2.0 with Gemini.

## The Problem

Elder fraud costs **$77.7 billion globally** (Nasdaq 2024). Japan's tokushu sagi losses hit **¥1.4 trillion** in 2025 -- a record. The FBI reports **$7.7 billion** in US elder fraud losses the same year, **up 37% YoY**. Every existing protection system classifies messages one at a time. None detect the multi-day trust-building campaigns that cause the largest losses.

## What Makes This Different

- **Behavioral velocity detection** -- flags trust-building patterns BEFORE any scam signal appears. The system detects danger at Day 4 of a 7-day attack, 3 days before the money ask, based on relationship velocity alone.
- **Social graph inference** -- builds contact networks from message history, cross-references identity claims across contacts, and structurally detects imposters who have no graph connection to anyone the user knows.
- **Elder abuse detection from trusted contacts** -- detects the same manipulation mechanics (isolation, financial control, authority escalation) regardless of whether the sender is a stranger or a known family member. References Japan's Elder Abuse Prevention Act (2006).
- **Outbound interception** -- catches the compliance signal ("I'll go to the bank tomorrow") between conversation and transaction. Blocks bank account numbers and transfer instructions leaving the user, not just scam messages arriving.
- **Victim state monitoring** -- analyzes the elder's *replies* for signs the scam is working. Compliance acceptance, secrecy adoption, financial commitment, emotional capitulation, urgency mirroring. Most systems watch what the scammer says. Elder Shield also watches whether the elder is falling for it.
- **Conversation knowledge graph with information provenance** -- tracks WHO revealed WHAT first. If grandma says "Kenji, is that you?" and the scammer then uses "Kenji" — the scammer didn't know the name. The elder gave it to them. Every fact is tagged: independent (the sender knew it) vs echo-grounded (the sender learned it from the elder). A scammer whose entire identity claim is built from facts the elder volunteered is structurally different from someone with genuine prior knowledge.

## Architecture: Detection / Scoring Separation

The key architectural insight: **the LLM detects signals, a deterministic ledger scores them**. The LLM never decides "safe" or "scam" — it finds signals and extracts facts. Classification is derived from accumulated evidence through the ConversationRiskLedger. Most LLM fraud systems ask the model "is this a scam?" and trust the answer. Our LLM is a sensor array, not a judge. The ledger is the judge — predictable, testable, auditable.

```
  Inbound Message
       |
  ┌────┴──────────────── PRE-LLM (pure Python, ~50ms) ───────────────────┐
  │ 1. Linguistic Analysis                                               │
  │   → style fingerprint, manipulation density (urgency/guilt/flattery) │
  │ 2. Corpus Search (TF-IDF, 22,979 entries)                            │
  │   → similar known scams with relevance scores                        │
  │ 3. Social Graph Validation + Contra-Indicator Check                  │
  │   → graph distance, imposter detection, legitimacy evidence          │
  └──────────────────────────────┬────────────────────────────────────────┘
                                 │ pre-computed context
                                 v
  ┌──────────────── LLM (Gemini Flash Lite, ~0.9s) ─────────────────────┐
  │ 4. Classification + Entity Extraction                                │
  │   → classify with pre-computed evidence; extract all facts           │
  └──────────────────────────────┬────────────────────────────────────────┘
                                 │ classification + extracted facts
                                 v
  ┌──────────── POST-CLASSIFICATION (Workflow agents, async) ────────────┐
  │ Behavioral Analyzer — longitudinal profiling, velocity scoring       │
  │ Conversation Knowledge Graph — provenance tracking, friction scoring │
  │ Family Alerter — triggered at 50% risk or elder Compromised                           │
  └──────────────────────────────────────────────────────────────────────┘
```

Steps 1-3 run **before the LLM** — pure Python, no API calls, ~50ms total. The LLM's job is simpler because it receives pre-computed evidence. Post-classification agents run asynchronously in the Workflow.

### Production Execution Model

The full pipeline is defined as an ADK Workflow DAG, but production execution separates the hot path from async analysis:

```
Hot path (per message, <1s):        Async path (per sender profile):
  Message → FunctionNode            Classification facts accumulate
    (Steps 1-4: pre-processing)       in sender profile via session state
  → Inbound Classifier (Agent)     → Behavioral Analyzer (Agent)
    output_key → session state        triggered by accumulated evidence
  → Response                       → Family Alerter (if risk > 50%)
```

The **Inbound Classifier** runs synchronously on every message — one LLM call, structured output via `output_schema`, results written to session state via `output_key`. The **Behavioral Analyzer** runs asynchronously against accumulated sender profiles, not raw messages. Same ADK agents, same session state, different execution timing.

This is a deliberate production scaling decision: the Workflow represents the full architecture, but routing every message through all agents sequentially would be the wrong design. The classifier responds in under 1 second — 12x faster than the original 7-tool LLM-routed approach. The behavioral analyzer needs accumulated cross-message evidence to be useful — running it on a single message wastes an LLM call.

### ADK Features Used

| Feature | Where | Purpose |
|---------|-------|---------|
| **Workflow + FunctionNode** | `root_agent.py` | DAG orchestration — deterministic pre-processing, conditional routing |
| **output_schema** | All agents | Pydantic-validated structured output (ClassificationResult, ExtractedFacts with ElderState, InterceptDecision, AlertRecord) |
| **output_key** | All agents | Writes results to session state for inter-agent data flow |
| **before_tool_callback** | Classifier, Analyzer | Native tool call tracing to session state |
| **after_model_callback** | Classifier | Runtime output validation |
| **before_model_callback** | Analyzer | Dynamic context injection from session state |
| **ADK Session State** | `app.py` | Longitudinal memory via `output_key` writes and `session.state` reads across agents |
| **Agent Search Data Store** | `search_scam_corpus.py` | 22,979-entry corpus with neural/semantic search — cross-language Japanese+English, no warm-up needed |
| **FunctionTool** | `search_scam_corpus` on Classifier | LLM can call corpus search for additional grounding evidence during classification |
| **Conditional routing** | Workflow edges | Risk-based fan-out to Family Alerter via 4-gate trigger system |
| **Multiple Runners** | `app.py` | Separate runners for classifier, naive baseline, extractor, pipeline, interceptor — baseline comparison baked into production code |

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
| 7 | Pre-processing pipeline (linguistic + TF-IDF + graph + contra-indicators → LLM classification) | Same F1 on cheapest model, 5 new capabilities | Agent Observability |

### How ADK tools drove the optimization

ADK didn't make the model better — it gave us the framework to build, measure, and validate a system that's better than any model alone:

- **Agent Evaluation** measured the baseline (F1 0.933) and validated every round. Without it, we'd be guessing.
- **Agent Simulation** proved Day 3 detection works across a 7-message trust-building sequence. No simulation = no proof the behavioral analyzer works.
- **Agent Observability** via ADK `before_tool_callback` showed us WHERE classification failed — tool call tracing, response validation, and context injection identified false positives on legitimate family messages. We traced the failures and fixed them.
- **Agent Optimizer** ran 5 iterations and couldn't beat our prompt — proving the value is in the infrastructure (tools, corpus, graph), not prompt wording.
- **Grounding** via corpus search gave the classifier evidence to cite instead of relying on prompt instructions alone.
- **Memory Bank** stores sender profiles, graph data, and baseline communication patterns across sessions.

## Behavioral Sequence: The Hero Test

A trust-building scam over 6 messages. The ConversationRiskLedger accumulates evidence with decay, tier amplification, and sequence detection. T1 signals (identity claim, flattery) are individually safe but activate a primer bonus when T2/T3 signals appear later — modeling the documented grooming-then-escalation pattern.

```
Msg 1  "Hi grandma, it's Takeshi"           risk: 3%   SAFE        (T1: identity claim noted)
Msg 2  "How's the clinic? I miss you"        risk: 3%   SAFE        (no new signals, score decays)
Msg 3  "My boss is great, work is good"      risk: 2%   SAFE        (still T1 only)
Msg 4  "Something bad happened at work"      risk: 19%  ELEVATED    (T2: emotional crisis, T1 primer activates)
Msg 5  "I need to pay back money, help?"     risk: 34%  SUSPICIOUS  ** FAMILY ALERTED ** (T3 signals compound)
Msg 6  "300K to this account, don't tell"    risk: 100% BLOCKED     (ore-ore sequence fires at 2.8x)
```

Messages 1-3 were individually safe. The system remembered them. When T2/T3 signals appeared, the primer bonus and ore-ore sequence multiplier compounded the accumulated evidence. A per-message classifier sees message 6 in isolation. The risk ledger sees the entire arc.

## Social Graph: How Contact Networks Are Built

Five-layer inference builds the graph from communication, not manual entry:

1. **Message history** -- anyone with 3+ months of reciprocal messaging becomes a known contact. Frequency, reciprocity, and formality are tracked.
2. **Relationship extraction** -- when grandma's message says "Yuki is coming next week," the system infers a Yuki-grandma edge. When daughter says "I'll go with Yuki," the edge is corroborated from both sides.
3. **Cross-referencing** -- a sender mentioned by 2+ verified contacts is RECOGNIZED. A sender mentioned by 1 is CORROBORATED. A sender mentioned by nobody is UNCONNECTED.
4. **Community detection** -- contacts cluster into natural groups (family, neighborhood, medical, commercial) based on mutual references and formality patterns. Japanese keigo level encodes relationship hierarchy -- a "grandson" using honorific language instead of casual speech is structurally suspicious.
5. **Anomaly detection** -- claiming to be "Tanaka's son" means nothing if Tanaka's node has no edge to the sender. Graph distance determines trust: known contacts get risk reduction (-0.2), unconnected senders claiming relationships get risk boost (+0.3).

Confidence levels: VERIFIED > OBSERVED > ESTABLISHED > RECOGNIZED > CORROBORATED > INFERRED > CLAIMED > UNCONNECTED.

## Conversation Knowledge Graph: Information Provenance

Most fraud detection systems ask: "is this message a scam?" Elder Shield asks: "who knows what, and how did they learn it?"

The conversation knowledge graph tracks every fact across both sides of the dialogue through three layers:

### Layer 1: Fact Ledger (Signal)

Append-only per turn. Every entity (name, location, institution, amount) is tagged with who stated it first and whether the other party echoed it.

```
Turn 0 (elder):  "Kenji, is that you?"     → name:健二 first_stated_by: elder
Turn 1 (sender): "Yes, it's Kenji! I'm in Osaka."  → name:健二 echo_detected: true, echo_by: sender
                                                     → location:大阪 first_stated_by: sender (independent)
```

The sender didn't know Kenji's name. The elder gave it to them. Every subsequent use of "Kenji" by the sender is echoed knowledge, not proof of identity.

### Layer 2: Epistemic State (Interpretation) — Elder's Guard

The elder's psychological trajectory: `Neutral → Opening Up → Vulnerable → Compromised`. Measured by **epistemic friction** — how much the elder resists new claims.

The LLM (fact extractor) detects five dimensions from each elder reply:
- **Compliance** (none/mild/strong) — agreeing to do what the sender asks
- **Resistance** (none/mild/strong) — challenging, questioning, pushing back
- **Disclosure** (none/mild/strong) — revealing personal information
- **Emotional engagement** (none/mild/strong) — concern FOR the sender
- **Instruction seeking** (boolean) — asking sender what to do (yielding control)

Plus VS-1 through VS-7 victim state signals: compliance acceptance, secrecy adoption, financial commitment, emotional capitulation, urgency mirroring, question cessation, deference shift.

A deterministic friction function scores these signals: strong resistance → +0.2 friction, strong compliance → -0.3 friction, instruction seeking → -0.2 friction. No keyword matching, no question mark counting — the LLM understands that "What should I do?" is compliance (yielding control) while "What do you mean?" is resistance (challenging). Across Japanese and English, any grammar, any synonym.

### Layer 3: Knowledge Graph (Interpretation)

Assembles the fact ledger and epistemic state into actionable signals:

- **Echo ratio** -- fraction of sender-stated facts that the elder introduced first. Above 0.6 = sender is mostly parroting the elder's own information.
- **Echo-grounded identity** -- the sender's identity claim is built entirely from facts the elder volunteered. Structurally different from someone with genuine prior knowledge.
- **Information asymmetry** -- `sender_echoing` (impersonation signal), `sender_knows_more` (suspicious independent knowledge), or `balanced`.

These signals feed directly into the risk assessment evidence chain.

### Research Foundations

The conversation knowledge graph draws on recent advances in epistemic logic and dialogue analysis:

- **Dynamic Epistemic Friction in Dialogue** (Gutiérrez-Basulto et al., 2025) -- operationalizes epistemic states and shows that friction reliably indicates how smoothly participants integrate new evidence. Our friction score implementation draws from this framework. [arXiv:2506.10934](https://arxiv.org/abs/2506.10934)
- **Joint Detection of Fraud and Concept Drift** (Sadat et al., 2025) -- treats concept drift and fraud detection together to avoid false positives from flagging normal topic changes. Our contra-indicator pipeline implements a similar dual-evidence approach. [arXiv:2505.07852](https://arxiv.org/abs/2505.07852)
- **Speaker-Oriented Dialogue Relation Extraction** (Yu et al., 2021) -- emphasizes tracking speaker-related information within dialogue context. Our fact provenance ledger implements speaker-attributed extraction at the turn level. [arXiv:2109.05182](https://arxiv.org/abs/2109.05182)

Full technical deep dive with all citations: [/technical](/technical)

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

### Longitudinal Evaluation: 52 Scenarios

51 of 52 scenarios evaluated — each a multi-message conversation run through both Elder Shield (risk ledger + LLM signal detection) and a naive baseline (LLM classification only, no tools, no corpus, no ledger).

| Metric | Elder Shield | Naive Baseline |
|--------|-------------|----------------|
| Classification accuracy | **63.6%** | 34.7% |
| False positives on legitimate messages | **0/12 (0%)** | 5/12 (42%) |
| Naive calls "scam" on first message | — | **75% of the time** |
| Scam scenarios eventually caught | 100% | 100% |

The naive baseline over-reacts — 75% of the time it classifies the very first message as "scam." Elder Shield accumulates evidence: safe → elevated → suspicious → blocked. Both catch every scam eventually. The difference is zero false positives and graduated response vs panic on first contact.

### Benchmark: Faxi production classifier vs Elder Shield

Both run on the **same model** (gemini-2.5-flash-lite), same cost. Faxi's classifier is the real production code from `spamCheckService.ts` — minimal prompt, no tools, no corpus.

#### Scam detection — both catch everything

| Test Case | Faxi Production | Elder Shield |
|---|---|---|
| Obvious ore-ore scam (¥800K + secrecy) | scam (0.99) | scam (0.98) |
| Fictitious billing (legal threat) | scam (0.98) | scam (1.0) |
| Refund scam (還付金詐欺) | scam (0.98) | scam (1.0) |
| Counter-system social engineering | scam (0.95) | scam (0.95) |

#### False positives — Elder Shield knows the difference

| Test Case | Faxi Production | Elder Shield | Why |
|---|---|---|---|
| Daughter asks for rent help (¥50K) | **scam (0.95)** ← blocks daughter | **safe (0.85)** ✓ | Verified contact in social graph |
| Grandson: surprise birthday + "don't tell mom" | **scam (0.85)** ← blocks grandson | **safe (0.90)** ✓ | Verified contact, mundane secrecy |
| Granddaughter asks for textbook money (¥50K) | **scam (0.95)** ← blocks granddaughter | **safe (0.85)** ✓ | Verified contact, proportional need |
| Real grandchild ¥3K from unknown phone | **scam (0.98)** ← blocks help request | **suspicious (0.65)** ✓ | Unknown sender but contra-indicators apply |
| Day 4 trust-building (soft financial mention) | **scam (0.85)** ← over-triggers | **suspicious (0.55)** ✓ | Contra-indicators: no secrecy, no third party |

**Faxi: 5 false positives.** It blocks a daughter asking for rent help, a grandson planning a birthday surprise, and a granddaughter buying textbooks. Same model, same message — Faxi just doesn't know who they are.

**Elder Shield: 0 false positives, 0 missed scams.** The difference isn't a better model. It's two things the production classifier doesn't have:

1. **Social graph** — verified contacts get a different analytical lens. A ¥50K request from a verified daughter is family support. The same request from an unknown sender is suspicious. The message is identical; the sender context changes the classification.

2. **Contra-indicator pipeline** — when corpus matches say "scam" but structural analysis says "no secrecy, no third-party account, mundane context," the classifier sees evidence for both sides and makes a judgment call instead of a pattern match.

#### Known contacts aren't whitelisted — they're monitored differently

Classifying a known contact's message as "safe" doesn't mean ignoring it. Every financial request is logged. The Behavioral Analyzer watches for patterns over time:
- A daughter asking for rent once → normal family support
- A daughter asking for rent every month → EA-1 (financial control signal)
- A caregiver gradually increasing requests → EA-3 (authority escalation)

The system doesn't decide "safe or scam." It decides "scam, family support, or abuse" — and the answer can change over time as evidence accumulates.

**Latency:** Faxi ~0.5s (1 LLM call). Elder Shield ~0.9s (pre-processing + 1 LLM call) — 12x faster than the original 7-tool approach (11s).

### How the pipeline creates judgment, not just pattern matching

Each step moves intelligence OUT of the model and INTO infrastructure:
- Steps 1-3 run **before** the LLM — linguistic analysis, TF-IDF corpus search, graph validation, contra-indicator analysis. Pure code, no API calls, ~50ms.
- The LLM call classifies and extracts entities — its job is simpler because it receives pre-computed evidence from both sides.
- Post-classification, the **Behavioral Analyzer** and **Conversation Knowledge Graph** run asynchronously — profile updates, provenance tracking, friction scoring.

The system sees what the corpus sees (5 scam matches) AND what the graph sees (verified daughter) AND what the contra-indicator check sees (no secrecy, mundane context). The LLM gets evidence for both sides and makes a judgment call. A pattern matcher can't do this. An LLM with the right infrastructure can.

### Corpus search: Agent Search Data Store

Three iterations of corpus search, each solving the previous version's limitations:

| Version | Technology | Japanese support | Warm-up | Cross-language |
|---------|-----------|-----------------|---------|----------------|
| v1 | Jaccard bag-of-words | Poor (0 matches on 5/7 queries) | None | No |
| v2 | Dual TF-IDF (word + char n-gram) | Good (custom char_wb vectorizer) | **30-50s** cold start | Partial (separate vectorizers) |
| v3 | **Agent Search Data Store** | Native (neural/semantic) | **None** | Yes (same query finds JP+EN results) |

Agent Search eliminates the 30-50 second corpus pre-warm that was blocking Cloud Run deployments. Neural search understands meaning — "お金を要求している" and "金銭を求めている" are the same concept. TF-IDF misses this. The TF-IDF implementation remains as a local development fallback.

## Demo

Live at [shield.faxi.jp](https://shield.faxi.jp):

- **/shield** -- Overview page with architecture, benchmark results, and the provenance tracking story.
- **/analyzer** -- **Conversation Analyzer** — 4 demo scenarios: early detection + block, outbound reply interception, longitudinal detection (6 messages), epistemic drift. Pre-captured seed data with live final exchange through real pipeline.
- **/architecture** -- Architecture diagram showing detection/scoring separation, signal flow, and protection actions.
- **/dashboard** -- Family safety dashboard with quarantine inbox, risk timeline, and contact network.
- **/technical** -- Technical deep dive with benchmark data, signal taxonomy, and academic citations.

### Agents

| Agent | Demo | Live? |
|-------|------|-------|
| Inbound Classifier | Conversation Analyzer | Yes — signal detection per message, ledger scores |
| Behavioral Analyzer | Conversation Analyzer (via accumulated signals) | Yes — LLM sees full message arc |
| Outbound Interceptor | Conversation Analyzer (Intercept Reply scenario) | Yes — live hold/release decision |
| Family Alerter | Conversation Analyzer (all scenarios) | Yes — triggered by risk ledger gates |
| Fact Extractor | Conversation Analyzer | Yes — fact extraction + elder state detection |
| Naive Classifier (Faxi baseline) | Both demos (Pre-ADK Tuning comparison) | Yes — live Gemini, no tools |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | Google ADK 2.0 (Python) |
| Model (all agents) | Gemini 2.5 Flash Lite on Vertex AI — infrastructure does the heavy lifting |
| Sessions | ADK Session State — longitudinal memory via output_key + session.state |
| Corpus grounding | Agent Search Data Store (22,979 entries) — neural/semantic search, no warm-up |
| Risk scoring | ConversationRiskLedger — additive evidence accumulation with decay, tier amplification, sequence detection |
| Deployment | Google Cloud Run (us-central1) — instant cold start (no corpus pre-warm) |
| Orchestration | ADK Workflow (FunctionNode + Agent DAG) |

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

## Signal Glossary

28 detection signals across 5 families, organized into 3 severity tiers:

**PM — Per-Message Signals** (detected by LLM from a single inbound message)

| Code | Signal | Tier | What it detects |
|---|---|---|---|
| PM-1 | Urgency language | T2 | 今すぐ, 急いで, ASAP, "act now" |
| PM-2 | Secrecy demand | T3 | 誰にも言わないで, "don't tell anyone" |
| PM-3 | Financial solicitation | T3 | **Active** request for money directed at elder: "send me", "transfer to" |
| PM-4 | Authority claim | T2 | Police, government, bank impersonation |
| PM-5 | Unusual payment method | T3 | Gift cards, crypto, convenience store |
| PM-6 | Legal threat | T3 | 法的措置, lawsuit, arrest |
| PM-7 | Credential solicitation | T3 | Passwords, PINs, My Number |
| PM-8 | Prize notification | T3 | "You've won" with fee requirement |
| PM-9 | Refund lure | T3 | Fake refund requiring bank details |
| PM-10 | Emotional crisis | T2 | Accident, hospital, emergency |
| PM-11 | Identity claim | T1 | Claims specific family relationship |
| PM-12 | Flattery density | T1 | Excessive compliments |
| PM-13 | SPF/DKIM fail | T3 | Email authentication failure |
| PM-14 | Financial context | T2 | Mentions money/costs WITHOUT asking — "I lost money", "card frozen" |

**VS — Victim State Signals** (detected by LLM from elder's outbound replies)

| Code | Signal | What it detects |
|---|---|---|
| VS-1 | Compliance acceptance | Agreeing to requests, accepting instructions |
| VS-2 | Secrecy adoption | Agreeing to keep conversation secret from family |
| VS-3 | Financial commitment | Stating intent to send money, go to bank, buy cards |
| VS-4 | Emotional capitulation | Reassuring the sender, expressing concern FOR them |
| VS-5 | Urgency mirroring | Adopting the sender's sense of urgency |
| VS-6 | Question cessation | Stopped asking questions (longitudinal) |
| VS-7 | Deference shift | Casual→formal or assertive→submissive (longitudinal) |

**BV — Behavioral Velocity** (detected across messages over time)

| Code | Signal | What it detects |
|---|---|---|
| BV-1 | Relationship velocity | Intimacy progressing too fast for timeline |
| BV-2 | Isolation index | Distancing from family/verification network |
| BV-3 | Emotional arc | Sentiment escalating on a schedule |
| BV-4 | Credibility seeding | Volunteering excessive personal details |
| BV-5 | Help positioning | Systematic "I'm here for you" from stranger |

**EA — Elder Abuse** (manipulation from known/trusted contacts)

| Code | Signal | What it detects |
|---|---|---|
| EA-1 | Financial control | Known contact requesting money or savings info |
| EA-2 | Trusted isolation | Known contact cutting off other family |
| EA-3 | Authority escalation | Caregiver taking over decisions |
| EA-4 | Communication shift | Sudden frequency or topic change |

**CM — Cross-Modal**

| Code | Signal | What it detects |
|---|---|---|
| CM-1 | Spending correlation | Conversation intensity matches spending patterns |

## Quick Start

```bash
pip install -r requirements.txt
gcloud auth application-default login
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=us-central1
export USE_VERTEX_SEARCH=true
export SCAM_CORPUS_DATA_STORE=scam-corpus
PYTHONPATH=. uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

No warm-up required — Agent Search Data Store provides instant corpus access.

## Project Structure

```
agents/
  root_agent.py            # ADK Workflow DAG orchestrator
  inbound_classifier.py    # Per-message signal detection (39 signals across 6 families)
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
  index.html               # Scam simulator (legacy)
app.py                     # FastAPI application (/shield, /analyzer, /architecture, /dashboard, /api/*)
```

## License

Apache 2.0 -- see [LICENSE](LICENSE).

## Built For

**Google for Startups AI Agents Challenge** -- Track 2: Optimize. APAC region.

Built by the team behind [Faxi](https://faxi.jp) -- an AI-powered fax-to-internet bridge for elderly Japanese users.
