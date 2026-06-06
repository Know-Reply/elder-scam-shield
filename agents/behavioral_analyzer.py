"""Behavioral Analyzer — longitudinal profiling, trust-building detection, elder abuse detection.

Core innovation of Elder Scam Shield. Builds sender profiles across messages
and detects manipulation patterns BEFORE explicit scam signals appear.

Two detection modes:
  1. Stranger scam detection — time-series analysis of new/unknown contacts
  2. Elder abuse detection — behavioral shift analysis of known/trusted contacts

ADK primitives: INTERPRET + JUDGE
Signals: LG-1..LG-10 (legacy), BV-1..BV-5 (behavioral velocity), EA-1..EA-4 (elder abuse)
"""

from datetime import date, datetime, timezone

from google.adk import Agent
from agents.tools.search_scam_corpus import search_scam_corpus, get_corpus_pattern_stats
try:
    from google.cloud import firestore
except ImportError:
    firestore = None

import json as _json
from pathlib import Path as _Path

_BASELINES_PATH = _Path(__file__).parent.parent / "data" / "processed" / "corpus_baselines.json"

def _load_baselines() -> dict:
    if _BASELINES_PATH.exists():
        with open(_BASELINES_PATH) as f:
            return _json.load(f)
    return {}

_BASELINES = _load_baselines()

# ── Signal taxonomy ─────────────────────────────────────────────────────
#
# Legacy longitudinal signals (LG-1..10): per-message pattern matching
# Behavioral velocity signals (BV-1..5): time-series computations
# Elder abuse signals (EA-1..4): trusted-contact manipulation detection
# Cross-modal signals (CM-1): spending correlation
#
# Weights derived from corpus analysis where possible. BV and EA signals
# are structurally defined — they don't have direct corpus correlates
# because they require multi-message context that single-entry corpora
# can't capture.

_pm = _BASELINES.get("derived_weights", {})
SIGNAL_WEIGHTS = {
    # Legacy longitudinal (from corpus)
    "LG-1": round((_pm.get("PM-9", 0.10) + _pm.get("PM-2", 0.09)) / 2, 4),
    "LG-2": round((_pm.get("PM-11", 0.08) + _pm.get("PM-4", 0.07)) / 2, 4),
    "LG-3": 0.06,
    "LG-4": round(_pm.get("PM-12", 0.09), 4),
    "LG-5": round(_pm.get("PM-3", 0.09), 4),
    "LG-6": round(_pm.get("PM-2", 0.09), 4),
    "LG-7": 0.05,
    "LG-8": round((_pm.get("PM-10", 0.09) + _pm.get("PM-1", 0.09)) / 2, 4),
    "LG-9": round(_pm.get("PM-12", 0.09), 4),
    "LG-10": round(_pm.get("PM-5", 0.09), 4),
    # Behavioral velocity (time-series, stranger detection)
    "BV-1": 0.10,   # relationship_velocity — how fast is intimacy progressing?
    "BV-2": 0.12,   # isolation_index — cumulative isolation references
    "BV-3": 0.08,   # emotional_arc — sentiment trajectory prediction
    "BV-4": 0.07,   # credibility_seeding — unsolicited detail volunteering
    "BV-5": 0.08,   # help_positioning — systematic availability signaling
    # Elder abuse (trusted contact manipulation)
    "EA-1": 0.10,   # financial_control — known contact requesting money/savings info
    "EA-2": 0.12,   # trusted_isolation — known contact cutting off other family
    "EA-3": 0.08,   # authority_escalation — caregiver taking over decisions
    "EA-4": 0.08,   # communication_shift — sudden frequency/topic change from known contact
    # Cross-modal
    "CM-1": round(_pm.get("PM-3", 0.09), 4),
}

_total = sum(SIGNAL_WEIGHTS.values())
if _total > 0:
    SIGNAL_WEIGHTS = {k: round(v / _total, 4) for k, v in SIGNAL_WEIGHTS.items()}

# ── Firestore (optional for local dev) ──────────────────────────────────

try:
    db = firestore.Client() if firestore else None
except Exception:
    db = None
PROFILES = db.collection("sender_profiles") if db else None
CONTACTS = db.collection("user_contacts") if db else None
RISK_EVENTS = db.collection("risk_events") if db else None

