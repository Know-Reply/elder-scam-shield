"""Pre-classification pipeline — context the LLM can't compute itself.

Three pre-processing steps run BEFORE the LLM, providing evidence
from infrastructure (corpus, graph, structural analysis). The LLM
then classifies and extracts entities — that's its job, not regex.

Pre-LLM steps (pure Python, ~50ms, no API calls):
  1. Linguistic Analysis       — manipulation density, style fingerprint
  2. Corpus Search             — TF-IDF over 22,979 entries
  3. Social Graph Validation   — contact verification, imposter detection
  3.5 Contra-Indicator Check   — evidence FOR legitimacy, not just against

LLM step (Gemini flash-lite, ~0.9s):
  4. Classification + Entity Extraction — output_schema enforced

Post-classification (separate agents in Workflow):
  - Behavioral Analyzer — longitudinal profiling (async)
  - Family Alerter — conditional on risk > 0.6
  - Conversation Knowledge Graph — provenance tracking
"""

import re


# ── Step 1: Linguistic Analysis ─────────────────────────────────────────

# Emotional manipulation keyword sets (research-documented patterns)
_URGENCY_WORDS = {
    "en": {"urgent", "immediately", "right now", "today", "asap", "hurry",
           "deadline", "expires", "last chance", "act now", "don't delay",
           "time sensitive", "within 24"},
    "ja": {"今すぐ", "急いで", "至急", "本日中", "すぐに", "直ちに", "緊急",
           "期限", "大至急"},
}
_GUILT_WORDS = {
    "en": {"disappointed", "let down", "counting on you", "only you",
           "no one else", "please help", "i beg", "desperate", "ashamed",
           "embarrassed", "sorry to ask", "hate to ask"},
    "ja": {"お願い", "頼む", "情けない", "申し訳", "すみません", "助けて",
           "頼り", "迷惑", "心配"},
}
_FLATTERY_WORDS = {
    "en": {"wonderful", "amazing", "special", "beautiful", "kind",
           "generous", "dear", "beloved", "sweetheart", "darling",
           "my love", "incredible", "extraordinary"},
    "ja": {"素敵", "素晴らしい", "優しい", "特別", "大切", "愛して",
           "すごい", "立派"},
}
_SECRECY_WORDS = {
    "en": {"don't tell", "keep secret", "between us", "confidential",
           "private matter", "don't share", "just between"},
    "ja": {"誰にも言わないで", "内緒", "秘密", "他の人には", "言わないで"},
}


def _detect_language(text: str) -> str:
    """Detect if text is primarily Japanese or English."""
    cjk = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text))
    ascii_alpha = len(re.findall(r'[a-zA-Z]', text))
    return "ja" if cjk > ascii_alpha else "en"


def _count_keyword_matches(text: str, keyword_set: dict, language: str) -> int:
    """Count keyword matches in text."""
    text_lower = text.lower()
    count = 0
    for word in keyword_set.get(language, set()) | keyword_set.get("en", set()):
        if word in text_lower:
            count += 1
    return count


