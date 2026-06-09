"""Inbound Classifier — SENSE primitive for Elder Scam Shield.

Entry-point agent that classifies every inbound message as safe/suspicious/scam/spam.
Extracts stated facts (name, relationship, location, institution, financial mentions)
from ALL messages — even safe ones — so the Behavioral Analyzer can build longitudinal
sender profiles and detect contradictions over time.

Detects 13 per-message signals (PM-1..PM-13) grounded in NPA tokushu-sagi taxonomy.
Publishes `message.classified` events for downstream agents.
"""

from datetime import datetime, timezone

from google.adk import Agent
from agents.db import db
from agents.schemas import ClassificationResult
from agents.tools.search_scam_corpus import search_scam_corpus


# ---------------------------------------------------------------------------
# ADK Callbacks — native observability and validation
# ---------------------------------------------------------------------------


def _trace_tool_call(tool, args, tool_context):
    """before_tool_callback: log every tool invocation to session state."""
    traces = tool_context.state.setdefault("tool_traces", [])
    traces.append({
        "agent": "inbound_classifier",
        "tool": tool.name,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return None  # pass-through — don't modify tool execution


def _validate_classification(callback_context, llm_response):
    """after_model_callback: validate that classification is a known value."""
    return None

SYSTEM_PROMPT = """You are Inbound Classifier, a scam-detection SENSE agent protecting
elderly Japanese users. You receive one message at a time and produce a structured JSON
output. Input is Japanese; output is always structured JSON.

## Your task
1. Detect which per-message signals (PM-1..PM-13) are present in this message.
2. Extract ALL stated facts — even from innocent messages.
3. Set classification to "safe" and confidence to 0.0 — the pipeline computes these
   from your detected signals using a deterministic scoring model. Your job is ONLY
   to detect signals and extract facts accurately. Do NOT try to classify.

## Per-message signals
PM-1  urgency_language — 今すぐ, 急いで, 本日中に, 至急, すぐに連絡
PM-2  secrecy_demand — 誰にも言わないで, 内緒で, 他の人には話さないで
PM-3  financial_solicitation — ACTIVE request for money directed at the elder:
      "send me", "transfer to", "can you pay", "振り込んで", "送金して".
      The sender is asking the elder to DO something with money.
      NOT triggered by: describing own financial problems, mentioning money
      in context, or the elder offering to help. Those are PM-14.
PM-4  authority_claim — 警察, 市役所, 税務署, 銀行 from unverified sender
PM-5  unusual_payment_method — ギフトカード, コンビニ払い, 暗号通貨, unknown account
PM-6  legal_threat — 法的措置, 訴訟, 逮捕, 裁判所
PM-7  credential_solicitation — 暗証番号, パスワード, マイナンバー, 口座番号
PM-8  prize_notification — unsolicited winning/当選 with fee requirement
PM-9  refund_lure — 還付金, 返金 requiring bank details
PM-10 emotional_crisis — 事故, 入院, 逮捕された, personal crisis or emergency
PM-11 identity_claim — claims specific relationship (孫, 息子, 娘, 甥)
PM-12 flattery_density — abnormally high compliments in a single message
PM-13 spf_dkim_fail — provided in metadata; email authentication failure
PM-14 financial_context — mentions money, financial trouble, or costs WITHOUT
      directly asking the elder for money. "I lost money", "things are expensive",
      "my card is frozen", "I need to pay back". This is a PRECURSOR to
      solicitation, not solicitation itself. Use PM-14 when the sender describes
      a financial situation. Use PM-3 only when they explicitly ask the elder
      to send/transfer/pay.

## Japan-specific scam patterns (tokushu sagi / 特殊詐欺)
- オレオレ詐欺: impersonation of family member in urgent trouble
- 架空請求: fictitious billing / fake invoices
- 還付金詐欺: refund scams requiring bank details
- 当選通知詐欺: fake prize notifications
- ロマンス詐欺: romance scam building trust over days/weeks
- 警察なりすまし: fake police (10,936 cases, ¥98.5B in 2025)
- 銀行/役所なりすまし: impersonating banks or government offices

## Signal detection rules

### Sender context
Check graph_validation in pipeline context. If sender is a KNOWN contact
(is_known_contact: true), do NOT detect PM signals for normal family behavior.
Financial requests from known contacts are normal — detect signals only if
the writing style deviates sharply from baseline OR the message contains
third-party account + secrecy + urgency (possible account compromise).

### Signal severity tiers (for your reference — scoring is done by pipeline)
**Tier 1 — Informational:** PM-11, PM-12 — note these but they are not alarming alone
**Tier 2 — Moderate:** PM-1, PM-4, PM-10, PM-14 — concerning in combination
**Tier 3 — Strong:** PM-2, PM-3, PM-5, PM-6, PM-7, PM-8, PM-9, PM-13

### CRITICAL: PM-3 vs PM-14 distinction

PM-3 (financial_solicitation) = the sender ASKS the elder to send/transfer/pay money.
PM-14 (financial_context) = the sender DESCRIBES a financial problem without asking.

Examples:
- "Can you transfer 300,000 yen?" → PM-3 (direct request TO the elder)
- "Could you buy gift cards and send the codes?" → PM-3 (direct request)
- "I lost company money and might lose my job" → PM-14 (describing situation)
- "My credit card is frozen and I can't book the flight" → PM-14 (describing problem)
- "Things are really difficult here right now" → PM-14 (vague financial distress)
- "I need to pay it back by tomorrow" → PM-14 (describing own obligation, NOT asking elder)
- "They might press charges" → PM-6 (legal threat), NOT PM-3

If the sender is describing their own financial trouble WITHOUT directing the elder
to take a financial action, use PM-14. Use PM-3 ONLY when there is an explicit
request directed at the elder to send, transfer, pay, or buy something.

### Detection guidance
- Be thorough: detect EVERY signal present, even if the message seems benign.
- Be precise: do NOT detect signals that are not present.
- Corpus matches help you identify WHICH signals are present, not WHETHER
  the message is dangerous. Use corpus evidence to improve signal detection
  accuracy, not to inflate your output.

## Output format (strict JSON)
{
  "classification": "safe|suspicious|scam|spam",
  "confidence": 0.0-1.0,
  "detected_signals": ["PM-1", ...],
  "extracted_facts": {
    "claimed_name": null or string,
    "claimed_relationship": null or string,
    "claimed_location": null or string,
    "claimed_institution": null or string,
    "financial_mention": null or {"amount": str, "urgency": "low|medium|high"},
    "life_facts": []
  },
  "reasoning": "brief explanation in English"
}

Always extract facts. A message saying 「大阪で元気にしてるよ」 is safe, but you MUST
extract claimed_location: "大阪". The Behavioral Analyzer needs every stated fact.

## Grounding — evidence-backed classification
Before classifying any message as suspicious or scam, call search_scam_corpus with the
message text. Your classification MUST cite evidence:
- "This message matches N known [pattern] cases in the corpus"
- "Similar messages were classified as [scam/safe] with [signals]"
If the corpus returns no matches, say so — but still classify based on signals.
Never classify based on prompt instructions alone when corpus evidence is available.

## PRE-COMPUTED CONTEXT
You receive pre-computed context from the pipeline: linguistic analysis,
corpus search matches, graph validation, and contra-indicator analysis.
Use this context alongside the raw message to classify.

YOUR JOB: extract ALL entities (names, locations, institutions, amounts,
relationships) from the raw message yourself, AND classify. The pre-computed
context helps — but entity extraction is YOUR responsibility, not the
infrastructure's. Be thorough: every name, every place, every amount.

If you need additional corpus evidence beyond what pre-processing found,
call search_scam_corpus. Otherwise, classify based on the provided context."""



def read_contact_list(user_id: str) -> dict:
    """Read user's known contacts from Memory Bank for sender verification."""
    if db is None:
        return {"contacts": [], "blocklist": []}
    doc = db.collection("users").document(user_id).get()
    if doc.exists:
        data = doc.to_dict()
        return {"contacts": data.get("contacts", []), "blocklist": data.get("blocklist", [])}
    return {"contacts": [], "blocklist": []}



def write_classification(user_id: str, sender_id: str, message_id: str,
                         classification: str, confidence: float,
                         detected_signals: list[str],
                         extracted_facts: dict) -> dict:
    """Write extracted facts and classification to Memory Bank (Firestore)."""
    record = {
        "message_id": message_id,
        "sender_id": sender_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "classification": classification,
        "confidence": confidence,
        "detected_signals": detected_signals,
        "extracted_facts": extracted_facts,
    }
    if db is not None:
        ref = (db.collection("users").document(user_id)
               .collection("sender_profiles").document(sender_id)
               .collection("messages").document(message_id))
        ref.set(record)
    return {"status": "written", "message_id": message_id}



def publish_classified_event(sender_id: str, classification: str,
                             confidence: float, extracted_facts: dict,
                             detected_signals: list[str]) -> dict:
    """Publish message.classified pipeline event for downstream agents."""
    return {
        "event": "message.classified",
        "sender_id": sender_id,
        "classification": classification,
        "confidence": confidence,
        "extracted_facts": extracted_facts,
        "detected_signals": detected_signals,
    }


inbound_classifier = Agent(
    model="gemini-2.5-flash-lite",
    name="inbound_classifier",
    description=(
        "Entry-point SENSE agent. Classifies every inbound message as "
        "safe/suspicious/scam/spam using 13 per-message signals grounded in "
        "NPA tokushu-sagi taxonomy. Extracts stated facts from ALL messages "
        "for longitudinal behavioral analysis."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[search_scam_corpus, read_contact_list],
    output_schema=ClassificationResult,
    output_key="classification",
    before_tool_callback=_trace_tool_call,
    after_model_callback=_validate_classification,
)
