"""Conversation Knowledge Graph — tracks information provenance in adversarial dialogue.

Three layers compose into a scam detection signal:

  fact-ledger (Signal)         — WHO said WHAT first. Append-only per turn.
  epistemic-state (Interpret)  — Is the elder resisting or complying? Friction score.
  knowledge-graph (Interpret)  — Information asymmetry: is the sender echoing or knowing?

The key insight: if the elder says "Kenji, is that you?" and the sender
then uses "Kenji" — the sender didn't know the name. The elder gave it
to them. Every fact in the conversation has provenance: independent
(the sender knew it) vs echoed (the sender learned it from the elder).

All state lives in ADK session state as Python dicts. No external database.
Updated per-message. Pure Python — no LLM call needed.
"""

from __future__ import annotations


# ── Fact Ledger (Signal layer) ────────────────────────────────────────

_GENERIC_WORDS = {
    "bank", "hospital", "police", "clinic", "school", "company",
    "grandfather", "grandmother", "grandma", "grandpa", "mother", "father",
    "mom", "dad", "son", "daughter", "friend", "brother", "sister",
    "uncle", "aunt", "nephew", "niece", "wife", "husband",
    "unknown", "not specified", "none", "n/a", "",
    "おばあちゃん", "おじいちゃん", "お母さん", "お父さん",
    "銀行", "病院", "警察", "学校",
}


def _is_specific(value: str) -> bool:
    """Check if a value is specific enough to be a standalone fact.
    'Mizuho Bank' is specific. 'bank' alone is not."""
    if not value:
        return False
    return value.lower().strip() not in _GENERIC_WORDS and len(value) > 1


def _facts_from_llm_extraction(extracted_facts: dict) -> tuple[list[dict], list[str]]:
    """Convert LLM-extracted facts into normalized entries + matched IDs.

    Only creates standalone fact entries from structured fields when they're
    specific (proper names, specific institutions). Generic words like "bank"
    or "grandfather" are not facts — the life_facts capture the context.

    Returns:
        (facts, matched_ids) — facts to add, and IDs of existing facts
        that the LLM identified as semantic matches.
    """
    facts = []
    if not extracted_facts:
        return facts, []

    # Primary name — only if specific (a proper name, not "grandfather")
    name = extracted_facts.get("claimed_name")
    if name and _is_specific(name):
        facts.append({"value": name, "type": "name",
                       "category": extracted_facts.get("claimed_relationship", "person")})

    # Referenced names — other people mentioned in the message
    for ref_name in extracted_facts.get("referenced_names", []):
        if ref_name and _is_specific(ref_name):
            facts.append({"value": ref_name, "type": "name", "category": "referenced"})

    # Location — only if specific (a city name, not just "here")
    location = extracted_facts.get("claimed_location")
    if location and _is_specific(location):
        facts.append({"value": location, "type": "location"})

    # Institution — only if specific ("Mizuho Bank", not "bank")
    institution = extracted_facts.get("claimed_institution")
    if institution and _is_specific(institution):
        facts.append({"value": institution, "type": "institution"})

    # Financial — only if a real amount, not "unknown"
    fin = extracted_facts.get("financial_mention")
    if fin and isinstance(fin, dict):
        amount = fin.get("amount")
        if amount and _is_specific(str(amount)):
            facts.append({"value": str(amount), "type": "amount"})

    # Life facts — significant details a scammer could exploit
    for lf in extracted_facts.get("life_facts", []):
        if lf and isinstance(lf, str) and len(lf) > 5 and len(lf) < 120:
            facts.append({"value": lf, "type": "life_fact"})

    # Backward compat: also check other_facts
    for other in extracted_facts.get("other_facts", []):
        if other and isinstance(other, str) and len(other) > 5 and len(other) < 120:
            facts.append({"value": other, "type": "life_fact"})

    # Matched existing fact IDs (LLM semantic matching)
    matched = extracted_facts.get("matched_existing", [])

    return facts, matched


def _make_fact_id(fact_type: str, value: str) -> str:
    """Stable ID for deduplication across turns."""
    return f"{fact_type}:{value.lower().strip()}"