def linguistic_analysis(text: str, sender_style_baseline: dict = None) -> dict:
    """Step 1: Lightweight linguistic analysis — no LLM needed.

    Computes:
    - Writing style fingerprint (length, complexity, punctuation)
    - Emotional manipulation density (urgency + guilt + flattery + secrecy)
    - Style deviation from sender's baseline (if available)

    Returns a pre-computed signal bundle that feeds into the Classifier.
    """
    language = _detect_language(text)
    words = text.split()
    word_count = len(words)
    char_count = len(text)

    # Writing style fingerprint
    avg_word_length = sum(len(w) for w in words) / max(word_count, 1)
    unique_words = len(set(w.lower() for w in words))
    vocabulary_richness = unique_words / max(word_count, 1)
    exclamation_count = text.count("!") + text.count("！")
    question_count = text.count("?") + text.count("？")
    ellipsis_count = text.count("...") + text.count("…")

    style = {
        "word_count": word_count,
        "char_count": char_count,
        "avg_word_length": round(avg_word_length, 2),
        "vocabulary_richness": round(vocabulary_richness, 3),
        "exclamation_density": round(exclamation_count / max(word_count, 1), 3),
        "question_density": round(question_count / max(word_count, 1), 3),
        "ellipsis_count": ellipsis_count,
    }

    # Emotional manipulation density
    urgency = _count_keyword_matches(text, _URGENCY_WORDS, language)
    guilt = _count_keyword_matches(text, _GUILT_WORDS, language)
    flattery = _count_keyword_matches(text, _FLATTERY_WORDS, language)
    secrecy = _count_keyword_matches(text, _SECRECY_WORDS, language)

    manipulation_score = (urgency * 0.3 + guilt * 0.25 + flattery * 0.2 + secrecy * 0.25)
    manipulation_density = round(manipulation_score / max(word_count / 10, 1), 3)

    manipulation = {
        "urgency_count": urgency,
        "guilt_count": guilt,
        "flattery_count": flattery,
        "secrecy_count": secrecy,
        "manipulation_density": min(manipulation_density, 1.0),
        "manipulation_signals": [],
    }
    if urgency > 0: manipulation["manipulation_signals"].append(f"urgency({urgency})")
    if guilt > 0: manipulation["manipulation_signals"].append(f"guilt({guilt})")
    if flattery > 0: manipulation["manipulation_signals"].append(f"flattery({flattery})")
    if secrecy > 0: manipulation["manipulation_signals"].append(f"secrecy({secrecy})")

    # Style deviation from baseline (if sender has history)
    style_deviation = 0.0
    if sender_style_baseline:
        baseline_len = sender_style_baseline.get("avg_word_count", word_count)
        baseline_vocab = sender_style_baseline.get("avg_vocabulary_richness", vocabulary_richness)
        len_dev = abs(word_count - baseline_len) / max(baseline_len, 1)
        vocab_dev = abs(vocabulary_richness - baseline_vocab) / max(baseline_vocab, 0.01)
        style_deviation = round(min((len_dev + vocab_dev) / 2, 1.0), 3)

    return {
        "language": language,
        "style": style,
        "manipulation": manipulation,
        "style_deviation": style_deviation,
        "style_deviation_flag": style_deviation > 0.5,
    }


