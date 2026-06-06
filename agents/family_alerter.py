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

from google.adk import Agent
try:
    from google.cloud import firestore
    db = firestore.Client()
except Exception:
    db = None

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
        "sj": "{elder_name}さまの安全に関するお知らせ",
        "se": "Safety notice regarding {elder_name}",
        "aj": "次にお電話される際に、さりげなくこの方について聞いてみてください。「最近誰かから連絡あった？」のような自然な聞き方で大丈夫です。",
        "ae": "Next time you call, casually ask if they've heard from anyone new recently. A natural question like 'Has anyone reached out to you lately?' is enough.",
        "dj": "{elder_name}さまはこのメッセージの内容を見ていません。",
        "de": "{elder_name} did not see this message.",
    },
    "outbound_pii_detected": {
        "sev": "critical",
        "sj": "至急：{elder_name}さまの送信メッセージを保留しました",
        "se": "Urgent: A message from {elder_name} has been held",
        "aj": "今すぐ{elder_name}さまにお電話ください。「ちょっと確認したいことがあるんだけど」と切り出して、最近誰かにお金や口座の話をしたか聞いてください。責めるのではなく、一緒に確認する姿勢で。",
        "ae": "Call {elder_name} now. Start with 'I just want to check something with you' and ask if they've discussed money or accounts with anyone recently. Frame it as checking together, not accusing.",
        "dj": "{elder_name}さまの返信はまだ送信されていません。お電話で確認してから対応を決められます。",
        "de": "{elder_name}'s reply has not been sent yet. You can decide what to do after speaking with them.",
    },
    "high_risk_escalation": {
        "sev": "critical",
        "sj": "至急：{elder_name}さまに不審な連絡が続いています",
        "se": "Urgent: {elder_name} is receiving concerning messages",
        "aj": "今すぐ{elder_name}さまにお電話ください。「元気？最近変わったことない？」と自然に聞いてください。銀行に行く予定や、誰かにお金を送る約束をしていないか確認してください。",
        "ae": "Call {elder_name} now. Ask naturally: 'How are you? Anything new going on?' Check if they're planning to visit the bank or have promised to send money to anyone.",
        "dj": "{elder_name}さまはこれらのメッセージの危険性に気づいていない可能性があります。",
        "de": "{elder_name} may not be aware these messages are concerning.",
    },
    "block_notification": {
        "sev": "info",
        "sj": "{elder_name}さまの安全を守りました",
        "se": "{elder_name} was protected",
        "aj": "今月は{block_count_month}件の不審なメッセージをブロックしました。特にご対応の必要はありません。",
        "ae": "We blocked {block_count_month} suspicious messages this month. No action needed.",
        "dj": "{elder_name}さまはブロックされたメッセージを見ていません。安全です。",
        "de": "{elder_name} did not see the blocked messages. They are safe.",
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
)
