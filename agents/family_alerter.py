"""Family Alerter agent — human-in-the-loop bridge for Elder Scam Shield.

Translates technical risk assessments into warm, actionable Japanese
notifications for family members. Never exposes scam message content,
even to family. Bilingual (JA primary, EN secondary), rate-limited,
dignity-preserving.

ADK primitive: CREATE
Pipeline subscribes: sender.risk_updated, outbound.held
Pipeline publishes:  alert.delivered
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from google.adk import Agent
from .schemas import AlertRecord
from .db import db

JST = timezone(timedelta(hours=9))
DEDUP_WINDOW_H = 24
RATE_LIMIT_PER_DAY = 5

# Family Alerter UX principles (from adversarial design review):
# 1. NEVER use 詐欺 (scam) in alert text — it's a confrontation trigger in Japanese.
#    A daughter who reads "scam detected" panic-confronts mom, mom feels surveilled,
#    mom turns the system off. The system causes the damage the scam would have.
# 2. Always assert what the elder DID NOT see: "{elder_name} did not see this message"
#    is the single highest-trust line in the system.
# 3. Give concrete 30-second scripts, not vague "call and confirm."
# 4. Silent blocks are high-value information — include monthly counter.
#
# Template fields:
#   sev: severity (info/warning/critical)
#   sj/se: subject line (ja/en)
#   aj/ae: action script (ja/en) — what to do in the NEXT 30 SECONDS
#   dj/de: dignity line (ja/en) — assure what the elder did NOT see

TEMPLATES: dict[str, dict[str, Any]] = {
    "suspicious_sender": {
        "sev": "warning",
        "sj": "不審な連絡パターンを検知 — ご確認をお願いします",
        "se": "Suspicious contact pattern detected for {elder_name}",
        "aj": "未確認の送信者から{elder_name}さまへの連絡に不審なパターンが検出されました。なりすまし詐欺（オレオレ詐欺）の可能性があります。{elder_name}さまに確認のご連絡をお勧めします。リスクが高まった場合、Faxiが自動的にブロックします。",
        "ae": "An unverified sender is showing patterns consistent with potential impersonation fraud (ore-ore scam) in their communication with {elder_name}. We recommend following up with {elder_name} to check in. If risk increases, Faxi will automatically block further messages.",
        "dj": "{elder_name}さまはこの通知を見ていません。",
        "de": "{elder_name} did not see this notification.",
    },
    "outbound_pii_detected": {
        "sev": "critical",
        "sj": "至急 — {elder_name}さまの返信を保留しました",
        "se": "Urgent: {elder_name}'s outbound reply has been held",
        "aj": "{elder_name}さまが個人情報（銀行口座・カード番号等）を含む返信を送信しようとしました。送信は保留されています。{elder_name}さまに確認のご連絡をお勧めします。",
        "ae": "{elder_name} attempted to send a reply containing sensitive information (bank details, card numbers, or similar). The reply has been held and not sent. We recommend contacting {elder_name} to discuss.",
        "dj": "{elder_name}さまの返信はまだ送信されていません。",
        "de": "{elder_name}'s reply has not been sent yet.",
    },
    "high_risk_escalation": {
        "sev": "critical",
        "sj": "至急 — 高リスクの通信パターンを検知",
        "se": "Urgent: high-risk communication pattern detected for {elder_name}",
        "aj": "{elder_name}さまへの連絡に高リスクのパターンが検出されました。金銭要求、秘密の強要、緊急性の訴えが含まれています。{elder_name}さまに確認のご連絡をお勧めします。心配な場合は警察相談ダイヤル #9110 にご相談ください。",
        "ae": "High-risk patterns detected in communication with {elder_name}: financial demands, secrecy requests, and urgency pressure. We recommend contacting {elder_name} to check in. If concerned, contact police consultation line #9110.",
        "dj": "{elder_name}さまはこれらのメッセージを見ていません。",
        "de": "{elder_name} did not see these messages.",
    },
    "block_notification": {
        "sev": "info",
        "sj": "今月{block_count_month}件目の自動ブロックを実行しました",
        "se": "Background protection: {block_count_month} block(s) this month for {elder_name}",
        "aj": "ご対応の必要はありません。{elder_name}さまにはこのメッセージは届いていません。",
        "ae": "No action needed. {elder_name} did not see this message. This is the {block_count_month}-th block this month.",
        "dj": "{elder_name}さまはブロックされたメッセージを見ていません。",
        "de": "{elder_name} did not see the blocked messages.",
    },
}


def generate_alert(
    alert_type: str,
    user_id: str,
    sender_id: str,
    risk_score: float,
    risk_factors: list[str],
    contradiction_count: int,
    message_count: int,
    days_active: int,
    elder_name: str = "",
    block_count_month: int = 0,
) -> dict[str, Any]:
    """Generate a bilingual family alert from a risk assessment.

    Returns the composed alert with evidence summary, or a dedup /
    rate-limit notice if the family has been contacted recently.
    """
    tmpl = TEMPLATES.get(alert_type)
    if not tmpl:
        return {"error": f"Unknown alert_type: {alert_type}"}

    now = datetime.now(JST)

    # Load family contact preferences
    if db is not None:
        profile = (db.collection("users").document(user_id).get().to_dict() or {})
        family = profile.get("family_contacts", [{}])[0]
        family_member_id = family.get("id", "unknown")
        delivery_channel = family.get("preferred_channel", "email")

        # Dedup & rate-limit within sliding 24 h window
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
    else:
        family_member_id = "family-demo"
        delivery_channel = "email"

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

    # Template substitution — elder name + block counter
    subs = {"elder_name": elder_name or "ご家族", "block_count_month": str(block_count_month)}
    def fill(s):
        for k, v in subs.items():
            s = s.replace("{" + k + "}", v)
        return s

    record = {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "severity": tmpl["sev"],
        "user_id": user_id,
        "sender_id": sender_id,
        "recipient": family_member_id,
        "delivery_channel": delivery_channel,
        "subject_ja": fill(tmpl["sj"]),
        "subject_en": fill(tmpl["se"]),
        "action_ja": fill(tmpl["aj"]),
        "action_en": fill(tmpl["ae"]),
        "dignity_ja": fill(tmpl.get("dj", "")),
        "dignity_en": fill(tmpl.get("de", "")),
        "evidence_summary": evidence,
        "elder_did_not_see": True,
        "timestamp": now,
        "delivery_status": "pending",
        "response_action": None,
    }

    # Persist notification record to Memory Bank
    if db is not None:
        db.collection("notifications").document(alert_id).set(record)

    # Pipeline event: alert.delivered
    pipeline_event = {
        "event": "alert.delivered",
        "alert_id": alert_id,
        "family_member_id": family_member_id,
        "delivery_channel": delivery_channel,
        "response_deadline": deadline,
    }

    return {"alert": record, "pipeline_event": pipeline_event}


family_alerter = Agent(
    model="gemini-2.5-flash-lite",
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
    output_schema=AlertRecord,
    output_key="alert",
)