def update_fact_ledger(
    extracted_facts: dict,
    direction: str,
    turn_index: int,
    ledger: dict | None = None,
    message_text: str = "",
) -> dict:
    """Append LLM-extracted facts to the conversation fact ledger.

    The LLM extracts facts. Then deterministic post-processing checks
    if any existing fact values appear in the message text — catching
    echoes the LLM missed. LLM does extraction, infrastructure does matching.

    Args:
        extracted_facts: dict from the fact extractor — LLM-extracted.
        direction: "inbound" (from sender) or "outbound" (from elder)
        turn_index: position in conversation (0-based)
        ledger: existing ledger from session state, or None for first message
        message_text: raw message text for deterministic echo detection

    Returns updated ledger dict.
    """
    if ledger is None:
        ledger = {"facts": {}, "turns": [], "contradiction_log": []}

    raw_facts, _ = _facts_from_llm_extraction(extracted_facts)
    speaker = "elder" if direction == "outbound" else "sender"
    other_speaker = "sender" if speaker == "elder" else "elder"

    turn_entry = {
        "turn_index": turn_index,
        "direction": direction,
        "speaker": speaker,
        "fact_ids": [],
        "new_facts": 0,
        "echoed_facts": 0,
    }

    # Deterministic echo detection: check if any existing facts from the
    # OTHER party appear in this message text. This catches echoes the LLM
    # missed — we know exactly what to look for (the existing ledger).
    text_lower = message_text.lower() if message_text else ""
    already_echoed = set()
    if text_lower:
        for fid, fact in ledger["facts"].items():
            if fact["first_stated_by"] == other_speaker and not fact["echo_detected"]:
                # Check if this fact's value (or any significant word from it)
                # appears in the message. "Mizuho Bank" matches "Mizuho".
                fact_val = fact["value"].lower()
                match = False
                if len(fact_val) >= 3 and fact_val in text_lower:
                    match = True
                else:
                    # Check individual words (4+ chars) from multi-word facts
                    for word in fact_val.split():
                        if len(word) >= 4 and word in text_lower:
                            match = True
                            break
                if match:
                    fact["echo_detected"] = True
                    fact["echo_by"] = speaker
                    fact["echo_at_turn"] = turn_index
                    turn_entry["echoed_facts"] += 1
                    turn_entry["fact_ids"].append(fid)
                    already_echoed.add(fid)

    for raw in raw_facts:
        fid = _make_fact_id(raw["type"], raw["value"])

        # Skip if this fact was already detected as an echo of an existing fact
        # (e.g. "Mizuho" extracted as new, but "Mizuho Bank" already echoed above)
        skip = False
        for echoed_fid in already_echoed:
            existing_val = ledger["facts"][echoed_fid]["value"].lower()
            new_val = raw["value"].lower()
            if new_val in existing_val or existing_val in new_val:
                skip = True
                break
        if skip:
            continue

        turn_entry["fact_ids"].append(fid)

        if fid not in ledger["facts"]:
            # New fact — first introduction
            ledger["facts"][fid] = {
                "fact_id": fid,
                "value": raw["value"],
                "type": raw["type"],
                "category": raw.get("category"),
                "first_stated_by": speaker,
                "first_turn": turn_index,
                "elder_turns": [turn_index] if speaker == "elder" else [],
                "sender_turns": [turn_index] if speaker == "sender" else [],
                "echo_detected": False,
                "echo_by": None,
                "echo_at_turn": None,
            }
            turn_entry["new_facts"] += 1
        else:
            # Existing fact — check for echo
            fact = ledger["facts"][fid]
            if speaker == "elder":
                if turn_index not in fact["elder_turns"]:
                    fact["elder_turns"].append(turn_index)
            else:
                if turn_index not in fact["sender_turns"]:
                    fact["sender_turns"].append(turn_index)

            # Echo: the other party introduced it first
            if fact["first_stated_by"] == other_speaker and not fact["echo_detected"]:
                fact["echo_detected"] = True
                fact["echo_by"] = speaker
                fact["echo_at_turn"] = turn_index
                turn_entry["echoed_facts"] += 1

    # Check for contradictions within same speaker
    # Simple: same type, different value, same speaker
    facts_by_speaker_type: dict[str, list] = {}
    for fid, fact in ledger["facts"].items():
        key = f"{fact['first_stated_by']}:{fact['type']}"
        facts_by_speaker_type.setdefault(key, []).append(fact)

    for key, group in facts_by_speaker_type.items():
        if len(group) > 1 and group[0]["type"] == "location":
            # Multiple locations from same speaker could be a contradiction
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    pair_key = f"{group[i]['fact_id']}|{group[j]['fact_id']}"
                    if not any(c["pair_key"] == pair_key for c in ledger["contradiction_log"]):
                        ledger["contradiction_log"].append({
                            "pair_key": pair_key,
                            "fact_a": group[i]["fact_id"],
                            "fact_b": group[j]["fact_id"],
                            "speaker": group[0]["first_stated_by"],
                            "type": "location_shift",
                            "detected_at_turn": turn_index,
                        })

    ledger["turns"].append(turn_entry)
    return ledger


