"""Social Graph Validation — contact network distance and imposter detection.

Checks whether a sender has ANY connection to the user's known contact graph.
A sender who claims a relationship but has no graph path gets an automatic
risk boost (imposter signal). Used by the Behavioral Analyzer as a
pre-screening step before longitudinal analysis.

Round 4 hardening: social graph validation layer.
"""

from __future__ import annotations

from agents.db import db as _db

# ── Mock graph for local dev ──────────────────────────────────────────

MOCK_GRAPH: dict[str, dict] = {
    "user_tanaka_001": {
        "owner": "山田花子",
        "contacts": {
            "contact_yuki_grandson": {
                "name": "ゆき",
                "relationship": "grandson",
                "location": "横浜",
                "message_history_months": 36,
                "connected_to": ["contact_misaki_daughter"],
            },
            "contact_misaki_daughter": {
                "name": "美咲",
                "relationship": "daughter",
                "location": "東京",
                "message_history_months": 60,
                "connected_to": ["contact_yuki_grandson"],
            },
            "contact_tanaka_taro": {
                "name": "田中太郎",
                "relationship": "friend",
                "location": "さいたま",
                "message_history_months": 120,
                "connected_to": [],
            },
            "contact_meguro_clinic": {
                "name": "目黒内科クリニック",
                "relationship": "clinic",
                "location": "目黒",
                "message_history_months": 24,
                "connected_to": [],
            },
        },
    }
}

# ── Firestore handle (shared client) ──────────────────────────────────

_GRAPHS = _db.collection("social_graphs") if _db else None


def _load_graph(user_id: str) -> dict:
    """Load the user's social graph from Firestore or fall back to mock."""
    if _GRAPHS is not None:
        doc = _GRAPHS.document(user_id).get()
        if doc.exists:
            return doc.to_dict()
    return MOCK_GRAPH.get(user_id, {"owner": "unknown", "contacts": {}})


def _compute_graph_distance(
    contacts: dict, sender_id: str
) -> tuple[int, str | None]:
    """Return (distance, connected_via).

    0  = sender IS a direct contact
    1  = sender is connected through one known contact (friend-of-friend)
    -1 = no connection found
    """
    # Direct contact?
    if sender_id in contacts:
        return 0, None

    # Friend-of-friend?
    for contact_id, contact_data in contacts.items():
        if sender_id in contact_data.get("connected_to", []):
            return 1, contact_id

    return -1, None


def _risk_modifier(
    distance: int,
    message_history_months: int | None,
    claimed_relationship: str | None,
) -> float:
    """Compute graph-based risk modifier.

    Returns:
        -0.2  known contact, long history (>= 12 months)
        -0.1  known contact, short history (< 12 months)
         0.0  friend-of-friend (neutral)
        +0.1  unknown sender, no relationship claim
        +0.3  unknown sender claims relationship but no graph connection (imposter)
    """
    if distance == 0:
        if message_history_months is not None and message_history_months >= 12:
            return -0.2
        return -0.1
    if distance == 1:
        return 0.0
    # distance == -1: no connection
    if claimed_relationship:
        return 0.3  # imposter signal
    return 0.1


# ── Public API ─────────────────────────────────────────────────────────


def validate_social_graph(
    user_id: str,
    sender_id: str,
    claimed_relationship: str | None = None,
) -> dict:
    """Check if sender connects to any node in the user's contact graph.

    Args:
        user_id: The protected user's ID.
        sender_id: The sender to validate.
        claimed_relationship: Optional relationship the sender claims
            (e.g. "grandson", "friend's son").

    Returns:
        {
            "sender_id": str,
            "is_known_contact": bool,
            "graph_distance": int,    # 0=direct, 1=friend-of-friend, -1=none
            "connected_via": str | None,
            "relationship_claimed": str | None,
            "relationship_verified": bool,
            "graph_risk_modifier": float,
            "network_size": int,
        }
    """
    graph = _load_graph(user_id)
    contacts = graph.get("contacts", {})

    distance, connected_via = _compute_graph_distance(contacts, sender_id)

    is_known = distance == 0
    message_history = None
    relationship_verified = False

    if is_known:
        contact_data = contacts[sender_id]
        message_history = contact_data.get("message_history_months")
        if claimed_relationship:
            relationship_verified = (
                contact_data.get("relationship", "").lower()
                == claimed_relationship.lower()
            )
        else:
            # No claim made, but they ARE a known contact — not suspicious
            relationship_verified = True

    modifier = _risk_modifier(distance, message_history, claimed_relationship)

    return {
        "sender_id": sender_id,
        "is_known_contact": is_known,
        "graph_distance": distance,
        "connected_via": connected_via,
        "relationship_claimed": claimed_relationship,
        "relationship_verified": relationship_verified,
        "graph_risk_modifier": modifier,
        "network_size": len(contacts),
    }