# ── ConversationRiskLedger — deterministic scoring from LLM-detected signals ──

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ── Signal weights ──────────────────────────────────────────────────────
#
# Calibration basis: NPA tokushu-sagi (special fraud) annual reports 2023-2025.
#
# Tier 1 (informational, weight 0.08-0.10): Identity claims and flattery are
# present in >90% of legitimate first-contact messages as well as scam openers.
# They carry near-zero weight alone but activate the T1 primer bonus when
# followed by T2/T3 signals — modeling the grooming-then-escalation pattern
# documented in 89% of multi-day ore-ore cases (NPA 2024 report, p.47).
#
# Tier 2 (moderate, weight 0.22-0.28): Urgency, authority claims, and emotional
# crisis are manipulation accelerants. They appear in both scam and legitimate
# contexts (real emergencies exist) but compound meaningfully with T1 priming.
# Authority claims (PM-4) weight lower than emotional crisis (PM-10) because
# authority impersonation is more common in spam than in targeted elder fraud.
#
# Tier 3 (strong, weight 0.32-0.55): These signals have near-zero benign
# occurrence in elder communication. Unusual payment methods (PM-5, 0.50) are
# highest because gift card / crypto payments have essentially no legitimate
# use in Japanese elder correspondence. SPF/DKIM failure (PM-13, 0.55) is a
# technical indicator with deterministic fraud correlation.
#
# NPA loss severity rankings (2023): authority impersonation > ore-ore >
# investment > romance, reflected in sequence multipliers below.
#
# Acknowledgment: these weights are priors seeded from NPA aggregate statistics,
# not fitted from labeled training data. Production calibration requires
# labeled case outcomes from Faxi's deployed pipeline.
# ────────────────────────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    # Weights are calibrated so that weight × TIER_AMP produces the right
    # score contribution WITHOUT needing override floors:
    #   T1 alone → ~0.3 (safe)
    #   T2 + T1 → ~1.5 (monitoring)
    #   Single T3 → ~3.0 (suspicious)
    #   T3 + T2 → ~4.5 (suspicious-high)
    #   Multiple T3 → ~6.0+ (high risk / scam)
    "PM-1":  0.75,  # urgency — T2, manipulation accelerant
    "PM-2":  1.40,  # secrecy demand — T3, strongest behavioral (NPA: 94% of ore-ore)
    "PM-3":  1.60,  # financial solicitation — T3, explicit money request
    "PM-4":  0.65,  # authority claim — T2, police/bank/gov impersonation
    "PM-5":  1.75,  # unusual payment — T3, gift cards/crypto (zero legit use)
    "PM-6":  1.30,  # legal threat — T3, NPA authority impersonation
    "PM-7":  1.50,  # credential solicitation — T3, passwords/card numbers
    "PM-8":  1.20,  # prize notification — T3, atobarai (advance-fee) scam
    "PM-9":  1.10,  # refund lure — T3, kankin (refund) scam
    "PM-10": 0.90,  # emotional crisis — T2, ore-ore signature (NPA: 78% open with crisis)
    "PM-11": 0.30,  # identity claim — T1, present in legit and scam equally
    "PM-12": 0.25,  # flattery density — T1, romance opener, common in normal contact
    "PM-13": 1.90,  # spf/dkim fail — T3, technical spoofing, near-deterministic
    "PM-14": 0.80,  # financial context — T2, mentions money/costs without asking
    # BV — Behavioral Velocity (cross-message patterns)
    "BV-1":  0.70,  # relationship velocity — T2, intimacy too fast
    "BV-2":  1.40,  # isolation index — T3, discouraging family contact
    "BV-3":  0.85,  # emotional arc — T2, scheduled sentiment escalation
    "BV-4":  0.60,  # credibility seeding — T2, excessive unprompted details
    "BV-5":  0.65,  # help positioning — T2, stranger as support system
    # EA — Elder Abuse (from known contacts)
    "EA-1":  1.20,  # financial control — T3, repeated money requests from trusted
    "EA-2":  1.50,  # trusted isolation — T3, cutting off from family
    "EA-3":  1.60,  # authority escalation — T3, taking over decisions
    "EA-4":  0.75,  # communication shift — T2, sudden change in pattern
}

SIGNAL_TIERS = {
    "PM-11": 1, "PM-12": 1,                          # Tier 1: informational
    "PM-1": 2, "PM-4": 2, "PM-10": 2, "PM-14": 2,     # Tier 2: moderate (PM)
    "BV-1": 2, "BV-3": 2, "BV-4": 2, "BV-5": 2, "EA-4": 2, # Tier 2: moderate (BV/EA)
    "PM-2": 3, "PM-3": 3, "PM-5": 3, "PM-6": 3,     # Tier 3: strong (PM)
    "PM-7": 3, "PM-8": 3, "PM-9": 3, "PM-13": 3,
    "BV-2": 3, "EA-1": 3, "EA-2": 3, "EA-3": 3,     # Tier 3: strong (BV/EA)
}

# Tier amplification: T3 signals compound ~2x stronger than T1
TIER_AMP = {1: 1.0, 2: 1.4, 3: 1.9}

# Score decays 8% per message — a conversation cold for 10 messages retains
# 0.92^10 = 43% of accumulated score. Fast attacks (ore-ore, 3-5 messages)
# breach thresholds before decay matters. Slow attacks (romance, weeks)
# require sustained signal presence to maintain score.
DECAY_RATE = 0.92

# T1 primer: when T1 signals (identity claim, flattery) precede T2/T3,
# the T2/T3 contribution is amplified 1.3x. Models the documented
# grooming-then-escalation pattern in ore-ore and romance scams.
T1_PRIMER_BONUS = 1.3