# ── Epistemic State (Interpretation layer) ────────────────────────────

TRUST_STAGES = ["skeptical", "engaged", "trusting", "compliant"]


def update_epistemic_state(
    text: str,
    direction: str,
    turn_index: int,
    state: dict | None = None,
) -> dict:
    """Update the elder's epistemic state based on their reply.

    Only updates on outbound messages (elder's replies).
    Inbound messages don't change the elder's state directly.
    """
    if state is None:
        state = {
            "trust_stage": "skeptical",
            "trust_stage_history": [{"stage": "skeptical", "turn": 0}],
            "friction_score": 0.8,
            "friction_history": [0.8],
            "friction_trajectory": "stable_high",
            "resistance_events": 0,
            "compliance_events": 0,
        }

    # Only elder's replies change epistemic state
    if direction != "outbound":
        return state

    # Language-agnostic structural signals
    question_count = text.count("?") + text.count("？")
    char_count = len(text)

    # Questions = resistance (good). Short agreeing replies = compliance (bad).
    if question_count >= 2:
        # Asking questions = maintaining friction
        state["resistance_events"] += 1
        state["friction_score"] = min(1.0, state["friction_score"] + 0.1)
    elif question_count == 1 and char_count > 50:
        # One question in a longer reply = engaged but cautious
        state["friction_score"] = max(0.0, state["friction_score"] - 0.05)
    elif question_count == 1 and char_count <= 50:
        # One question in a short reply = slightly declining but still engaged
        state["friction_score"] = max(0.0, state["friction_score"] - 0.1)
    elif question_count == 0 and char_count < 50:
        # Very short reply, no questions = strong compliance signal
        state["compliance_events"] += 1
        state["friction_score"] = max(0.0, state["friction_score"] - 0.3)
    elif question_count == 0 and char_count < 100:
        # Short reply, no questions = likely compliance
        state["compliance_events"] += 1
        state["friction_score"] = max(0.0, state["friction_score"] - 0.2)
    elif question_count == 0 and char_count >= 100:
        # Long reply, no questions = engaged and trusting
        state["compliance_events"] += 1
        state["friction_score"] = max(0.0, state["friction_score"] - 0.1)

    state["friction_history"].append(round(state["friction_score"], 2))

    # Update trust stage based on friction
    f = state["friction_score"]
    if f >= 0.6:
        new_stage = "skeptical"
    elif f >= 0.4:
        new_stage = "engaged"
    elif f >= 0.2:
        new_stage = "trusting"
    else:
        new_stage = "compliant"

    if new_stage != state["trust_stage"]:
        state["trust_stage"] = new_stage
        state["trust_stage_history"].append({"stage": new_stage, "turn": turn_index})

    # Compute friction trajectory
    history = state["friction_history"]
    if len(history) >= 3:
        recent = history[-3:]
        if all(r <= 0.2 for r in recent):
            state["friction_trajectory"] = "collapsed"
        elif recent[-1] < recent[0] - 0.1:
            state["friction_trajectory"] = "declining"
        elif abs(recent[-1] - recent[0]) > 0.2:
            state["friction_trajectory"] = "volatile"
        else:
            state["friction_trajectory"] = "stable_high" if recent[-1] >= 0.5 else "stable_low"

    return state


# ── Conversation Knowledge Graph (Interpretation layer) ───────────────

