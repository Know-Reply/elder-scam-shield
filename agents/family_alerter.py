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
from agents.schemas import AlertRecord
from agents.db import db

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
        "sj": "新しい連絡先について — ご確認のお願い",
        "se": "A new contact for {elder_name} — please review",
        "aj": "今週中にお時間のあるとき、{elder_name}さまに「最近、新しいお友達やご連絡された方はいらっしゃいますか？」と自然な形でお声がけください。聞き役に徹してください。",
        "ae": "Within the next few days, ask {elder_name} casually: 'who have you been talking to lately?' Listen — don't lead. Please do not say 'scam' — it puts {elder_name} on the defensive and makes the system feel like surveillance.",
        "dj": "{elder_name}さまはこのメッセージを見ていません。",
        "de": "{elder_name} did not see this message.",
    },
    "outbound_pii_detected": {
        "sev": "critical",
        "sj": "至急 — 個人情報の送信を保留しました",
        "se": "Urgent: {elder_name}'s outbound message containing personal information has been held",
        "aj": "4時間以内にお電話ください。世間話から入り、もしお金や口座番号、振り込みの話が出てきたら、「いいね、でも一緒に確認してから決めよう」とご提案ください。「詐欺」という言葉は避けてください。",
        "ae": "Within 4 hours: call {elder_name}. Start with normal conversation. If money, bank info, or transfers come up, gently say: 'sounds interesting — let's wait and check together before we decide.' This buys time without confrontation. Please do not say 'scam.'",
        "dj": "{elder_name}さまの返信はまだ送信されていません。",
        "de": "{elder_name}'s reply has not been sent yet.",
    },
    "high_risk_escalation": {
        "sev": "critical",
        "sj": "至急 — 高リスクの通信パターンを検知",
        "se": "Urgent: high-risk communication pattern detected with {elder_name}",
        "aj": "4時間以内にお電話ください。詳細はお伝えせず、「最近どう？」と普段通りにお話を始めてください。もし新しいご連絡相手の話が出たら、聞き役に徹し、ご本人の言葉でお状況を教えてもらってください。",
        "ae": "Within 4 hours: call {elder_name}. Don't mention the alert. Start with your usual check-in. If a new contact comes up, listen and let {elder_name} describe the situation in their own words. Decide together after — not before.",
        "dj": "{elder_name}さまはこれらのメッセージを見ていません。",
        "de": "{elder_name} did not see these messages.",
    },
    "block_notification": {
        "sev": "info",
        "sj": "今月{block_count_month}件目の自動ブロックを実行しました",
        "se": "Background protection: {block_count_month} block(s) this month for {elder_name}",
        "aj": "ご対応の必要はありません。{elder_name}さまにはこのメッセージは届いていません。システムは設計どおり機能しています。",
        "ae": "No action needed. {elder_name} did not see this message. The system is working as designed — this is the {block_count_month}-th block this month, all silent and resolved.",
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
    model="gemini-3.1-flash-lite",
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
