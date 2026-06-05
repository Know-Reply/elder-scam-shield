"""Family Alerter agent — human-in-the-loop bridge for Elder Scam Shield.

Translates technical risk assessments into warm, actionable Japanese
notifications for family members. Never exposes scam message content,
even to family. Bilingual (JA primary, EN secondary), rate-limited,
dignity-preserving.

ADK primitive: CREATE
A2A subscribes: sender.risk_updated, outbound.held
A2A publishes:  alert.delivered
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from google.adk.agents import Agent
from google.adk.tools import tool
from google.cloud import firestore

JST = timezone(timedelta(hours=9))
DEDUP_WINDOW_H = 24
RATE_LIMIT_PER_DAY = 5
db = firestore.Client()

# fmt: off
TEMPLATES: dict[str, dict[str, Any]] = {
    "suspicious_sender":      {"sev": "warning",  "sj": "不審な連絡先についてのお知らせ",        "se": "Notice about a suspicious contact",      "aj": "お時間のあるときにご確認いただければ幸いです。", "ae": "Please review when convenient."},
    "outbound_pii_detected":  {"sev": "critical", "sj": "至急：個人情報の送信を保留しました",    "se": "Urgent: outbound personal information held", "aj": "至急お電話でご本人にご確認ください。",         "ae": "Please call and confirm with them directly."},
    "high_risk_escalation":   {"sev": "critical", "sj": "至急：高リスクの連絡を検知しました",    "se": "Urgent: high-risk communication detected",  "aj": "至急お電話でご本人にご確認ください。",         "ae": "Please call and confirm with them directly."},
    "block_notification":     {"sev": "info",     "sj": "不審なメッセージをブロックしました",    "se": "Suspicious message blocked",                "aj": "特にご対応の必要はありません。",               "ae": "No action needed."},
}
# fmt: on

@tool
def generate_alert(
    alert_type: str,
    user_id: str,
    sender_id: str,
    risk_score: float,
    risk_factors: list[str],
    contradiction_count: int,
    message_count: int,
    days_active: int,
) -> dict[str, Any]:
    """Generate a bilingual family alert from a risk assessment.

    Returns the composed alert with evidence summary, or a dedup /
    rate-limit notice if the family has been contacted recently.
    """
    tmpl = TEMPLATES.get(alert_type)
    if not tmpl:
        return {"error": f"Unknown alert_type: {alert_type}"}

    # Load family contact preferences
    profile = (db.collection("users").document(user_id).get().to_dict() or {})
    family = profile.get("family_contacts", [{}])[0]
    family_member_id = family.get("id", "unknown")
    delivery_channel = family.get("preferred_channel", "email")

    # Dedup & rate-limit within sliding 24 h window
    now = datetime.now(JST)
    recent = list(
        db.collection("notifications")
        .where("user_id", "==", user_id)
        .where("timestamp", ">=", now - timedelta(hours=DEDUP_WINDOW_H))
        .stream()
    )
    if any(
        (d := n.to_dict()).get("alert_type") == alert_type
        and d.get("sender_id") == sender_id
        for n in recent
    ):
        return {"status": "dedup", "message": "Duplicate alert suppressed within 24 h."}
    if len(recent) >= RATE_LIMIT_PER_DAY:
        return {"status": "rate_limited", "message": "Daily alert cap reached."}

    # Evidence summary — counts and categories, never raw content
    evidence = {
        "risk_score": round(risk_score, 2),
        "risk_factors": risk_factors,
        "contradiction_count": contradiction_count,
        "message_count": message_count,
        "days_active": days_active,
        "assessed_at": now.isoformat(),
    }

    alert_id = f"alert-{user_id}-{now.strftime('%Y%m%d%H%M%S')}"
    is_critical = tmpl["sev"] == "critical"
    deadline = (now + timedelta(hours=4 if is_critical else 24)).isoformat()

    record = {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "severity": tmpl["sev"],
        "user_id": user_id,
        "sender_id": sender_id,
        "recipient": family_member_id,
        "delivery_channel": delivery_channel,
        "subject_ja": tmpl["sj"],
        "subject_en": tmpl["se"],
        "action_ja": tmpl["aj"],
        "action_en": tmpl["ae"],
        "evidence_summary": evidence,
        "timestamp": now,
        "delivery_status": "pending",
        "response_action": None,
    }

    # Persist notification record to Memory Bank
    db.collection("notifications").document(alert_id).set(record)

    # A2A publish: alert.delivered
    a2a_event = {
        "event": "alert.delivered",
        "alert_id": alert_id,
        "family_member_id": family_member_id,
        "delivery_channel": delivery_channel,
        "response_deadline": deadline,
    }

    return {"alert": record, "a2a": a2a_event}


family_alerter = Agent(
    model="gemini-2.0-flash",
    name="family_alerter",
    description=(
        "Translates scam detection events into warm, actionable Japanese "
        "notifications for family members. Never reveals message content."
    ),
    instruction=(
        "You are the Family Alerter for Elder Scam Shield. Compose warm, "
        "non-technical bilingual notifications (Japanese primary, English "
        "secondary) for family members when scam risk is detected.\n\n"
        "RULES:\n"
        "- NEVER include actual message content from the scam conversation.\n"
        "- Frame evidence as counts and categories, not quotes.\n"
        "- Preserve the elderly user's dignity — never imply incompetence.\n"
        "- Use respectful keigo when referring to the protected user.\n"
        "- Keep Japanese natural and warm, as if from a trusted service.\n"
        "- Fill the provided template structure; do not invent new fields."
    ),
    tools=[generate_alert],
)