def build_knowledge_graph(
    ledger: dict,
    epistemic: dict,
) -> dict:
    """Assemble the conversation knowledge graph from ledger + epistemic state.

    This is the signal surface that risk-assessment reads. Computed from
    the accumulated evidence, not from any single message.
    """
    facts = ledger.get("facts", {})

    # Information asymmetry analysis
    sender_facts = [f for f in facts.values() if "sender" in (f.get("sender_turns") and "sender") or f["first_stated_by"] == "sender"]
    elder_facts = [f for f in facts.values() if f["first_stated_by"] == "elder"]

    # Echo analysis: facts the sender used AFTER the elder introduced them
    sender_echoed = [f for f in facts.values() if f.get("echo_by") == "sender"]
    elder_echoed = [f for f in facts.values() if f.get("echo_by") == "elder"]

    # Independent facts: sender introduced these without elder mentioning first
    sender_independent = [
        f for f in facts.values()
        if f["first_stated_by"] == "sender" and not f.get("echo_detected")
    ]
    sender_echo_only = [
        f for f in facts.values()
        if f["first_stated_by"] == "elder" and f.get("echo_by") == "sender"
    ]

    total_sender_used = len(sender_independent) + len(sender_echo_only)
    echo_ratio = round(len(sender_echo_only) / max(total_sender_used, 1), 2)

    # Asymmetry: positive = sender knows more (suspicious), negative = sender echoing
    asymmetry = len(sender_independent) - len(sender_echo_only)

    if total_sender_used == 0:
        asymmetry_verdict = "insufficient_data"
    elif echo_ratio >= 0.6:
        asymmetry_verdict = "sender_echoing"
    elif len(sender_independent) > len(sender_echo_only) * 2:
        asymmetry_verdict = "sender_knows_more"
    else:
        asymmetry_verdict = "balanced"

    # Identity claim analysis
    identity_claims = []
    name_facts = {fid: f for fid, f in facts.items() if f["type"] == "name"}
    for fid, f in name_facts.items():
        if f["first_stated_by"] == "sender":
            credibility = "independent"
        elif f.get("echo_by") == "sender":
            credibility = "echo_grounded"
        else:
            credibility = "elder_only"
        identity_claims.append({
            "fact_id": fid,
            "name": f["value"],
            "credibility": credibility,
            "first_stated_by": f["first_stated_by"],
            "echo_detected": f.get("echo_detected", False),
        })

    # Composite signals for risk-assessment
    friction = epistemic.get("friction_score", 0.8)
    trajectory = epistemic.get("friction_trajectory", "stable_high")

    graph_signals = {
        "echo_ratio": echo_ratio,
        "echo_grounded_identity": any(ic["credibility"] == "echo_grounded" for ic in identity_claims),
        "friction_collapsed": trajectory == "collapsed",
        "friction_score": friction,
        "friction_trajectory": trajectory,
        "trust_stage": epistemic.get("trust_stage", "skeptical"),
        "elder_facts_exposed": len(elder_facts),
        "sender_independent_facts": len(sender_independent),
        "sender_echoed_facts": len(sender_echo_only),
        "contradictions": len(ledger.get("contradiction_log", [])),
        "turns_analyzed": len(ledger.get("turns", [])),
    }

    return {
        "information_asymmetry": {
            "sender_independent_facts": [f["fact_id"] for f in sender_independent],
            "sender_echo_facts": [f["fact_id"] for f in sender_echo_only],
            "echo_ratio": echo_ratio,
            "asymmetry_score": asymmetry,
            "asymmetry_verdict": asymmetry_verdict,
        },
        "identity_claim_analysis": identity_claims,
        "epistemic_summary": {
            "trust_stage": epistemic.get("trust_stage", "skeptical"),
            "friction_score": friction,
            "friction_trajectory": trajectory,
            "compliance_events": epistemic.get("compliance_events", 0),
            "resistance_events": epistemic.get("resistance_events", 0),
        },
        "contradictions": ledger.get("contradiction_log", []),
        "graph_signals": graph_signals,
    }


# ── Public API: process one turn ──────────────────────────────────────

def process_conversation_turn(
    text: str,
    direction: str,
    turn_index: int,
    session_state: dict,
    extracted_facts: dict | None = None,
) -> dict:
    """Process a single conversation turn and update all three graph layers.

    Call this on every message — both inbound (sender) and outbound (elder).

    Args:
        text: message content (used for epistemic state — structural analysis)
        direction: "inbound" or "outbound"
        turn_index: position in conversation
        session_state: dict with fact_ledger, epistemic_state, knowledge_graph keys
        extracted_facts: LLM-extracted facts dict (from ClassificationResult or
            InterceptDecision). If None, fact ledger is not updated.

    Returns dict with updated state for all three layers + graph_signals for risk assessment.
    """
    # Layer 1: Update fact ledger from LLM-extracted facts (both directions)
    if extracted_facts:
        ledger = update_fact_ledger(
            extracted_facts, direction, turn_index,
            ledger=session_state.get("fact_ledger"),
            message_text=text,
        )
    else:
        ledger = session_state.get("fact_ledger") or {"facts": {}, "turns": [], "contradiction_log": []}

    # Layer 2: Update epistemic state (outbound only — elder's replies)
    epistemic = update_epistemic_state(
        text, direction, turn_index,
        state=session_state.get("epistemic_state"),
    )

    # Layer 3: Build knowledge graph from accumulated evidence
    graph = build_knowledge_graph(ledger, epistemic)

    return {
        "fact_ledger": ledger,
        "epistemic_state": epistemic,
        "knowledge_graph": graph,
        "graph_signals": graph.get("graph_signals", {}),
    }