# ── System prompt ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the Behavioral Analyzer for Elder Scam Shield, protecting elderly
Japanese users from TWO threat classes:
  1. Trust-building scams from strangers (特殊詐欺, ロマンス詐欺)
  2. Financial abuse from known/trusted contacts (高齢者虐待)

You analyze sender profiles over time to detect manipulation PATTERNS, not just
individual signals. Your goal is to flag danger BEFORE any explicit scam signal
(money request, bank details) appears.

══════════════════════════════════════════════════════════════
PART 1: STRANGER SCAM DETECTION — TIME-SERIES ANALYSIS
══════════════════════════════════════════════════════════════

For unknown/new contacts, compute these behavioral velocity metrics:

BV-1 RELATIONSHIP VELOCITY
  How fast is this relationship progressing? Measure intimacy level per day.
  - Day 1-2: introduction, shared interests → normal
  - Day 3-4: personal disclosures, "special connection" → accelerating
  - Day 4+: "call me anytime," "I worry about you" → abnormal velocity
  Score: 0.0 (normal pace) to 1.0 (dangerously fast)
  Baseline: legitimate new contacts take 2-4 weeks to reach personal topics.
  A stranger reaching "I'm here for you" in 4 days = velocity 0.8+

BV-2 ISOLATION INDEX
  Count references that distance the user from their verification network.
  Each instance adds to a cumulative score:
  - "Don't tell your father" → +0.3
  - "Your grandson is probably busy" → +0.2
  - "Just between us" → +0.3
  - "I'll handle it, don't bother anyone" → +0.2
  - "Don't go to the bank, I'll come to you" → +0.3
  Legitimate contacts do NOT systematically cut you off from other people.
  Score ≥0.5 from a stranger = strong manipulation signal.

BV-3 EMOTIONAL ARC
  Track sentiment trajectory across messages. Scams follow a predictable arc:
    polite → warm → intimate → concerned → urgent → desperate
  Legitimate relationships don't escalate on a 7-day schedule.
  Flag if emotional intensity increases >0.2 per message on average.

BV-4 CREDIBILITY SEEDING
  How much unsolicited personal detail is the sender volunteering?
  Real contacts don't need to prove who they are.
  Count instances of: job title, location, mutual connections, life history,
  "my father always spoke of you," specific knowledge of the user's life.
  Score: (detail_count / message_count). Normal <0.3. Seeding >0.6.

BV-5 HELP POSITIONING
  Detect systematic availability signaling from a stranger:
  - "If you need anything, call me" → +0.2
  - "I'm always here for you" → +0.2
  - "I worry about you living alone" → +0.3
  - "You can count on me" → +0.2
  From a 3-day stranger, this is grooming. From a 10-year friend, this is normal.
  Weight by relationship_age: score × (1.0 / max(days_known / 30, 1.0))

RISK SCORING FOR STRANGERS:
  By Day 4 with high velocity + isolation + help positioning:
    risk_score should be 0.35-0.45 — BEFORE any contradiction or money ask.
  The system should flag "this relationship is moving too fast" as the reason.

══════════════════════════════════════════════════════════════
PART 2: ELDER ABUSE DETECTION — TRUSTED CONTACT MONITORING
══════════════════════════════════════════════════════════════

For KNOWN contacts (whitelisted, verified, long history), detect these patterns.
These are MORE alarming than stranger signals because they come from trusted people.

EA-1 FINANCIAL CONTROL BY KNOWN CONTACT
  A family member or caregiver who starts:
  - Requesting money ("お母さん、ちょっとお金貸して" from a child is normal occasionally.
    But escalating amounts, increasing frequency, or directing savings = abuse signal)
  - Asking about savings/accounts ("通帳どこにある？" "年金いくら入ってる？")
  - Directing financial decisions ("その保険解約した方がいい" "私が管理するから")
  Threshold: 3+ financial references in 30 days from a single known contact.

