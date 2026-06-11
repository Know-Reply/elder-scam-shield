# Elder Shield: Hackathon Submission

## Problem to solve

Elder-targeted fraud cost Japan ¥324 billion in 2025 (NPA), up from ¥199 billion in 2024, and $77.7 billion globally (Nasdaq 2024). Existing systems classify messages one at a time. None detect multi-day trust-building campaigns targeting elderly users: users who cannot evaluate warnings, making traditional alert-based protection ineffective. A scammer building rapport over 5 days looks safe on days 1-4: each message is genuinely innocuous. By day 5, the elder is emotionally compromised. A per-message classifier catches the ask but misses the 4 days of setup where intervention could have prevented it.

## Our solution

Elder Shield separates LLM signal detection from deterministic risk scoring. Through ADK optimization, all six agents run on Gemini Flash Lite: the cheapest model tier. The LLM detects 40 signals across 6 families; a deterministic ConversationRiskLedger makes the classification decision. Evidence accumulates across messages with decay, tier amplification, attack sequence detection, sender-trust modulation from the social graph, and a grooming-then-escalation primer bonus modeled on NPA tokushu-sagi data.

- **LLM finds signals, not verdicts.** 15 per-message signals in 3 severity tiers. A deterministic ledger scores them additively: classification from accumulated evidence, never an LLM opinion.
- **Elder's replies reveal if the scam is working.** 7 victim state signals from outbound messages: compliance, secrecy adoption, financial commitment. Most systems watch the scammer. Elder Shield watches whether the elder is falling for it.
- **Every fact has provenance.** Tracks WHO revealed WHAT first. Echo-grounded identity detection: the scammer's "knowledge" was given to them by the elder.
- **Family alerted, not alarmed.** Bilingual JP/EN notifications when elder reaches Compromised or risk crosses 50%. Never exposes content. Never says "scam": dignity-preserving.
- **Outbound replies held for review.** Gift card codes, bank details caught before sending.
- **Behavioral velocity (BV-1..5)** catches grooming arcs: relationship velocity, isolation attempts, emotional scheduling.
- **Elder abuse (EA-1..4)** from trusted contacts: financial control, isolation, authority escalation.

Business model: Elder Shield ships as a family-protection subscription on Faxi. The adult children who already manage a parent's Faxi account pay for the protection tier and receive the alerts. The buyer (the family) is not the user (the elder) — which is why dignity-preserving alerts are a revenue requirement, not a UX nicety: an elder who feels surveilled turns the system off, and the subscription churns.

Longitudinal evaluation across 52 multi-message scenarios (140 graded messages, both systems on gemini-2.5-flash-lite): **34/34 scams caught vs 31/34 naive — the baseline missed two investment groomers and a romance opener that look reasonable message-by-message. 0/13 false positives.** Per-message stage accuracy (is the system at the right alert level at each point in the conversation?) is 67.2% vs 62.8%. The zero false positives were earned through the evaluation itself: an earlier run exposed 4 legitimate family conversations being flagged, root-caused to graph trust never reaching the scoring layer; we wired the social graph's verdict into the risk ledger and gated attack-pattern multipliers to unverified senders. After the fix, every legitimate family conversation ends in "monitoring" — watched, never flagged.

## Technologies used

- Google ADK 2.0: Workflow DAG, output_schema, output_key, FunctionTool, before_tool_callback, multiple Runners
- Gemini 2.5 Flash Lite on Vertex AI (us-central1): all 6 agents, cheapest model tier
- Vertex AI Agent Engine: root agent deployed via adk deploy (`reasoningEngines/4623304008042283008`, us-central1, 2026-06-10)
- Agent Search Data Store: 22,979-entry corpus, neural search, cross-language JP+EN
- Cloud Run: FastAPI app with ConversationRiskLedger scoring layer
- ADK Session State: output_key + session.state carry structured results between agents within each request; longitudinal per-sender memory lives in the deterministic risk ledger (VertexAiSessionService planned for production persistence)

ADK optimization tools drove the development:
- Agent Evaluation: 55-case EvalSet (ADK format) run through a live ADK Runner harness with committed raw results, plus a 51-scenario longitudinal suite
- Agent Simulation: multi-day scam sequences replayed end-to-end through live agents to stress-test longitudinal detection
- Agent Optimizer: confirmed prompt near-optimal; value is in infrastructure, not prompts
- Agent Observability: 45 OTel spans across 3 traced cases (15 per case) identified false positive root causes, drove contra-indicator design