SCORE_CAP = 10.0

# ── Attack sequence patterns ───────────────────────────────────────────
#
# Multipliers reflect NPA loss severity rankings:
# Authority impersonation (3.2x) > ore-ore (2.8x) > investment (2.5x) > romance (2.2x)
# Authority is highest because police/court impersonation + legal threat
# has near-zero benign explanation — NPA reports it as the highest per-case
# loss category (avg. ¥9.8M per case in 2023).

ATTACK_SEQUENCES = {
    "ore_ore": {
        "canonical": ["PM-11", "PM-10", "PM-1", "PM-2", "PM-3"],
        "min_match": 3,
        "multiplier": 2.8,
    },
    "romance": {
        "canonical": ["PM-12", "PM-11", "PM-10", "PM-3", "PM-5"],
        "min_match": 3,
        "multiplier": 2.2,
    },
    "investment": {
        "canonical": ["PM-11", "PM-4", "PM-8", "PM-5"],
        "min_match": 3,
        "multiplier": 2.5,
    },
    "authority": {
        "canonical": ["PM-4", "PM-6", "PM-1", "PM-2", "PM-7"],
        "min_match": 3,
        "multiplier": 3.2,
    },
}

# Score → classification bands
SCORE_BANDS = [
    (0.00, 1.50, "safe"),
    (1.50, 3.00, "monitoring"),
    (3.00, 5.00, "suspicious"),
    (5.00, 7.50, "high_risk"),
    (7.50, SCORE_CAP + 0.01, "scam"),
]

# Score → confidence mapping (normalized to 0.0-1.0 for API compatibility)
def _score_to_confidence(score: float) -> float:
    return round(min(score / SCORE_CAP, 1.0), 3)

# Score → classification label (maps to API-compatible 4-level)
def _score_to_classification(score: float) -> str:
    for lo, hi, label in SCORE_BANDS:
        if lo <= score < hi:
            return label
    return "scam"

# API-compatible classification (4 levels)
def _to_api_classification(internal: str) -> str:
    return {
        "safe": "safe",
        "monitoring": "monitoring",
        "suspicious": "suspicious",
        "high_risk": "high_risk",
        "scam": "scam",
    }.get(internal, "safe")


def _detect_sequence_match(all_signals_in_order: list[list[str]]) -> tuple[str, float]:
    """Scan message signal history for known attack sequence matches.

    Returns (sequence_name, multiplier) or (None, 1.0).
    Uses a sliding window of 10 messages, checks if canonical
    sequence steps appear in order.
    """
    # Flatten to ordered list of unique signal appearances per message
    window = all_signals_in_order[-10:]
    best_name = None
    best_multiplier = 1.0

    for name, pattern in ATTACK_SEQUENCES.items():
        canonical = pattern["canonical"]
        min_match = pattern["min_match"]
        multiplier = pattern["multiplier"]

        # Scan: find how many canonical steps appear in order
        step = 0
        for msg_signals in window:
            if step < len(canonical) and canonical[step] in msg_signals:
                step += 1
        if step >= min_match and multiplier > best_multiplier:
            best_name = name
            best_multiplier = multiplier

    return best_name, best_multiplier


def _check_tier_overrides(signals: list[str]) -> Optional[float]:
    """Check for tier override rules that floor the score.

    With properly calibrated weights, most signals naturally reach the
    right score bands. Overrides are only for combinations that are
    categorically distinguishable from noise — no single-signal floors.
    """
    t3_in_message = [s for s in signals if SIGNAL_TIERS.get(s, 0) == 3]

    # 3+ distinct T3 signals in one message → floor 7.5 (blocked)
    # No legitimate message contains financial solicitation + secrecy +
    # credential request simultaneously.
    if len(t3_in_message) >= 3:
        return 7.5

    return None


@dataclass
class MessageRecord:
    message_index: int
    signals: list[str]
    contribution: float
    score_after: float
    sequence_match: Optional[str] = None