EA-2 ISOLATION BY TRUSTED CONTACT
  Same mechanics as BV-2 but from someone already trusted:
  - "お姉さんには言わなくていいよ" (don't tell your sister)
  - "私がお金のこと全部やるから" (I'll handle all the money stuff)
  - "銀行に自分で行かなくていい" (you don't need to go to the bank yourself)
  Isolation language from a KNOWN contact is MORE alarming than from a stranger.
  Weight: EA-2 = BV-2 × 1.5 when sender is verified contact.

EA-3 AUTHORITY ESCALATION BY CAREGIVER
  Track the progression in a known contact's communication:
  Stage 1: helpful suggestions → "こうした方がいいよ"
  Stage 2: directing actions → "こうしなさい" "私がやっておくから"
  Stage 3: making demands → "言う通りにして" "余計なことしないで"
  Stage 4: controlling access → "電話しなくていい" "私が全部やる"
  Flag at Stage 2→3 transition. Stage 4 = critical alert.

EA-4 COMMUNICATION PATTERN SHIFT
  If a known contact who previously messaged monthly suddenly:
  - Messages daily (frequency spike >3x baseline)
  - Shifts topics to finances (topic_shift_score)
  - Increases directive language
  This behavioral change is itself the signal — not any single message.
  Compare current 7-day window vs 90-day baseline for the same contact.

IMPORTANT: This is NOT about accusing family members. It's about detecting
the same manipulation mechanics (isolation, emotional pressure, financial
control) regardless of sender. The system flags the PATTERN and lets the
family network review — the same way it handles stranger scams.

Japan's 高齢者虐待防止法 (Elder Abuse Prevention Act, 2006) specifically
addresses financial exploitation by family and caregivers.

══════════════════════════════════════════════════════════════
LEGACY SIGNALS (still active)
══════════════════════════════════════════════════════════════

LG-1 through LG-10 remain active for backward compatibility:
  LG-1: stated_fact_contradiction
  LG-2: contact_identity_mismatch
  LG-3: frequency_escalation
  LG-4: emotional_progression
  LG-5: financial_mention_timing
  LG-6: isolation_language_trend
  LG-7: persona_inconsistency
  LG-8: crisis_after_trust
  LG-9: rapid_intimacy
  LG-10: compliance_conditioning

CM-1: conversation_spending_correlation

══════════════════════════════════════════════════════════════
REASONING CHAIN
══════════════════════════════════════════════════════════════

1. RECEIVE classified message with extracted facts.
2. LOAD sender profile (or initialize if new).
3. LOAD user's contact list — determine if sender is KNOWN or STRANGER.
4. BRANCH:
   - STRANGER → compute BV-1..BV-5 + LG-1..LG-10
   - KNOWN CONTACT → compute EA-1..EA-4 + check for behavioral shifts
5. UPDATE sender profile with new facts and computed scores.
6. COMPUTE risk_score as weighted combination of all triggered signals.
7. PUBLISH sender.risk_updated with assessment, signals, and recommendation.

OUTPUT: structured JSON with sender_id, risk_score, risk_factors[],
  behavioral_velocity (for strangers) or abuse_indicators (for known contacts),
  recommendation (monitor|flag|block|alert_family).

GROUNDING: call get_corpus_pattern_stats and search_scam_corpus to cite evidence."""


def _empty_profile(sender_email: str) -> dict:
    return {
        "sender_email": sender_email,
        "first_seen": date.today().isoformat(),
        "message_count": 0,
        "contact_frequency": [],
        "is_known_contact": False,
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
        # Behavioral velocity metrics (stranger detection)
        "velocity_scores": {
            "relationship_velocity": 0.0,
            "isolation_index": 0.0,
            "emotional_arc": [],
            "credibility_seeding_count": 0,
            "help_positioning_score": 0.0,
        },
        # Elder abuse metrics (known contact monitoring)
        "abuse_indicators": {
            "financial_control_refs": 0,
            "isolation_refs": 0,
            "authority_stage": 0,
            "baseline_frequency": 0,
            "current_frequency": 0,
            "topic_shift_score": 0.0,
        },
    }


def load_sender_profile(sender_email: str) -> dict:
    """Load or initialize the sender's longitudinal profile from Memory Bank."""
    if PROFILES is None:
        return _empty_profile(sender_email)
    doc = PROFILES.document(sender_email).get()
    return doc.to_dict() if doc.exists else _empty_profile(sender_email)


def load_user_contacts(user_id: str) -> dict:
    """Load the user's verified contact list for cross-reference."""
    if CONTACTS is None:
        return {"contacts": []}
    doc = CONTACTS.document(user_id).get()
    return doc.to_dict() if doc.exists else {"contacts": []}


def update_sender_profile(sender_email: str, profile: dict) -> dict:
    """Write updated sender profile back to Memory Bank (Firestore)."""
    profile["last_updated"] = datetime.now(timezone.utc).isoformat()
    if PROFILES is not None:
        PROFILES.document(sender_email).set(profile)
    return profile


def compute_risk_score(detected_signals: list[str],
                       velocity_scores: dict = None,
                       abuse_indicators: dict = None,
                       is_known_contact: bool = False) -> dict:
    """Compute weighted risk score from detected signals and behavioral metrics.

    Args:
        detected_signals: Signal codes, e.g. ["LG-1", "BV-2", "EA-1"].
        velocity_scores: BV metrics dict (stranger detection).
        abuse_indicators: EA metrics dict (known contact monitoring).
        is_known_contact: Whether sender is in user's contact list.

    Returns:
        Dict with risk_score, recommendation, and breakdown.
    """
    # Base score from signal weights
    base_score = sum(SIGNAL_WEIGHTS.get(s, 0.0) for s in detected_signals)

    # Add behavioral velocity composite (strangers)
    bv_score = 0.0
    if velocity_scores and not is_known_contact:
        bv_score = (
            velocity_scores.get("relationship_velocity", 0) * 0.3 +
            velocity_scores.get("isolation_index", 0) * 0.3 +
            velocity_scores.get("help_positioning_score", 0) * 0.2 +
            min(velocity_scores.get("credibility_seeding_count", 0) / 5, 1.0) * 0.1 +
            (len(velocity_scores.get("emotional_arc", [])) > 3) * 0.1
        )

    # Add elder abuse composite (known contacts)
    ea_score = 0.0
    if abuse_indicators and is_known_contact:
        ea_score = (
            min(abuse_indicators.get("financial_control_refs", 0) / 3, 1.0) * 0.3 +
            min(abuse_indicators.get("isolation_refs", 0) / 3, 1.0) * 0.3 +
            min(abuse_indicators.get("authority_stage", 0) / 4, 1.0) * 0.2 +
            abuse_indicators.get("topic_shift_score", 0) * 0.2
        )
        # Isolation from known contact is 1.5x more alarming
        ea_score *= 1.2

    score = min(base_score + bv_score * 0.4 + ea_score * 0.4, 1.0)
    score = round(score, 3)

    if score >= 0.7:
        rec = "block"
    elif score >= 0.4:
        rec = "flag"
    elif score >= 0.25:
        rec = "monitor"
    else:
        rec = "safe"

    return {
        "risk_score": score,
        "recommendation": rec,
        "breakdown": {
            "signal_weight_score": round(base_score, 3),
            "behavioral_velocity_score": round(bv_score, 3),
            "elder_abuse_score": round(ea_score, 3),
            "is_known_contact": is_known_contact,
        },
    }


def publish_risk_assessment(
    sender_id: str,
    risk_score: float,
    risk_factors: list[str],
    contradiction_details: list[dict],
    recommendation: str,
    behavioral_velocity: dict = None,
    abuse_indicators: dict = None,
) -> dict:
    """Publish sender.risk_updated event via A2A for downstream agents."""
    event = {
        "event_type": "sender.risk_updated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender_id": sender_id,
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "contradiction_details": contradiction_details,
        "recommendation": recommendation,
    }
    if behavioral_velocity:
        event["behavioral_velocity"] = behavioral_velocity
    if abuse_indicators:
        event["abuse_indicators"] = abuse_indicators
    if RISK_EVENTS is not None:
        RISK_EVENTS.document(f"{sender_id}_{event['timestamp']}").set(event)
    return event


behavioral_analyzer = Agent(
    model="gemini-2.5-flash",
    name="behavioral_analyzer",
    description=(
        "Builds longitudinal sender profiles with time-series behavioral analysis. "
        "Detects trust-building scams from strangers via velocity scoring, isolation "
        "index, and emotional arc detection — flagging danger BEFORE explicit scam "
        "signals appear. Also detects financial abuse from known/trusted contacts "
        "via authority escalation, communication shift, and isolation monitoring. "
        "References Japan's 高齢者虐待防止法 (Elder Abuse Prevention Act)."
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
