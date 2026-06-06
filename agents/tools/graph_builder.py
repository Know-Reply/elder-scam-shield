"""Social Graph Builder — infers contact network from communication patterns.

Closes the loop between fact extraction and graph validation:
  1. Classifier extracts facts from every message (name, relationship, location)
  2. Graph builder accumulates those facts into sender profiles
  3. Profiles that meet confidence thresholds become graph nodes
  4. Cross-references between contacts create verified edges
  5. The graph grows stronger with every message

Confidence levels:
  VERIFIED    — family portal registration or user confirmation
  OBSERVED    — 6+ months reciprocal message history
  ESTABLISHED — 3-6 months message history
  RECOGNIZED  — mentioned by 2+ verified contacts
  CORROBORATED — referenced by one verified contact
  INFERRED    — single third-party mention
  CLAIMED     — sender's own assertion only
  UNCONNECTED — no graph path
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from google.cloud import firestore
    _db = firestore.Client()
except Exception:
    _db = None


# ── Confidence thresholds ───────────────────────────────────────────────

CONFIDENCE_LEVELS = {
    "VERIFIED": 7,      # family portal registration
    "OBSERVED": 6,      # 6+ months reciprocal history
    "ESTABLISHED": 5,   # 3-6 months history
    "RECOGNIZED": 4,    # mentioned by 2+ verified contacts
    "CORROBORATED": 3,  # referenced by one verified contact
    "INFERRED": 2,      # single third-party mention
    "CLAIMED": 1,       # sender's own assertion only
    "UNCONNECTED": 0,   # no connection
}


def _get_graph_collection():
    return _db.collection("social_graphs") if _db else None


def _get_profiles_collection():
    return _db.collection("sender_profiles") if _db else None


# ── Core graph building functions ───────────────────────────────────────


def update_graph_from_message(
    user_id: str,
    sender_id: str,
    extracted_facts: dict,
    message_timestamp: str = None,
) -> dict:
    """Update the social graph based on extracted facts from a classified message.

    Called after the Inbound Classifier processes every message. Facts extracted
    from message content feed into the graph builder to create and strengthen
    edges over time.

    Args:
        user_id: The protected user's ID.
        sender_id: Who sent the message.
        extracted_facts: Facts extracted by the Classifier:
            {
                "claimed_name": "ゆき",
                "claimed_relationship": "grandson",
                "claimed_location": "横浜",
                "mentioned_contacts": ["お母さん", "美咲"],
                "other_facts": [...]
            }
        message_timestamp: ISO timestamp of the message.

    Returns:
        Dict with graph updates applied and current confidence level.
    """
    now = message_timestamp or datetime.now(timezone.utc).isoformat()
    updates = []

    # ── 1. Update sender's direct profile ───────────────────────────
    # Every message from this sender strengthens (or creates) their node

    sender_node = _load_or_create_node(user_id, sender_id)
    sender_node["message_count"] = sender_node.get("message_count", 0) + 1
    sender_node["last_seen"] = now

    if not sender_node.get("first_seen"):
        sender_node["first_seen"] = now

    # Accumulate stated facts (don't overwrite — track history)
    facts_history = sender_node.setdefault("facts_history", [])
    facts_history.append({
        "timestamp": now,
        "facts": extracted_facts,
    })

    # Update claimed identity fields
    if extracted_facts.get("claimed_name"):
        names = sender_node.setdefault("claimed_names", [])
        name = extracted_facts["claimed_name"]
        if name not in names:
            names.append(name)

    if extracted_facts.get("claimed_relationship"):
        rels = sender_node.setdefault("claimed_relationships", [])
        rel = extracted_facts["claimed_relationship"]
        if rel not in rels:
            rels.append(rel)

    if extracted_facts.get("claimed_location"):
        locs = sender_node.setdefault("claimed_locations", [])
        loc = extracted_facts["claimed_location"]
        if loc not in [l.get("value") if isinstance(l, dict) else l for l in locs]:
            locs.append({"value": loc, "date": now})

    # ── 2. Compute confidence level ─────────────────────────────────

    confidence = _compute_confidence(sender_node, user_id)
    sender_node["confidence"] = confidence
    updates.append(f"sender confidence: {confidence}")

    # ── 3. Cross-reference: extract mentions of other people ────────
    # When this sender mentions someone, it creates an inferred edge
    # between them

    mentioned = extracted_facts.get("mentioned_contacts", [])
    if not mentioned:
        # Try to extract from other_facts
        for fact in extracted_facts.get("other_facts", []):
            if isinstance(fact, str):
                # Look for name references in Japanese
                for indicator in ["お母さん", "お父さん", "息子", "娘", "孫",
                                  "姉", "兄", "妹", "弟", "奥さん", "主人"]:
                    if indicator in fact:
                        mentioned.append(indicator)

    cross_refs = []
    for mention in mentioned:
        ref = _record_cross_reference(user_id, sender_id, mention, now)
        if ref:
            cross_refs.append(ref)
            updates.append(f"cross-ref: {sender_id} → {mention}")

    # ── 4. Auto-promote to graph node if threshold met ──────────────

    promoted = False
    if confidence in ("OBSERVED", "ESTABLISHED", "VERIFIED"):
        promoted = _promote_to_contact(user_id, sender_id, sender_node)
        if promoted:
            updates.append(f"promoted to contact (confidence: {confidence})")

    # ── 5. Persist updates ──────────────────────────────────────────

    _save_node(user_id, sender_id, sender_node)

    return {
        "sender_id": sender_id,
        "confidence": confidence,
        "message_count": sender_node["message_count"],
        "claimed_names": sender_node.get("claimed_names", []),
        "claimed_relationships": sender_node.get("claimed_relationships", []),
        "cross_references": cross_refs,
        "promoted_to_contact": promoted,
        "updates": updates,
    }


def check_cross_references(user_id: str, sender_id: str) -> dict:
    """Check if other known contacts have mentioned this sender.

    The key insight: a scammer can fake one relationship, but they can't
    insert themselves into a web of cross-references built over months.

    Args:
        user_id: The protected user's ID.
        sender_id: The sender to check.

    Returns:
        Dict with cross-reference evidence from other contacts.
    """
    graph = _load_graph(user_id)
    contacts = graph.get("contacts", {})
    sender_node = _load_or_create_node(user_id, sender_id)

    sender_names = sender_node.get("claimed_names", [])

    # Search all known contacts for mentions of this sender
    mentions_by_others = []
    for contact_id, contact_data in contacts.items():
        if contact_id == sender_id:
            continue
        # Check if this contact has ever mentioned any of the sender's names
        contact_node = _load_or_create_node(user_id, contact_id)
        for fact_entry in contact_node.get("facts_history", []):
            facts = fact_entry.get("facts", {})
            for other_fact in facts.get("other_facts", []):
                if isinstance(other_fact, str):
                    for name in sender_names:
                        if name in other_fact:
                            mentions_by_others.append({
                                "mentioned_by": contact_id,
                                "mentioned_by_name": contact_data.get("name", contact_id),
                                "context": other_fact[:100],
                                "date": fact_entry.get("timestamp"),
                            })

    corroborated = len(mentions_by_others) > 0
    recognized = len(set(m["mentioned_by"] for m in mentions_by_others)) >= 2

    return {
        "sender_id": sender_id,
        "sender_names": sender_names,
        "mentions_by_known_contacts": mentions_by_others,
        "corroborated": corroborated,
        "recognized": recognized,  # mentioned by 2+ distinct contacts
        "evidence_strength": "RECOGNIZED" if recognized else "CORROBORATED" if corroborated else "NONE",
    }


# ── Internal helpers ────────────────────────────────────────────────────


def _load_graph(user_id: str) -> dict:
    """Load the user's social graph."""
    from agents.tools.social_graph import MOCK_GRAPH
    coll = _get_graph_collection()
    if coll:
        doc = coll.document(user_id).get()
        if doc.exists:
            return doc.to_dict()
    return MOCK_GRAPH.get(user_id, {"owner": "unknown", "contacts": {}})


