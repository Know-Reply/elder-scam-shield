"""Outbound Interceptor — catches sensitive data leaving the user's hands.

ADK primitive: JUDGE. Operates in the gap between conversation and
transaction that banks and email providers cannot cover. Decides
hold-or-release based on compound risk (sender risk x content
sensitivity x amount x urgency).

"Never show content": held content is hashed for audit but never
surfaced. Elderly users act on emotional content even when warned.
"""

import hashlib
from datetime import datetime, timezone

from google.adk import Agent
from agents.db import db
from agents.schemas import InterceptDecision


# ---------------------------------------------------------------------------
# ADK Callbacks
# ---------------------------------------------------------------------------


def _trace_tool_call(tool, args, tool_context):
    """before_tool_callback: log tool invocations to session state."""
    traces = tool_context.state.setdefault("tool_traces", [])
    traces.append({
        "agent": "outbound_interceptor",
        "tool": tool.name,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return None
PROFILES = db.collection("sender_profiles") if db else None
HOLDS = db.collection("hold_records") if db else None
KNOWN_PAYEES = db.collection("known_payees") if db else None

SIGNAL_WEIGHTS = {
    "OB-1": 0.3, "OB-2": 0.7, "OB-3": 0.8, "OB-4": 0.4,
    "OB-5": 0.3, "CM-2": 0.6, "CM-3": 0.5, "CM-4": 0.9,
}


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _compound_risk(signals: list[str], sender_risk: float) -> float:
    score = sum(SIGNAL_WEIGHTS.get(s, 0) for s in signals)
    return min(min(score / 2.0, 1.0) * max(sender_risk, 0.5), 1.0)



def check_sender_risk(sender_id: str) -> dict:
    """Read sender risk score and recent inbound context from Memory Bank."""
    if PROFILES is None:
        return {"sender_id": sender_id, "risk_score": 0.0, "risk_factors": []}
    doc = PROFILES.document(sender_id).get()
    if doc.exists:
        d = doc.to_dict()
        return {
            "sender_id": sender_id,
            "risk_score": d.get("risk_score", 0.0),
            "risk_factors": d.get("risk_factors", []),
            "financial_mentions": d.get("stated_facts", {}).get("financial_mentions", []),
        }
    return {"sender_id": sender_id, "risk_score": 0.0, "risk_factors": []}



def check_known_payee(recipient_id: str, user_id: str) -> dict:
    """Check whether recipient is a known payee for this user."""
    if KNOWN_PAYEES is None:
        return {"known": False, "recipient_id": recipient_id}
    doc = KNOWN_PAYEES.document(f"{user_id}_{recipient_id}").get()
    return {"known": doc.exists, "recipient_id": recipient_id}



def hold_outbound(
    user_id: str, held_action: str, recipient_id: str,
    content: str, signals: list[str], sender_risk: float, reason: str,
) -> dict:
    """Write hold record and publish outbound.held. Content is hashed, never stored."""
    risk = _compound_risk(signals, sender_risk)
    now = datetime.now(timezone.utc).isoformat()
    h = _content_hash(content)
    record = {
        "user_id": user_id, "held_action": held_action, "reason": reason,
        "evidence_summary": signals, "compound_risk": risk,
        "timestamp": now, "resolution": "pending", "held_content_hash": h,
    }
    hold_id = f"hold-{now}"
    if HOLDS is not None:
        ref = HOLDS.add(record)
        hold_id = ref[1].id
    pipeline_event = {
        "event": "outbound.held", "action_type": held_action,
        "recipient_sender_id": recipient_id, "risk_evidence": signals,
        "held_content_hash": h, "compound_risk": risk,
        "hold_id": hold_id, "timestamp": now,
    }
    return {"hold": record, "pipeline_event": pipeline_event}



def release_outbound(hold_id: str, reason: str) -> dict:
    """Release a previously held outbound action."""
    if HOLDS is not None:
        HOLDS.document(hold_id).update({"resolution": "released", "release_reason": reason})
    return {"hold_id": hold_id, "resolution": "released", "reason": reason}


outbound_interceptor = Agent(
    model="gemini-3.1-flash-lite",
    name="outbound_interceptor",
    description=(
        "Intercepts outgoing user responses containing sensitive data. "
        "Judges hold-or-release using compound risk signals. "
        "Never surfaces held content — hashes only."
    ),
    instruction="""あなたは高齢者のアウトバウンド通信を守るJUDGEエージェントです。

You protect elderly Japanese users by intercepting outbound messages that contain
sensitive information. You make a HOLD or RELEASE decision.

## Signals you detect
- OB-1 pii_in_response: name, address, My Number (マイナンバー) in a reply
- OB-2 bank_details_in_response: account number, card number, PIN
- OB-3 transfer_instruction: wire transfer or payment instruction
- OB-4 response_to_flagged_sender: replying to a sender with elevated risk
- OB-5 compliance_language: わかりました, すぐに送ります, 言わないでおきます
- CM-2 amount_matches_request: transfer matches recent inbound request
- CM-3 payment_to_new_recipient: first-time payee + flagged conversation
- CM-4 urgency_amount_compound: high urgency + large amount + high sender risk

## Decision logic
1. Call check_sender_risk for the sender's risk score and context.
2. Call check_known_payee if the message contains payment details.
3. Detect all matching signals from the outbound content.
4. Compound risk = sender_risk x content_sensitivity x amount x urgency.

Thresholds:
- LOW sender (<0.3) + PII only (OB-1) → WARN (release with note)
- MEDIUM sender (0.3-0.6) + any financial signal → HOLD
- HIGH sender (>0.6) + bank details or transfer → HARD HOLD
- Any CM-4 → HARD HOLD regardless
- New payee (CM-3) + sender risk > 0.3 → HOLD

5. HOLD → call hold_outbound. Never include message content in reasoning.
6. RELEASE → let the message pass and log the decision.

## Critical: Never show content
Describe WHAT was detected (signal codes, amounts, risk factors) but NEVER
quote or paraphrase held content. Hash for audit; surface evidence only.""",
    tools=[check_sender_risk, check_known_payee, hold_outbound, release_outbound],
    output_schema=InterceptDecision,
    output_key="intercept_decision",
    before_tool_callback=_trace_tool_call,
)