@dataclass
class ConversationRiskLedger:
    """Accumulates risk evidence across messages in a conversation.

    LLM detects signals. This ledger scores them deterministically.
    Classification is a derived label from the running score — never
    an LLM opinion.
    """
    conversation_id: str = ""
    running_score: float = 0.0
    message_count: int = 0
    signal_history: list = field(default_factory=list)  # list of MessageRecord dicts
    t1_primer_active: bool = False
    sequence_matches: list = field(default_factory=list)
    tier_counts: dict = field(default_factory=lambda: {"T1": 0, "T2": 0, "T3": 0})
    signal_counts: dict = field(default_factory=dict)
    family_alert_fired: bool = False
    family_alert_reason: Optional[str] = None
    overrides_applied: list = field(default_factory=list)
    highest_score_reached: float = 0.0
    # Track sustained high score for Gate A
    _consecutive_high: int = 0

    def to_dict(self) -> dict:
        """Serialize for session state / API response."""
        return {
            "conversation_id": self.conversation_id,
            "running_score": round(self.running_score, 3),
            "classification": _score_to_classification(self.running_score),
            "api_classification": _to_api_classification(_score_to_classification(self.running_score)),
            "confidence": _score_to_confidence(self.running_score),
            "message_count": self.message_count,
            "signal_history": self.signal_history,
            "t1_primer_active": self.t1_primer_active,
            "sequence_matches": self.sequence_matches,
            "tier_counts": self.tier_counts,
            "signal_counts": self.signal_counts,
            "family_alert_fired": self.family_alert_fired,
            "family_alert_reason": self.family_alert_reason,
            "overrides_applied": self.overrides_applied,
            "highest_score_reached": round(self.highest_score_reached, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationRiskLedger":
        """Restore from session state."""
        ledger = cls()
        ledger.conversation_id = d.get("conversation_id", "")
        ledger.running_score = d.get("running_score", 0.0)
        ledger.message_count = d.get("message_count", 0)
        ledger.signal_history = d.get("signal_history", [])
        ledger.t1_primer_active = d.get("t1_primer_active", False)
        ledger.sequence_matches = d.get("sequence_matches", [])
        ledger.tier_counts = d.get("tier_counts", {"T1": 0, "T2": 0, "T3": 0})
        ledger.signal_counts = d.get("signal_counts", {})
        ledger.family_alert_fired = d.get("family_alert_fired", False)
        ledger.family_alert_reason = d.get("family_alert_reason")
        ledger.overrides_applied = d.get("overrides_applied", [])
        ledger.highest_score_reached = d.get("highest_score_reached", 0.0)
        ledger._consecutive_high = d.get("_consecutive_high", 0)
        return ledger

    def update(self, signals: list[str]) -> dict:
        """Process one message's detected signals. Returns update summary.

        This is the core accumulation function:
        1. Decay existing score
        2. Compute message contribution (weight × tier amp)
        3. Apply T1 primer bonus if T1 preceded T2/T3
        4. Apply sequence multiplier if attack pattern matches
        5. Apply tier override floors
        6. Update classification from score
        7. Check family alert gates
        """
        self.message_count += 1
        score_before = self.running_score

        # 1. Decay existing score
        self.running_score *= DECAY_RATE

        # 2. Compute message contribution
        contribution = 0.0
        for s in signals:
            weight = SIGNAL_WEIGHTS.get(s, 0.0)
            tier = SIGNAL_TIERS.get(s, 1)
            contribution += weight * TIER_AMP[tier]

            # Track counts
            tier_key = f"T{tier}"
            self.tier_counts[tier_key] = self.tier_counts.get(tier_key, 0) + 1
            self.signal_counts[s] = self.signal_counts.get(s, 0) + 1

        # 3. T1 primer bonus: if T1 was seen before and this message has T2/T3
        if self.t1_primer_active and any(SIGNAL_TIERS.get(s, 0) >= 2 for s in signals):
            contribution *= T1_PRIMER_BONUS

        # 4. Sequence multiplier
        all_msg_signals = [r["signals"] for r in self.signal_history] + [signals]
        seq_name, seq_mult = _detect_sequence_match(all_msg_signals)
        if seq_name and seq_name not in self.sequence_matches:
            self.sequence_matches.append(seq_name)
        contribution *= seq_mult

        # 5. Add contribution (pre-override)
        self.running_score = min(SCORE_CAP, self.running_score + contribution)

        # 6. Tier override floors
        override_floor = _check_tier_overrides(signals)
        if override_floor is not None and self.running_score < override_floor:
            self.overrides_applied.append({
                "message_index": self.message_count - 1,
                "rule": "tier_override",
                "score_before": round(self.running_score, 3),
                "score_after": round(override_floor, 3),
            })
            self.running_score = override_floor

        # Update T1 primer flag
        if any(SIGNAL_TIERS.get(s, 0) == 1 for s in signals):
            self.t1_primer_active = True

        # Track highest score
        if self.running_score > self.highest_score_reached:
            self.highest_score_reached = self.running_score

        # Record message
        record = {
            "message_index": self.message_count - 1,
            "signals": signals,
            "contribution": round(contribution, 3),
            "score_after": round(self.running_score, 3),
            "sequence_match": seq_name,
        }
        self.signal_history.append(record)

        # 7. Family alert gates
        alert_fired_now = False
        if not self.family_alert_fired:
            alert_fired_now, reason = self._check_family_alert_gates(signals, seq_name)
            if alert_fired_now:
                self.family_alert_fired = True
                self.family_alert_reason = reason

        classification = _score_to_classification(self.running_score)

        return {
            "score_before": round(score_before, 3),
            "score_after": round(self.running_score, 3),
            "contribution": round(contribution, 3),
            "classification": classification,
            "api_classification": _to_api_classification(classification),
            "confidence": _score_to_confidence(self.running_score),
            "sequence_match": seq_name,
            "sequence_multiplier": seq_mult,
            "override_applied": override_floor is not None,
            "family_alert_fired": alert_fired_now,
            "family_alert_reason": self.family_alert_reason if alert_fired_now else None,
        }

    def _check_family_alert_gates(self, signals: list[str], seq_name: Optional[str]) -> tuple[bool, Optional[str]]:
        """Check all four family alert gates. Returns (fired, reason)."""
        # Gate A: Score sustained >= 5.0 for 2 consecutive messages
        if self.running_score >= 5.0:
            self._consecutive_high += 1
            if self._consecutive_high >= 2:
                return True, "score_sustained"
        else:
            self._consecutive_high = 0

        # Gate B: Score spike >= 7.5 (SCAM band)
        if self.running_score >= 7.5:
            return True, "score_spike"

        # Gate C: Tier override fired
        if _check_tier_overrides(signals) is not None:
            return True, "tier_override"

        # Gate D: ore-ore or authority sequence confirmed at score >= 3.0
        if seq_name in ("ore_ore", "authority") and self.running_score >= 3.0:
            return True, "sequence_match"

        # Gate E: any Tier 3 signal detected (serious concern, per user requirement)
        if any(SIGNAL_TIERS.get(s, 0) == 3 for s in signals):
            return True, "tier3_detected"

        return False, None


def classify_from_signals(signals: list[str], ledger: ConversationRiskLedger = None) -> dict:
    """Compute classification from LLM-detected signals using the risk ledger.

    If no ledger provided, creates a fresh one (single-message mode).
    Returns the update result plus the full ledger state.
    """
    if ledger is None:
        ledger = ConversationRiskLedger()

    update = ledger.update(signals)

    return {
        "update": update,
        "ledger": ledger.to_dict(),
    }


# ── Full pipeline runner ────────────────────────────────────────────────

def _contra_indicator_check(text: str, linguistic: dict) -> dict:
    """Step 4.5: Check for signs that a scam-shaped message may be legitimate.

    Scams and real family requests can look structurally identical.
    This step surfaces the distinguishing features so the LLM has
    pre-computed evidence for both sides, not just corpus matches.
    """
    # Secrecy demands — strong scam indicator when present
    secrecy_patterns = re.compile(
        r'誰にも言わないで|内緒|言わないで|秘密|他の人には|'
        r'お父さんには.*言わないで|お母さんには.*言わないで|'
        r"don't tell|keep.*secret|between us",
        re.I
    )
    has_secrecy = bool(secrecy_patterns.search(text))

    # Third-party account — scams demand transfer to someone else's account
    third_party_account = bool(re.search(
        r'この口座|相手の口座|以下の口座|振込先|'
        r"this account|their account|transfer to",
        text, re.I
    ))

    # External deadline pressure — someone ELSE demanding payment
    external_pressure = bool(re.search(
        r'相手が.*払え|相手が.*要求|警察.*呼ぶ|訴える|法的|'
        r'今すぐ.*払|期限.*まで|'
        r"they.*demand|police.*call|sue|legal",
        text, re.I
    ))

    # Mundane need — proportional, everyday request
    mundane_patterns = re.compile(
        r'タクシー|バス|電車|ランチ|昼ごはん|教科書|文房具|'
        r'携帯.*壊れ|自転車|財布.*落|忘れ|'
        r"taxi|bus|lunch|textbook|phone.*broke|wallet|forgot",
        re.I
    )
    has_mundane_context = bool(mundane_patterns.search(text))

    # Manipulation density from linguistic analysis
    manipulation = linguistic.get("manipulation", {})
    low_manipulation = manipulation.get("manipulation_density", 0) == 0

    # Count contra-indicators present
    contra_count = sum([
        not has_secrecy,        # no secrecy demand
        not third_party_account, # no third-party account
        not external_pressure,   # no external deadline
        has_mundane_context,     # mundane everyday need
        low_manipulation,        # no manipulation language
    ])

    may_be_legitimate = contra_count >= 3 and not has_secrecy and not third_party_account

    return {
        "has_secrecy_demand": has_secrecy,
        "has_third_party_account": third_party_account,
        "has_external_pressure": external_pressure,
        "has_mundane_context": has_mundane_context,
        "low_manipulation": low_manipulation,
        "contra_indicator_count": contra_count,
        "may_be_legitimate": may_be_legitimate,
        "guidance": (
            "IMPORTANT: This message has strong contra-indicators suggesting it may be "
            "a legitimate family request, not a scam. No secrecy demand, no third-party "
            "account, mundane context. Classify as SUSPICIOUS (not scam) and recommend "
            "verification by calling the sender's known number."
        ) if may_be_legitimate else None,
    }


def run_pre_classification_pipeline(
    message_text: str,
    sender_id: str,
    user_id: str,
    sender_style_baseline: dict = None,
) -> dict:
    """Run steps 1-4 of the pipeline BEFORE the LLM classifier.

    Returns a context bundle that the Classifier consumes.
    The LLM extracts entities and classifies. Pre-processing provides
    context the LLM can't compute itself (corpus matches, graph state).
    """
    from agents.tools.search_scam_corpus import search_scam_corpus
    from agents.tools.social_graph import validate_social_graph

    # Step 1: Linguistic Analysis (structural, no LLM)
    linguistic = linguistic_analysis(message_text, sender_style_baseline)

    # Step 2: Corpus Search (TF-IDF)
    corpus_result = search_scam_corpus(message_text, top_k=5)

    # Step 3: Social Graph Validation
    graph = validate_social_graph(user_id, sender_id)

    # Step 3.5: Contra-indicator analysis
    contra = _contra_indicator_check(message_text, linguistic)

    return {
        "linguistic": linguistic,
        "corpus_matches": corpus_result.get("matches", []),
        "corpus_stats": corpus_result.get("corpus_stats", {}),
        "graph_validation": graph,
        "contra_indicators": contra,
        "pipeline_version": "v2_7step",
    }