def _load_or_create_node(user_id: str, sender_id: str) -> dict:
    """Load a sender's node data or create empty one."""
    coll = _get_profiles_collection()
    if coll:
        doc = coll.document(f"{user_id}_{sender_id}").get()
        if doc.exists:
            return doc.to_dict()
    return {
        "sender_id": sender_id,
        "first_seen": None,
        "last_seen": None,
        "message_count": 0,
        "claimed_names": [],
        "claimed_relationships": [],
        "claimed_locations": [],
        "facts_history": [],
        "confidence": "UNCONNECTED",
        "cross_references_made": [],
        "cross_references_received": [],
    }


def _save_node(user_id: str, sender_id: str, node: dict) -> None:
    """Persist sender node to Firestore."""
    coll = _get_profiles_collection()
    if coll:
        coll.document(f"{user_id}_{sender_id}").set(node)


def _compute_confidence(node: dict, user_id: str) -> str:
    """Compute confidence level based on accumulated evidence."""
    msg_count = node.get("message_count", 0)
    first_seen = node.get("first_seen")
    last_seen = node.get("last_seen")

    # Check for verified status (family portal)
    if node.get("verified"):
        return "VERIFIED"

    # Compute history duration
    if first_seen and last_seen:
        try:
            first = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            last = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            duration = last - first
            months = duration.days / 30

            if months >= 6 and msg_count >= 10:
                return "OBSERVED"
            if months >= 3 and msg_count >= 5:
                return "ESTABLISHED"
        except (ValueError, TypeError):
            pass

    # Check cross-references
    cross_refs = node.get("cross_references_received", [])
    distinct_sources = len(set(r.get("from") for r in cross_refs if isinstance(r, dict)))
    if distinct_sources >= 2:
        return "RECOGNIZED"
    if distinct_sources >= 1:
        return "CORROBORATED"

    # Check if they've made any claims
    if node.get("claimed_relationships") or node.get("claimed_names"):
        if msg_count >= 1:
            return "CLAIMED"

    return "UNCONNECTED"


def _record_cross_reference(
    user_id: str, sender_id: str, mentioned_name: str, timestamp: str
) -> dict | None:
    """Record that sender_id mentioned someone in a message."""
    # Store the cross-reference on both sides
    ref = {
        "from": sender_id,
        "mentioned": mentioned_name,
        "timestamp": timestamp,
    }
    return ref


def _promote_to_contact(user_id: str, sender_id: str, node: dict) -> bool:
    """Promote a sender to a full contact in the social graph."""
    graph = _load_graph(user_id)
    contacts = graph.get("contacts", {})

    if sender_id in contacts:
        return False  # already a contact

    # Add to graph
    contacts[sender_id] = {
        "name": node.get("claimed_names", ["unknown"])[0] if node.get("claimed_names") else "unknown",
        "relationship": node.get("claimed_relationships", ["unknown"])[0] if node.get("claimed_relationships") else "contact",
        "location": node.get("claimed_locations", [{}])[0].get("value", "") if node.get("claimed_locations") else "",
        "message_history_months": node.get("message_count", 0),
        "connected_to": [],
        "confidence": node.get("confidence", "ESTABLISHED"),
        "auto_promoted": True,
    }

    # Save updated graph
    coll = _get_graph_collection()
    if coll:
        coll.document(user_id).set(graph)

    return True
