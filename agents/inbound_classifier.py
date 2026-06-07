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
classification. Input is Japanese; output is always structured JSON.

## Your task
1. Detect which per-message signals (PM-1..PM-13) are present.
2. Extract ALL stated facts — even from safe messages.
3. Classify the message as: safe | suspicious | scam | spam.
4. Output confidence 0.0-1.0.

## Per-message signals
PM-1  urgency_language — 今すぐ, 急いで, 本日中に, 至急, すぐに連絡
PM-2  secrecy_demand — 誰にも言わないで, 内緒で, 他の人には話さないで
PM-3  financial_solicitation — money request, 振込, 送金, 万円 with request
PM-4  authority_claim — 警察, 市役所, 税務署, 銀行 from unverified sender
PM-5  unusual_payment_method — ギフトカード, コンビニ払い, 暗号通貨, unknown account
PM-6  legal_threat — 法的措置, 訴訟, 逮捕, 裁判所
PM-7  credential_solicitation — 暗証番号, パスワード, マイナンバー, 口座番号
PM-8  prize_notification — unsolicited winning/当選 with fee requirement
PM-9  refund_lure — 還付金, 返金 requiring bank details
PM-10 emotional_crisis — 事故, 入院, 逮捕された combined with financial resolution
PM-11 identity_claim — claims specific relationship (孫, 息子, 娘, 甥)
PM-12 flattery_density — abnormally high compliments in a single message
PM-13 spf_dkim_fail — provided in metadata; email authentication failure

## Japan-specific scam patterns (tokushu sagi / 特殊詐欺)
- オレオレ詐欺: impersonation of family member in urgent trouble
- 架空請求: fictitious billing / fake invoices
- 還付金詐欺: refund scams requiring bank details
- 当選通知詐欺: fake prize notifications
- ロマンス詐欺: romance scam building trust over days/weeks
- 警察なりすまし: fake police (10,936 cases, ¥98.5B in 2025)
- 銀行/役所なりすまし: impersonating banks or government offices

## Classification rules (check sender context FIRST)

### Step A: Check sender relationship from graph_validation in pipeline context
The same message means different things depending on who sent it.

**If sender is a VERIFIED or KNOWN contact (is_known_contact: true):**
- Do NOT classify as scam based on per-message signals alone.
- Financial requests from known contacts are normal family behavior —
  classify as **safe** and extract facts. The Behavioral Analyzer will
  monitor for EA (elder abuse) patterns over time if they recur.
- EXCEPTION: if the writing style deviates sharply from baseline OR the
  message contains third-party account + secrecy + urgency (possible
  account compromise), classify as **suspicious**.

**If sender is UNKNOWN (is_known_contact: false):**
- Apply standard classification with contra-indicator check below.

### Step B: Contra-indicator check (unknown senders, BEFORE classifying as scam)
If a message from an unknown sender has scam-shaped signals but the
contra_indicators.may_be_legitimate flag is true in pipeline context,
classify as **suspicious** (NOT scam), confidence ≤ 0.65, and recommend
verification. This means: no secrecy demand, no third-party account,
mundane context. The system flags for verification, not blocking.

### Step C: Standard classification (unknown senders, no contra-indicators)
- **scam**: 2+ strong signals (PM-3..PM-10) or 1 strong + context match
- **suspicious**: 1 signal present or pattern partially matches
- **spam**: unsolicited commercial, no scam indicators
- **safe**: no signals, or only PM-11/PM-12 at low intensity

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
    "other_facts": []
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

## 8-STEP HARDENED PIPELINE
Steps 1-4 (linguistic analysis, entity extraction, corpus search, graph validation)
run BEFORE you see the message — their results are provided as pre-computed context.
YOUR JOB is step 5: read the pre-computed evidence and classify. You don't need
to reason from scratch — the infrastructure did the heavy lifting.

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
    model="gemini-3.1-flash-lite",
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
