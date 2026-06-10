# Elder Shield: Hackathon Submission

## Problem to solve

Elder fraud costs ¥1.4 trillion annually in Japan (NPA 2025) and $77.7 billion globally (Nasdaq 2024). Existing systems classify messages one at a time. None detect multi-day trust-building campaigns targeting elderly users: users who cannot evaluate warnings, making traditional alert-based protection ineffective. A scammer building rapport over 5 days looks safe on days 1-4: each message is genuinely innocuous. By day 5, the elder is emotionally compromised. A per-message classifier catches the ask but misses the 4 days of setup where intervention could have prevented it.

## Our solution

Elder Shield separates LLM signal detection from deterministic risk scoring. Through ADK optimization, all six agents run on Gemini Flash Lite: the cheapest model tier. The LLM detects 39 signals across 6 families; a deterministic ConversationRiskLedger makes the classification decision. Evidence accumulates across messages with decay, tier amplification, attack sequence detection, and a grooming-then-escalation primer bonus modeled on NPA tokushu-sagi data.

- **LLM finds signals, not verdicts.** 15 per-message signals in 3 severity tiers. A deterministic ledger scores them additively: classification from accumulated evidence, never an LLM opinion.
- **Elder's replies reveal if the scam is working.** 7 victim state signals from outbound messages: compliance, secrecy adoption, financial commitment. Most systems watch the scammer. Elder Shield watches whether the elder is falling for it.
- **Every fact has provenance.** Tracks WHO revealed WHAT first. Echo-grounded identity detection: the scammer's "knowledge" was given to them by the elder.
- **Family alerted, not alarmed.** Bilingual JP/EN notifications when elder reaches Compromised or risk crosses 50%. Never exposes content. Never says "scam": dignity-preserving.
- **Outbound replies held for review.** Gift card codes, bank details caught before sending.
- **Behavioral velocity (BV-1..5)** catches grooming arcs: relationship velocity, isolation attempts, emotional scheduling.
- **Elder abuse (EA-1..4)** from trusted contacts: financial control, isolation, authority escalation.

52-scenario longitudinal evaluation: 63.6% accuracy vs 34.7% naive baseline. 0/12 legitimate scenarios falsely flagged vs 5/12 naive (42%). Naive calls "scam" on 75% of first messages. Elder Shield accumulates: safe → elevated → suspicious → blocked.

## Technologies used

- Google ADK 2.0: Workflow DAG, output_schema, output_key, FunctionTool, before_tool_callback, multiple Runners
- Gemini 2.5 Flash Lite on Vertex AI (us-central1): all 6 agents, cheapest model tier
- Vertex AI Agent Engine: root agent deployed via adk deploy
- Agent Search Data Store: 22,979-entry corpus, neural search, cross-language JP+EN
- Cloud Run: FastAPI app with ConversationRiskLedger scoring layer
- ADK Session State: longitudinal memory via output_key + session.state

ADK optimization tools drove the development:
- Agent Evaluation: 55-case EvalSet via AgentEvaluator + 52-scenario longitudinal suite
- Agent Simulation: LlmBackedUserSimulator stress-tested multi-day scam sequences
- Agent Optimizer: confirmed prompt near-optimal; value is in infrastructure, not prompts
- Agent Observability: 45 OTel spans per case identified false positive root causes, drove contra-indicator design

## Data sources

22,979 corpus entries from 6 sources including real phishing emails, Japanese scam transcripts, NPA police-published scripts, and antiphishing.jp reports. Signal weights calibrated against NPA tokushu-sagi reports 2023-2025.

## Findings and learnings

1. **LLMs are better sensors than judges.** Separating detection from scoring improved accuracy from 34.7% to 63.6%. The LLM understands language; it shouldn't make risk decisions.

2. **False positives matter more than catch rate.** Blocking a real grandchild's request destroys trust. 0/12 false positives matters because a disabled system protects nobody.

3. **The T1 primer bonus models real attack behavior.** Ore-ore scams start with identity claims (T1), then escalate. The 1.3x multiplier when T2/T3 follows T1 models how the attack actually works.

4. **Agent Optimizer proved the value is in infrastructure, not prompts.** The optimizer couldn't beat our prompt. The accuracy improvement comes from the pipeline (corpus, risk ledger, graph), not prompt engineering.

5. **Observability found the false positive root cause.** OTel traces showed family messages matching scam patterns, driving the contra-indicator pipeline.

## Third-party integrations

No third-party SDKs or runtime integrations. Built entirely on Google ADK + Vertex AI + Cloud Run. Data sources are all open-source (MIT, Apache 2.0) or public government publications.

---

## Questionnaire Answers

### Which specific feature of Agent Platform was most critical to your project's impact, and what is one thing it's currently missing?

`output_schema` with Pydantic + `output_key` to session state. This enabled our core architectural innovation: separating LLM signal detection from deterministic scoring. The LLM outputs a structured `ClassificationResult` with `detected_signals`: the `output_schema` guarantees the shape, and `output_key` writes it to session state where our `ConversationRiskLedger` scores it deterministically. Without typed structured output, we couldn't reliably bridge LLM language understanding to a predictable, testable scoring function. The LLM is a sensor array; the ledger is the judge. `output_schema` made that separation possible.

Missing: Session state accessible via API outside Agent Engine. Our pipeline has application logic (FastAPI endpoints, demo UI rendering) that needs to read agent session state after a Workflow completes. Currently this requires either running agents in-process (losing managed sessions) or deploying to Agent Engine (losing direct API control). A REST API for reading/writing managed session state from external applications would let us deploy agents to Agent Engine while keeping our application server independent.

### If you could add one specific API capability or integration that would have saved you 2+ hours of work, what would it be?

A clear model availability matrix per backend. We configured `GOOGLE_GENAI_USE_VERTEXAI=TRUE` but our model (`gemini-3.1-flash-lite`) wasn't available on Vertex AI: only through the Generative Language API. ADK silently fell back to the free tier (15 RPM), and we spent 3+ hours debugging 429 errors before discovering we were routing through the wrong API with a hard-capped quota. If ADK raised an error on startup saying "model X is not available on Vertex AI in region Y" instead of silently falling back, that would have saved significant time.

More broadly, we found that AI coding assistants (including Claude Code, which we used heavily) consistently suggested non-ADK patterns: raw API calls, custom session management, keyword-based detection: instead of ADK-native approaches like `output_schema`, `FunctionTool`, and `VertexAiSessionService`. This suggests the ADK documentation isn't well-represented in LLM training data yet. CLAUDE.md-style agent instruction files that teach AI assistants how to use ADK correctly would accelerate adoption significantly: developers increasingly build *with* AI assistants, and if those assistants don't know ADK, developers won't use it either.

### Describe the readiness of your project for launch.

Demo-ready with production architecture. The system runs on Cloud Run with Vertex AI (gemini-2.5-flash-lite), Agent Search Data Store (22,979-entry corpus), and a live interactive demo with 4 scenarios showing early detection + block, outbound reply interception, longitudinal detection across 6 messages, and epistemic drift tracking. All classification results are live LLM calls, not pre-scripted. The root agent is also deployed to Vertex AI Agent Engine via `adk deploy`.

Production gaps: Cross-conversation state requires persistent sessions (designed for VertexAiSessionService but currently using InMemorySessionService for the application layer). Social graph uses mock data. The ConversationRiskLedger weights are priors seeded from NPA aggregate statistics, not fitted from labeled training data: production calibration requires labeled case outcomes from Faxi's deployed pipeline. The system is designed as a drop-in replacement for Faxi's existing `spamCheckService.ts` with a compatible API contract.
