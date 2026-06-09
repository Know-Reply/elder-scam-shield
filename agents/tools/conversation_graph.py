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

def _is_present(value: str) -> bool:
    """Check if a value is non-empty."""
    return bool(value and value.strip())


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
    if name and _is_present(name):
        facts.append({"value": name, "type": "name",
                       "category": extracted_facts.get("claimed_relationship", "person")})

    # Referenced names — other people mentioned in the message
    for ref_name in extracted_facts.get("referenced_names", []):
        if ref_name and _is_present(ref_name):
            facts.append({"value": ref_name, "type": "name", "category": "referenced"})

    # Location — only if specific (a city name, not just "here")
    location = extracted_facts.get("claimed_location")
    if location and _is_present(location):
        facts.append({"value": location, "type": "location"})

    # Institution — only if specific ("Mizuho Bank", not "bank")
    institution = extracted_facts.get("claimed_institution")
    if institution and _is_present(institution):
        facts.append({"value": institution, "type": "institution"})

    # Financial — only if a real specific amount
    fin = extracted_facts.get("financial_mention")
    if fin and isinstance(fin, dict):
        amount = str(fin.get("amount", "")).strip()
        if amount and amount.lower() not in ("", "unknown", "not specified", "none", "null", "n/a"):
            facts.append({"value": amount, "type": "amount"})

    # Life facts — significant details a scammer could exploit
    for lf in extracted_facts.get("life_facts", []):
        if lf and isinstance(lf, str) and len(lf) > 5 and len(lf) < 120:
            facts.append({"value": lf, "type": "life_fact"})


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
) -> dict:
    """Append LLM-extracted facts to the conversation fact ledger.

    The LLM handles both extraction AND matching. No string matching.
    matched_existing contains fact IDs the LLM recognized as referenced.

    Args:
        extracted_facts: dict from the fact extractor — LLM-extracted.
        direction: "inbound" (from sender) or "outbound" (from elder)
        turn_index: position in conversation (0-based)
        ledger: existing ledger from session state, or None for first message

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

    # Echo detection via LLM: matched_existing contains fact IDs from the
    # existing ledger that the LLM identified as referenced in this message.
    # No string matching. The LLM handles semantic equivalence.
    _, matched_ids = _facts_from_llm_extraction(extracted_facts)
    matched_set = set()
    for matched_fid in matched_ids:
        if matched_fid in ledger["facts"]:
            fact = ledger["facts"][matched_fid]
            if fact["first_stated_by"] == other_speaker and not fact["echo_detected"]:
                fact["echo_detected"] = True
                fact["echo_by"] = speaker
                fact["echo_at_turn"] = turn_index
                turn_entry["echoed_facts"] += 1
                turn_entry["fact_ids"].append(matched_fid)
            matched_set.add(matched_fid)

    for raw in raw_facts:
        fid = _make_fact_id(raw["type"], raw["value"])

        # Skip if the LLM matched this to an existing fact (dedup)
        if fid in matched_set:
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
    elder_state: dict | None = None,
) -> dict:
    """Update the elder's epistemic state from LLM-detected signals.

    The LLM (fact extractor) detects psychological signals from the elder's
    replies: compliance, resistance, disclosure, emotional engagement,
    instruction seeking. This function scores those signals deterministically.

    LLM detects. Math scores. No regex, no heuristics.
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

    # Friction delta weights for LLM-detected signals
    # Positive = friction increases (elder resisting = good)
    # Negative = friction decreases (elder complying = bad)
    FRICTION_DELTAS = {
        "resistance": {"none": 0.0, "mild": 0.05, "strong": 0.2},
        "compliance": {"none": 0.0, "mild": -0.1, "strong": -0.3},
        "disclosure": {"none": 0.0, "mild": -0.05, "strong": -0.15},
        "emotional_engagement": {"none": 0.0, "mild": -0.05, "strong": -0.15},
    }
    INSTRUCTION_SEEKING_DELTA = -0.2  # yielding control is a strong compliance signal

    # Apply LLM-detected signals
    es = elder_state or {}
    delta = 0.0
    for signal_name, levels in FRICTION_DELTAS.items():
        level = es.get(signal_name, "none")
        delta += levels.get(level, 0.0)

    if es.get("instruction_seeking", False):
        delta += INSTRUCTION_SEEKING_DELTA
        state["compliance_events"] += 1

    # Track events
    compliance_level = es.get("compliance", "none")
    resistance_level = es.get("resistance", "none")
    if compliance_level in ("mild", "strong"):
        state["compliance_events"] += 1
    if resistance_level in ("mild", "strong"):
        state["resistance_events"] += 1

    # Apply delta to friction score (clamped 0.0 - 1.0)
    state["friction_score"] = max(0.0, min(1.0, state["friction_score"] + delta))
    state["friction_history"].append(round(state["friction_score"], 2))

    # Update trust stage based on friction — even 25-point bands
    f = state["friction_score"]
    if f >= 0.7:
        new_stage = "skeptical"
    elif f >= 0.45:
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
    sender_facts = [f for f in facts.values() if f.get("sender_turns") or f["first_stated_by"] == "sender"]
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


