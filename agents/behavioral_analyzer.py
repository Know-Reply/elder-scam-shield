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
from agents.tools.social_graph import validate_social_graph
from agents.tools.graph_builder import update_graph_from_message, check_cross_references
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

GROUNDING: call get_corpus_pattern_stats and search_scam_corpus to cite evidence.

ADAPTIVE PER-USER BASELINES (Round 5):
  Before scoring, call load_user_baselines to get THIS user's communication norms.
  Pass user_baselines + sender_history_days + sender_message_count to compute_risk_score.
  A known contact with 3 years of history gets up to -0.3 risk reduction.
  A contact whose message frequency is within 2x of user's normal gets -0.1.
  A user who regularly discusses finances gets -0.05 when known contacts mention money.
  This eliminates false positives on active family members asking for legitimate help.

SOCIAL GRAPH VALIDATION (Round 4):
  Before deep behavioral analysis, call validate_social_graph to check whether
  the sender has ANY connection to the user's known contact network.
  - graph_distance 0 (direct contact) with long history → risk reduction (-0.2)
  - graph_distance 1 (friend-of-friend) → neutral
  - graph_distance -1 with a claimed relationship → IMPOSTER SIGNAL (+0.3)
  Incorporate graph_risk_modifier into the final risk_score computation."""


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


def load_user_baselines(user_id: str) -> dict:
    """Load per-user communication baselines from Memory Bank.

    Adaptive baselines (Round 5): instead of population thresholds, compare
    against THIS user's normal patterns. A user who gets 5 messages/day from
    known contacts has a different "normal" than one who gets 1/week.

    Returns baseline dict with frequency, topic, and tone norms.
    """
    if db is not None:
        doc = db.collection("user_baselines").document(user_id).get()
        if doc.exists:
            return doc.to_dict()
    # Default baselines for users without history
    return {
        "avg_messages_per_day": 1.0,
        "avg_messages_per_contact_per_week": 2.0,
        "known_contact_count": 4,
        "typical_financial_mentions_per_month": 1,
        "typical_topics": ["health", "family", "daily_life"],
        "communication_style": "formal",
    }


def compute_risk_score(detected_signals: list[str],
                       velocity_scores: dict = None,
                       abuse_indicators: dict = None,
                       is_known_contact: bool = False,
                       graph_risk_modifier: float = 0.0,
                       user_baselines: dict = None,
                       sender_history_days: int = 0,
                       sender_message_count: int = 0) -> dict:
    """Compute weighted risk score from detected signals and behavioral metrics.

    Args:
        detected_signals: Signal codes, e.g. ["LG-1", "BV-2", "EA-1"].
        velocity_scores: BV metrics dict (stranger detection).
        abuse_indicators: EA metrics dict (known contact monitoring).
        is_known_contact: Whether sender is in user's contact list.
        graph_risk_modifier: From validate_social_graph (-0.2 to +0.3).
        user_baselines: Per-user communication norms (Round 5 adaptive).
        sender_history_days: How many days of history with this sender.
        sender_message_count: Total messages from this sender.

    Returns:
        Dict with risk_score, recommendation, and breakdown.
    """
    baselines = user_baselines or {}

    # Base score from signal weights
    base_score = sum(SIGNAL_WEIGHTS.get(s, 0.0) for s in detected_signals)

    # ── Adaptive baseline adjustments (Round 5) ────────────────────────
    # Known contacts with established history get risk reduction.
    # The longer the history, the more trust earned.
    adaptive_modifier = 0.0
    if is_known_contact and sender_history_days > 0:
        # Long-established contacts get risk reduction
        history_trust = min(sender_history_days / 365, 0.3)  # max 0.3 reduction for 1yr+
        adaptive_modifier -= history_trust

        # Active contacts (frequent messaging) get velocity threshold relaxation
        if sender_message_count > 0:
            msg_per_day = sender_message_count / max(sender_history_days, 1)
            user_normal = baselines.get("avg_messages_per_contact_per_week", 2.0) / 7.0
            # If this contact's frequency is within 2x of user's normal, no velocity alarm
            if msg_per_day <= user_normal * 2:
                adaptive_modifier -= 0.1  # frequency is within normal range

        # Financial mentions from known contacts with financial history are less alarming
        if baselines.get("typical_financial_mentions_per_month", 0) >= 2:
            # User regularly discusses finances — don't over-flag
            if "PM-3" in detected_signals or "LG-5" in detected_signals:
                adaptive_modifier -= 0.05

    # ── Behavioral velocity composite (strangers) ──────────────────────
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

    # Combine all components
    raw_score = base_score + bv_score * 0.4 + ea_score * 0.4
    # Apply modifiers: graph validation (Round 4) + adaptive baselines (Round 5)
    raw_score += graph_risk_modifier
    raw_score += adaptive_modifier
    score = round(max(min(raw_score, 1.0), 0.0), 3)

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
            "graph_risk_modifier": round(graph_risk_modifier, 3),
            "adaptive_modifier": round(adaptive_modifier, 3),
            "is_known_contact": is_known_contact,
            "sender_history_days": sender_history_days,
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
    model="gemini-3.1-flash-lite",
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
        load_user_baselines,
        update_sender_profile,
        compute_risk_score,
        publish_risk_assessment,
        search_scam_corpus,
        get_corpus_pattern_stats,
        validate_social_graph,
        check_cross_references,
    ],
    sub_agents=[],
)
