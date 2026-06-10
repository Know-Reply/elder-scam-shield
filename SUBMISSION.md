# Elder Shield — Hackathon Submission

## Problem to solve

Elder fraud costs ¥1.4 trillion annually in Japan (NPA 2025 — a record). Every existing protection system classifies messages one at a time. None detect the multi-day trust-building campaigns that cause the largest losses. A scammer who builds rapport over 5 days before asking for money looks safe on days 1-4 — each individual message is genuinely innocuous. By the time the money request arrives on day 5, the elder is already emotionally compromised. A per-message classifier catches the ask but misses the setup. We needed a system that remembers the setup and compounds the evidence.

## Our solution

Elder Shield is a multi-agent scam protection system that separates LLM signal detection from deterministic risk scoring. The LLM (Gemini 2.5 Flash Lite) detects 28 signals across 5 families — it never classifies. A ConversationRiskLedger accumulates evidence across messages with decay, tier amplification, attack sequence detection, and a T1 primer bonus that models the documented grooming-then-escalation pattern in Japanese tokushu-sagi fraud.

Key features:

- **Inbound Shield**: 14 per-message signals (PM-1..PM-14) in 3 severity tiers. Additive scoring — no override floors, weights calibrated against NPA data.
- **Elder's Guard**: LLM detects victim state signals (VS-1..VS-7) from the elder's outbound replies — compliance, secrecy adoption, financial commitment. Tracks whether the scam is *working*, not just whether it exists.
- **Conversation Knowledge Graph**: Information provenance tracking — WHO revealed WHAT first. Detects echo-grounded identity (scammer's identity built from facts the elder volunteered).
- **Family Alerter**: Bilingual JP/EN notifications triggered by 4 gates (score sustained, score spike, tier override, sequence match). Never exposes message content. Dignity-preserving design.
- **Outbound Interceptor**: Holds replies containing sensitive data (gift card codes, bank details) before sending.
- **Behavioral Velocity (BV-1..5)**: Cross-conversation patterns — relationship velocity, isolation attempts, emotional arc scheduling.
- **Elder Abuse (EA-1..4)**: Detects manipulation from known/trusted contacts — financial control, trusted isolation, authority escalation.

52-scenario longitudinal evaluation: 63.6% classification accuracy vs 34.7% naive baseline. 0/12 false positives vs 5/12 naive (42%). The naive baseline calls "scam" on 75% of first messages. Elder Shield accumulates evidence: safe → elevated → suspicious → blocked.

## Technologies used

- **Google ADK 2.0** (Python) — Workflow DAG, output_schema (Pydantic), output_key, before_tool_callback, FunctionTool, multiple Runners
- **Gemini 2.5 Flash Lite** on **Vertex AI** (us-central1) — all 6 agents
- **Vertex AI Agent Engine** — deployed via `adk deploy` for managed sessions
- **Agent Search Data Store** — 22,979-entry scam corpus with neural/semantic search, cross-language Japanese + English
- **Google Cloud Run** — FastAPI application serving demo UI and API endpoints
- **InMemorySessionService** — longitudinal session state for risk ledger accumulation

## Data sources

22,979 corpus entries across 8 scam categories from 7 sources:

| Source | Entries | Type |
|--------|---------|------|
| zefang-liu/phishing-email-dataset | 17,514 | Real phishing + safe emails |
| BothBosu/scam-dialogue + multi-agent | 3,200 | Multi-turn phone/chat transcripts |
| cybersectony/PhishingEmailDetectionv2.0 | 1,254 | Real phishing + legitimate emails |
| antiphishing.jp | 203 | Real Japanese phishing reports |
| NPA SOS47 dialogues | 44 | Real police-published scam scripts |
| Synthetic NPA scenarios | 162 | Japanese scam scenarios (3 difficulty levels) |
| Synthetic edge cases | 12 | Bilingual, ambiguous test cases |

Signal weights calibrated against NPA tokushu-sagi annual reports 2023-2025. Attack sequence multipliers reflect NPA loss severity rankings: authority impersonation (3.2x) > ore-ore (2.8x) > investment (2.5x) > romance (2.2x).

## Findings and learnings

1. **LLMs are better sensors than judges.** When we let the LLM classify (safe/suspicious/scam), it was inconsistent — the same message scored differently across runs, and corpus matches overrode tier guidance. When we separated detection (LLM finds signals) from scoring (deterministic ledger computes classification), accuracy jumped from 34.7% to 63.6% and became reproducible. The LLM understands language; it shouldn't be making risk decisions.

2. **Keyword detection doesn't work for Japanese.** We built keyword-based victim state analysis and epistemic friction scoring (counting question marks). Both failed — Japanese has no word boundaries, and "What should I do?" (compliance) looks identical to "What do you mean?" (resistance) to a character counter. Moving all language understanding to the LLM and keeping only math in the scoring layer was the right architecture.

3. **False positives are worse than missed scams for elder protection.** Blocking a real grandchild's taxi money request destroys trust in the system. The elder turns it off. Our zero false positive rate (0/12 legitimate scenarios) matters more than the detection rate, because a system the elder disables protects nobody.

4. **The T1 primer bonus is the most insight-driven feature.** Ore-ore scams always start with identity claims (T1), then escalate to crisis + money (T2/T3). Encoding this as a 1.3x multiplier when T2/T3 follows T1 isn't a numeric trick — it models how the attack actually works. Messages 1-3 are individually safe but they prime the score for message 4.

5. **AI coding assistants don't know ADK yet.** Our AI assistant consistently suggested non-ADK patterns — raw API calls, custom session management, regex-based detection. ADK documentation needs to be consumable by AI coding tools, not just human developers. Developers increasingly build *with* AI assistants, and if those assistants don't know ADK, developers won't use it correctly.

## Third-party integrations

All data sources are open-source or publicly available:

- zefang-liu/phishing-email-dataset (MIT License)
- BothBosu/scam-dialogue (Apache 2.0)
- cybersectony/PhishingEmailDetectionv2.0 (Apache 2.0)
- antiphishing.jp (public reports, used under fair use for research)
- NPA SOS47 (Japanese government public safety publications)

No third-party SDKs beyond Google Cloud services. Built entirely on Google ADK + Vertex AI + Cloud Run.

---

## Questionnaire Answers

### Which specific feature of Agent Platform was most critical to your project's impact, and what is one thing it's currently missing?

`output_schema` with Pydantic + `output_key` to session state. This enabled our core architectural innovation: separating LLM signal detection from deterministic scoring. The LLM outputs a structured `ClassificationResult` with `detected_signals` — the `output_schema` guarantees the shape, and `output_key` writes it to session state where our `ConversationRiskLedger` scores it deterministically. Without typed structured output, we couldn't reliably bridge LLM language understanding to a predictable, testable scoring function. The LLM is a sensor array; the ledger is the judge. `output_schema` made that separation possible.

Missing: Session state accessible via API outside Agent Engine. Our pipeline has application logic (FastAPI endpoints, demo UI rendering) that needs to read agent session state after a Workflow completes. Currently this requires either running agents in-process (losing managed sessions) or deploying to Agent Engine (losing direct API control). A REST API for reading/writing managed session state from external applications would let us deploy agents to Agent Engine while keeping our application server independent.

### If you could add one specific API capability or integration that would have saved you 2+ hours of work, what would it be?

A clear model availability matrix per backend. We configured `GOOGLE_GENAI_USE_VERTEXAI=TRUE` but our model (`gemini-3.1-flash-lite`) wasn't available on Vertex AI — only through the Generative Language API. ADK silently fell back to the free tier (15 RPM), and we spent 3+ hours debugging 429 errors before discovering we were routing through the wrong API with a hard-capped quota. If ADK raised an error on startup saying "model X is not available on Vertex AI in region Y" instead of silently falling back, that would have saved significant time.

More broadly, we found that AI coding assistants (including Claude Code, which we used heavily) consistently suggested non-ADK patterns — raw API calls, custom session management, keyword-based detection — instead of ADK-native approaches like `output_schema`, `FunctionTool`, and `VertexAiSessionService`. This suggests the ADK documentation isn't well-represented in LLM training data yet. CLAUDE.md-style agent instruction files that teach AI assistants how to use ADK correctly would accelerate adoption significantly — developers increasingly build *with* AI assistants, and if those assistants don't know ADK, developers won't use it either.

### Describe the readiness of your project for launch.

Demo-ready with production architecture. The system runs on Cloud Run with Vertex AI (gemini-2.5-flash-lite), Agent Search Data Store (22,979-entry corpus), and a live interactive demo with 4 scenarios showing early detection + block, outbound reply interception, longitudinal detection across 6 messages, and epistemic drift tracking. All classification results are live LLM calls, not pre-scripted. The root agent is also deployed to Vertex AI Agent Engine via `adk deploy`.

Production gaps: Cross-conversation state requires persistent sessions (designed for VertexAiSessionService but currently using InMemorySessionService for the application layer). Social graph uses mock data. The ConversationRiskLedger weights are priors seeded from NPA aggregate statistics, not fitted from labeled training data — production calibration requires labeled case outcomes from Faxi's deployed pipeline. The system is designed as a drop-in replacement for Faxi's existing `spamCheckService.ts` with a compatible API contract.