# ── Persistence: consolidate for ADK session state scoping ────────────

IDENTITY_TYPES = {"name", "location", "institution", "amount", "relationship"}


def consolidate_for_persistence(ledger: dict, epistemic: dict) -> tuple[dict, dict]:
    """Consolidate the fact ledger into two persistent structures.

    Identity facts: names, locations, institutions, amounts — small, stable,
    used for matching across sessions. Stored at user: scope.

    Vulnerability summary: consolidated profile of the elder's revealed
    vulnerabilities — not a growing list, but a current-state summary.
    Stored at user: scope.

    Per-conversation details stay in the session-level fact_ledger.
    """
    facts = ledger.get("facts", {})

    # Identity facts — persist across sessions for matching
    identity = {}
    for fid, fact in facts.items():
        if fact.get("type") in IDENTITY_TYPES:
            identity[fid] = {
                "value": fact["value"],
                "type": fact["type"],
                "first_stated_by": fact["first_stated_by"],
                "first_turn": fact["first_turn"],
                "echo_detected": fact.get("echo_detected", False),
                "echo_by": fact.get("echo_by"),
            }

    # Vulnerability summary — consolidated from life_facts
    vulnerabilities = []
    for fid, fact in facts.items():
        if fact.get("type") == "life_fact" and fact["first_stated_by"] == "elder":
            vulnerabilities.append(fact["value"])

    summary = {
        "vulnerabilities": vulnerabilities,
        "trust_stage": epistemic.get("trust_stage", "skeptical"),
        "friction_score": epistemic.get("friction_score", 0.8),
        "friction_trajectory": epistemic.get("friction_trajectory", "stable_high"),
        "total_elder_facts_exposed": sum(
            1 for f in facts.values() if f["first_stated_by"] == "elder"
        ),
        "total_echoed_facts": sum(
            1 for f in facts.values() if f.get("echo_detected")
        ),
    }

    return identity, summary


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
        )
    else:
        ledger = session_state.get("fact_ledger") or {"facts": {}, "turns": [], "contradiction_log": []}

    # Layer 2: Update epistemic state (outbound only — elder's replies)
    # Pass LLM-detected elder state signals if available
    elder_state = None
    if extracted_facts and isinstance(extracted_facts, dict):
        elder_state = extracted_facts.get("elder_state")
    epistemic = update_epistemic_state(
        text, direction, turn_index,
        state=session_state.get("epistemic_state"),
        elder_state=elder_state,
    )

    # Layer 3: Build knowledge graph from accumulated evidence
    graph = build_knowledge_graph(ledger, epistemic)

    # Consolidate into persistent layers (ADK session state scoping)
    identity_facts, vulnerability_summary = consolidate_for_persistence(ledger, epistemic)

    return {
        "fact_ledger": ledger,
        "epistemic_state": epistemic,
        "knowledge_graph": graph,
        "graph_signals": graph.get("graph_signals", {}),
        # Persistent state — use user: prefix in ADK session
        "user:identity_facts": identity_facts,
        "user:vulnerability_summary": vulnerability_summary,
    }
