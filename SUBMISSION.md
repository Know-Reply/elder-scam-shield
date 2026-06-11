# Elder Shield: Hackathon Submission

## Problem to solve

Elder-targeted fraud cost Japan ¥324 billion in 2025 (NPA, up from ¥199 billion in 2024) and $77.7 billion globally (Nasdaq 2024). Existing systems classify messages one at a time; none detect multi-day trust-building campaigns against users who cannot evaluate warnings. Every message in a 5-day rapport campaign is genuinely innocuous — a per-message classifier catches the final ask but misses the setup, where intervention could still prevent harm.

## Our solution

Elder Shield separates LLM signal detection from deterministic risk scoring. Six agents, all on Gemini Flash Lite (the cheapest tier): the LLM detects 40 signals across 6 families; a deterministic ConversationRiskLedger makes every classification decision, accumulating evidence across messages with decay, tier amplification, attack-sequence detection, sender-trust modulation from the social graph, and a grooming-then-escalation primer bonus modeled on NPA tokushu-sagi data.

- **LLM finds signals, not verdicts.** Classification always derives from accumulated evidence, never an LLM opinion.
- **The elder's replies reveal if the scam is working.** 7 victim-state signals: compliance, secrecy adoption, financial commitment.
- **Every fact has provenance.** Tracks who revealed what first — catching scammers whose "knowledge" came from the elder.
- **Family alerted, not alarmed.** Bilingual notifications, content never exposed, never says "scam" — dignity-preserving.
- **Outbound replies held.** Gift-card codes and bank details caught before sending.
- **Behavioral velocity (BV) and elder abuse (EA) signals** catch grooming arcs and manipulation by trusted contacts.

Business model: a family-protection subscription on Faxi — the adult children who manage a parent's account pay and receive the alerts. The buyer isn't the user, so dignity-preserving alerts are a revenue requirement: a surveilled elder turns the system off.

Evaluation: 52 longitudinal scenarios, 140 graded messages, both systems on gemini-2.5-flash-lite. **34/34 scams caught vs 31/34 naive; 0/13 false positives; 67.2% vs 62.8% stage accuracy.** The zero FPs were earned through the eval: an earlier run flagged 4 family conversations, root-caused to graph trust never reaching the scoring layer. We wired the graph's verdict into the ledger and gated attack-pattern multipliers to unverified senders — family conversations now end in "monitoring": watched, never flagged.

## Technologies used

- Google ADK 2.0: Workflow DAG, output_schema, output_key, tool callbacks, multiple Runners
- Gemini 2.5 Flash Lite on Vertex AI — all 6 agents
- Vertex AI Agent Engine: root agent deployed via adk deploy (resource ID in README)
- Agent Search Data Store: 22,979-entry corpus, neural search, cross-language JP+EN
- Cloud Run: FastAPI app with the ConversationRiskLedger scoring layer
- ADK Session State: output_key carries structured agent results; longitudinal memory in the deterministic ledger

ADK optimization tools drove development:
- Agent Evaluation: 55-case EvalSet via live ADK Runner harness + 52-scenario longitudinal suite, raw results committed
- Agent Simulation: multi-day scam sequences replayed end-to-end through live agents
- Agent Optimizer: confirmed prompt near-optimal — the value is in infrastructure
- Agent Observability: 45 OTel spans across 3 traced cases surfaced false-positive root causes

## Data sources

22,979 corpus entries from 7 sources: real phishing emails, Japanese scam transcripts, NPA police-published scripts, antiphishing.jp reports. Signal weights seeded from NPA tokushu-sagi aggregate statistics.

## Findings and learnings

1. **LLMs are better sensors than judges.** When the eval exposed family messages being flagged, the fix was ~30 auditable ledger lines, not prompt surgery.

2. **False positives matter more than catch rate.** A blocked grandchild means a disabled system, and a disabled system protects nobody. Our eval initially showed 4 FPs; we root-caused and fixed rather than re-labeled.

3. **Attack patterns are sender-relative.** The T1 primer (identity claim, then escalation) models real ore-ore behavior — and is gated to unverified senders, because the same arc from a verified grandson is just how family talks.

4. **Optimizer and Observability earned their keep.** The optimizer couldn't beat our prompt; OTel traces found family messages matching scam corpus patterns, driving the contra-indicator design.

5. **The per-message gap closes as models improve; the context gap doesn't.** A newer model made the naive baseline far better per message — it still missed 3 of 34 multi-day scams, knowing nothing about senders, the elder's replies, or outbound money.

## Third-party integrations

None — built entirely on Google ADK + Vertex AI + Cloud Run. Data sources are openly published datasets (Apache 2.0, LGPL-3.0, one unspecified-license research set) and public government publications; per-source licensing in data/DATA_PROVENANCE.md.

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