## Data sources

22,979 corpus entries from 7 sources including real phishing emails, Japanese scam transcripts, NPA police-published scripts, and antiphishing.jp reports. Signal weights calibrated against NPA tokushu-sagi reports 2023-2025.

## Findings and learnings

1. **LLMs are better sensors than judges.** When the evaluation exposed legitimate family messages being flagged, the fix was ~30 auditable lines in the deterministic ledger — not prompt surgery. The LLM understands language; it shouldn't make risk decisions, precisely so that risk decisions stay debuggable.

2. **False positives matter more than catch rate.** Blocking a real grandchild's request destroys trust. 0/13 false positives matters because a disabled system protects nobody — and our eval initially showed 4, which we root-caused and fixed rather than re-labeled.

3. **The T1 primer bonus models real attack behavior.** Ore-ore scams start with identity claims (T1), then escalate. The 1.3x multiplier when T2/T3 follows T1 models how the attack actually works — and it is gated to unverified senders, because the same arc from a verified grandson is just how family talks.

4. **Agent Optimizer proved the value is in infrastructure, not prompts.** The optimizer couldn't beat our prompt. The accuracy improvement comes from the pipeline (corpus, risk ledger, graph), not prompt engineering.

5. **Observability found the false positive root cause.** OTel traces showed family messages matching scam patterns, driving the contra-indicator pipeline.

6. **The per-message gap closes as models improve; the context gap doesn't.** Re-running on a newer model, the naive baseline got dramatically better at single-message classification — and still missed 3 of 34 multi-day scams while knowing nothing about who senders are, what the elder is doing, or what leaves the device. The durable advantage is the infrastructure a per-message classifier can't have at any model size.

## Third-party integrations

No third-party SDKs or runtime integrations. Built entirely on Google ADK + Vertex AI + Cloud Run. Data sources are openly published datasets (Apache 2.0, LGPL-3.0, one unspecified-license research dataset) and public government publications; per-source licensing is documented in [data/DATA_PROVENANCE.md](data/DATA_PROVENANCE.md).

---

## Questionnaire Answers

### Which specific feature of Agent Platform was most critical to your project's impact, and what is one thing it's currently missing?

`output_schema` with Pydantic + `output_key` to session state. This enabled our core architectural innovation: separating LLM signal detection from deterministic scoring. The LLM outputs a structured `ClassificationResult` with `detected_signals`: the `output_schema` guarantees the shape, and `output_key` writes it to session state where our `ConversationRiskLedger` scores it deterministically. Without typed structured output, we couldn't reliably bridge LLM language understanding to a predictable, testable scoring function. The LLM is a sensor array; the ledger is the judge. `output_schema` made that separation possible.

Missing: Session state accessible via API outside Agent Engine. Our pipeline has application logic (FastAPI endpoints, demo UI rendering) that needs to read agent session state after a Workflow completes. Currently this requires either running agents in-process (losing managed sessions) or deploying to Agent Engine (losing direct API control). A REST API for reading/writing managed session state from external applications would let us deploy agents to Agent Engine while keeping our application server independent.

### If you could add one specific API capability or integration that would have saved you 2+ hours of work, what would it be?

ADK should raise an error at startup when a model isn't available on Vertex AI in the configured region, instead of silently falling back to the Generative Language API with a hard-capped 15 RPM quota. Cost us 3+ hours debugging 429 errors.

### Describe the readiness of your project for launch.

Demo-ready with production architecture. The system runs on Cloud Run with Vertex AI (gemini-2.5-flash-lite), Agent Search Data Store (22,979-entry corpus), and a live interactive demo with 4 scenarios showing early detection + block, outbound reply interception, longitudinal detection across 6 messages, and epistemic drift tracking. Scenario walk-up messages replay pre-captured seed data; the final exchange in each scenario and the Free Play mode run live through the full pipeline. The root agent is also deployed to Vertex AI Agent Engine via `adk deploy`.

Production gaps: Cross-conversation state requires persistent sessions (designed for VertexAiSessionService but currently using InMemorySessionService for the application layer). Social graph uses mock data. The ConversationRiskLedger weights are priors seeded from NPA aggregate statistics, not fitted from labeled training data: production calibration requires labeled case outcomes from Faxi's deployed pipeline. The system is designed as a drop-in replacement for Faxi's existing `spamCheckService.ts` with a compatible API contract.
