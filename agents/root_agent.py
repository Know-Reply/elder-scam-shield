"""Elder Scam Shield — root agent composing 4 sub-agents with A2A event routing.

Entry point for ADK. Orchestrates the scam protection pipeline:
  Inbound Classifier → Behavioral Analyzer → Outbound Interceptor → Family Alerter

A2A event chain:
  message.classified → sender.risk_updated → outbound.held → alert.delivered
"""

from google.adk.agents import Agent
from google.adk.tools import tool
from google.cloud import firestore

from .inbound_classifier import inbound_classifier
from .behavioral_analyzer import behavioral_analyzer
from .outbound_interceptor import outbound_interceptor
from .family_alerter import family_alerter

db = firestore.Client()


@tool
def route_classified_event(event: dict) -> dict:
    """Route a message.classified event to the Behavioral Analyzer.

    Called after the Inbound Classifier produces a classification.
    Passes sender_id, extracted_facts, and detected_signals to the
    Behavioral Analyzer for longitudinal profile update.
    """
    return {
        "route_to": "behavioral_analyzer",
        "event_type": "message.classified",
        "payload": event,
    }


@tool
def route_risk_event(event: dict) -> dict:
    """Route a sender.risk_updated event to downstream agents.

    When the Behavioral Analyzer publishes a risk update:
    - Outbound Interceptor receives it for hold-decision context.
    - Family Alerter receives it if risk_score > 0.6 (notification threshold).
    """
    targets = ["outbound_interceptor"]
    if event.get("risk_score", 0) > 0.6:
        targets.append("family_alerter")
    return {
        "route_to": targets,
        "event_type": "sender.risk_updated",
        "payload": event,
    }


@tool
def route_hold_event(event: dict) -> dict:
    """Route an outbound.held event to the Family Alerter.

    Every hold triggers a family notification — the human-in-the-loop
    decides whether to release.
    """
    return {
        "route_to": "family_alerter",
        "event_type": "outbound.held",
        "payload": event,
    }


root_agent = Agent(
    model="gemini-2.0-flash",
    name="elder_scam_shield",
    description=(
        "Elder Scam Shield — multi-agent scam protection for elderly Japanese "
        "users. Orchestrates 4 sub-agents via A2A events: classify inbound "
        "messages, build longitudinal sender profiles, intercept outbound "
        "sensitive data, and alert family members."
    ),
    instruction=(
        "You are the orchestrator for Elder Scam Shield. Route messages "
        "through the pipeline:\n\n"
        "1. INBOUND: Send every incoming message to inbound_classifier.\n"
        "2. CLASSIFY → ANALYZE: When inbound_classifier returns, call "
        "route_classified_event to pass the result to behavioral_analyzer.\n"
        "3. RISK → INTERCEPT/ALERT: When behavioral_analyzer returns, call "
        "route_risk_event. If risk > 0.6, family_alerter is also notified.\n"
        "4. OUTBOUND: When the user sends a reply, send it to "
        "outbound_interceptor with the sender's current risk context.\n"
        "5. HOLD → ALERT: When outbound_interceptor holds content, call "
        "route_hold_event to notify the family.\n\n"
        "Never surface scam message content in your own responses. "
        "Report pipeline status using signal codes and risk scores only."
    ),
    tools=[route_classified_event, route_risk_event, route_hold_event],
    sub_agents=[
        inbound_classifier,
        behavioral_analyzer,
        outbound_interceptor,
        family_alerter,
    ],
)
