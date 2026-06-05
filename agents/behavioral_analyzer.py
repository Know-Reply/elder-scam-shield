"""Behavioral Analyzer agent — longitudinal sender profiling and contradiction detection.

Builds sender profiles across messages, detects trust-building attack patterns
that per-message classifiers miss. Core innovation of Elder Scam Shield.

ADK primitives: INTERPRET + JUDGE
Signals: LG-1..LG-10 (longitudinal), CM-1 (cross-modal)
"""

from datetime import date, datetime, timezone

from google.adk import Agent
from agents.tools.search_scam_corpus import search_scam_corpus, get_corpus_pattern_stats
from google.cloud import firestore

SIGNAL_WEIGHTS = {
    "LG-1": 0.15,  # stated_fact_contradiction
    "LG-2": 0.15,  # contact_identity_mismatch
    "LG-3": 0.08,  # frequency_escalation
    "LG-4": 0.10,  # emotional_progression
    "LG-5": 0.12,  # financial_mention_timing
    "LG-6": 0.08,  # isolation_language_trend
    "LG-7": 0.07,  # persona_inconsistency
    "LG-8": 0.10,  # crisis_after_trust
    "LG-9": 0.05,  # rapid_intimacy
    "LG-10": 0.05, # compliance_conditioning
    "CM-1": 0.05,  # conversation_spending_correlation
}

db = firestore.Client()
PROFILES = db.collection("sender_profiles")
CONTACTS = db.collection("user_contacts")
RISK_EVENTS = db.collection("risk_events")

SYSTEM_PROMPT = """You are the Behavioral Analyzer for Elder Scam Shield, protecting elderly
Japanese users from trust-building scams (特殊詐欺).

REASONING CHAIN — execute on every message.classified event:

1. RECEIVE the classified message with extracted facts (sender, claims, sentiment).
2. LOAD the sender's full profile from Memory Bank (or initialize if first contact).
3. LOAD the user's known contact list for cross-reference.
4. EXTRACT new stated facts: claimed name, relationship, location, institution, timeline.
5. CHECK CONTRADICTIONS against all previously stored facts for this sender.
6. DETECT LONGITUDINAL SIGNALS (LG-1 through LG-10):
   - LG-1: Do new facts contradict previous claims? (location, job, relationship)
   - LG-2: Does claimed identity match user's actual contacts?
   - LG-3: Is message frequency accelerating? (compare contact_frequency windows)
   - LG-4: Has emotional tone progressed from casual → intimate → urgent?
   - LG-5: First financial mention timing — suspicious if after day 5+ of rapport.
   - LG-6: Increasing requests for secrecy or isolation?
   - LG-7: Writing style or formality shifts between messages?
   - LG-8: Emergency narrative appearing after trust was established?
   - LG-9: Relationship depth advancing faster than cultural baseline?
   - LG-10: Small compliance requests escalating to larger ones?
7. DETECT CROSS-MODAL SIGNALS:
   - CM-1: Correlation between conversation intensity and user spending patterns.
8. COMPUTE risk_score as weighted combination of detected signals.
9. UPDATE sender profile in Memory Bank with accumulated facts and new score.
10. PUBLISH sender.risk_updated with assessment and recommendation.

OUTPUT must be structured JSON with: sender_id, risk_score (0.0-1.0), risk_factors[],
contradiction_details[], recommendation (monitor|flag|block).

CULTURAL CONTEXT: Japanese elderly are especially vulnerable to オレオレ詐欺 (impersonation
fraud) and ロマンス詐欺 (romance scams). Respect for claimed family bonds makes
contradiction detection critical — the user will not question a "grandchild" themselves.

GROUNDING — corpus-backed risk assessment:
When you detect a pattern, call get_corpus_pattern_stats with the scam_type slug to cite
evidence: "In N confirmed [pattern] cases, [signal] appeared in X% of cases by Day Y."
Call search_scam_corpus when the sender profile shows accumulated risk, to find similar
known scam progressions. Your risk assessments must cite evidence, not just signal weights."""


def _empty_profile(sender_email: str) -> dict:
    return {
        "sender_email": sender_email,
        "first_seen": date.today().isoformat(),
        "message_count": 0,
        "contact_frequency": [],
        "stated_facts": {
            "claimed_name": [],
            "claimed_relationship": [],
            "claimed_locations": [],
            "claimed_institution": [],
            "financial_mentions": [],
        },
        "verified_against_contacts": {"match": None},
        "contradiction_count": 0,
        "risk_score": 0.0,
        "risk_factors": [],
    }



def load_sender_profile(sender_email: str) -> dict:
    """Load or initialize the sender's longitudinal profile from Memory Bank."""
    doc = PROFILES.document(sender_email).get()
    return doc.to_dict() if doc.exists else _empty_profile(sender_email)



def load_user_contacts(user_id: str) -> dict:
    """Load the user's verified contact list for cross-reference."""
    doc = CONTACTS.document(user_id).get()
    return doc.to_dict() if doc.exists else {"contacts": []}



def update_sender_profile(sender_email: str, profile: dict) -> dict:
    """Write updated sender profile back to Memory Bank (Firestore)."""
    profile["last_updated"] = datetime.now(timezone.utc).isoformat()
    PROFILES.document(sender_email).set(profile)
    return profile



def compute_risk_score(detected_signals: list[str]) -> dict:
    """Compute weighted risk score from detected longitudinal signal codes.

    Args:
        detected_signals: List of signal codes, e.g. ["LG-1", "LG-2", "LG-5", "CM-1"].

    Returns:
        Dict with risk_score (0.0-1.0) and recommendation (monitor|flag|block).
    """
    score = sum(SIGNAL_WEIGHTS.get(s, 0.0) for s in detected_signals)
    score = min(score, 1.0)
    if score >= 0.7:
        rec = "block"
    elif score >= 0.4:
        rec = "flag"
    else:
        rec = "monitor"
    return {"risk_score": round(score, 3), "recommendation": rec}



def publish_risk_assessment(
    sender_id: str,
    risk_score: float,
    risk_factors: list[str],
    contradiction_details: list[dict],
    recommendation: str,
) -> dict:
    """Publish sender.risk_updated event via A2A for downstream agents.

    Consumed by: Outbound Interceptor (context for hold decisions),
    Family Alerter (notification trigger).
    """
    event = {
        "event_type": "sender.risk_updated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender_id": sender_id,
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "contradiction_details": contradiction_details,
        "recommendation": recommendation,
    }
    RISK_EVENTS.document(f"{sender_id}_{event['timestamp']}").set(event)
    return event


behavioral_analyzer = Agent(
    model="gemini-2.5-pro",
    name="behavioral_analyzer",
    description=(
        "Builds longitudinal sender profiles, detects fact contradictions, "
        "cross-references against known contacts, and publishes risk assessments. "
        "Catches trust-building scams that per-message classifiers miss."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[
        load_sender_profile,
        load_user_contacts,
        update_sender_profile,
        compute_risk_score,
        publish_risk_assessment,
        search_scam_corpus,
        get_corpus_pattern_stats,
    ],
    sub_agents=[],
)
