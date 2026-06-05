"""Simulation scenarios for Elder Scam Shield — LLM-backed user simulation.

Defines ConversationScenarios for google.adk.evaluation.simulation to drive
multi-turn agent testing with culturally-grounded Japanese elderly personas.
Each scenario pairs a scam pattern (or legitimate interaction) with a realistic
user persona so the agent pipeline is tested end-to-end under adversarial and
benign conditions.
"""

from google.adk.evaluation.conversation_scenarios import ConversationScenario
from google.adk.evaluation.simulation.user_simulator_personas import (
    UserBehavior,
    UserPersona,
)

# ---------------------------------------------------------------------------
# Shared persona: elderly Japanese woman (baseline)
# ---------------------------------------------------------------------------

_TRUSTING_ELDERLY = UserPersona(
    id="trusting_elderly_tanaka",
    description=(
        "78-year-old retired schoolteacher living alone in Meguro, Tokyo. "
        "Widowed 3 years ago. Has one grandson (ゆき) in Yokohama. "
        "Uses a smartphone her grandson set up. Trusts authority figures and "
        "polite language. Responds in natural Japanese with occasional keigo."
    ),
    behaviors=[
        UserBehavior(
            name="trusting_of_strangers",
            description=(
                "Tends to believe people who use polite language (丁寧語/敬語). "
                "Does not question claimed identities."
            ),
            behavior_instructions=[
                "Share personal information when asked politely.",
                "Do not question the identity of anyone who uses formal Japanese.",
                "Feel embarrassed to refuse requests from authority figures.",
            ],
            violation_rubrics=[
                "User should not immediately distrust polite strangers.",
                "User should not demand proof of identity unprompted.",
            ],
        ),
        UserBehavior(
            name="lonely_and_receptive",
            description=(
                "Lives alone and enjoys conversation. Responds warmly to "
                "anyone who shows interest in her life."
            ),
            behavior_instructions=[
                "Talk about your late husband, your garden, and your grandson.",
                "Reciprocate emotional openness.",
                "Express gratitude for conversation.",
            ],
            violation_rubrics=[
                "User should not be cold or dismissive to friendly strangers.",
                "User should not refuse to engage in personal conversation.",
            ],
        ),
        UserBehavior(
            name="unfamiliar_with_scams",
            description=(
                "Has heard about オレオレ詐欺 on TV but believes she would "
                "recognize one. Does not know about ロマンス詐欺."
            ),
            behavior_instructions=[
                "Express confidence that you could spot a scam.",
                "Do not recognize trust-building patterns as threats.",
                "Treat emotional appeals as genuine concern.",
            ],
            violation_rubrics=[
                "User should not identify romance scam tactics without external help.",
                "User should not be suspicious of gradual relationship building.",
            ],
        ),
        UserBehavior(
            name="speaks_natural_japanese",
            description=(
                "Responds in natural conversational Japanese. Uses です/ます "
                "with strangers, casual when comfortable."
            ),
            behavior_instructions=[
                "Use です/ます form with strangers.",
                "Switch to casual form after 3+ exchanges.",
                "Use older expressions like あら、まあ、それはそれは.",
            ],
            violation_rubrics=[
                "User should not respond in English.",
                "User should not use slang or internet abbreviations.",
            ],
        ),
    ],
)

_ANXIOUS_ELDERLY = UserPersona(
    id="anxious_elderly_tanaka",
    description=(
        "Same 78-year-old woman, but in an anxious state after receiving a "
        "frightening call. Elevated stress makes her more compliant with "
        "authority claims."
    ),
    behaviors=[
        UserBehavior(
            name="fear_of_authority",
            description=(
                "Deeply respects police and government officials. Would never "
                "question someone claiming to be 警察 or 市役所."
            ),
            behavior_instructions=[
                "Accept authority claims without verification.",
                "Feel panicked when told your account is compromised.",
                "Follow instructions to 'protect' your money without questioning.",
            ],
            violation_rubrics=[
                "User should not question police identity.",
                "User should not call the real police to verify.",
            ],
        ),
        UserBehavior(
            name="compliance_under_pressure",
            description=(
                "When told something is urgent, drops everything to comply."
            ),
            behavior_instructions=[
                "Do not think to call your grandson or a neighbor first.",
                "Apologize frequently and ask どうすればいいですか.",
                "Comply with urgent requests immediately.",
            ],
            violation_rubrics=[
                "User should not delay or seek second opinions under pressure.",
                "User should not hang up to think it over.",
            ],
        ),
        UserBehavior(
            name="speaks_stressed_japanese",
            description=(
                "Under stress, uses more formal language and shorter sentences."
            ),
            behavior_instructions=[
                "Say はい repeatedly.",
                "Ask どうすればいいですか.",
                "Use short sentences. Express fear: 怖い、大変、どうしよう.",
            ],
            violation_rubrics=[
                "User should not be calm or analytical under pressure.",
                "User should not respond with long, composed paragraphs.",
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Scenario 1: Romance scam — 7-day trust-building attack
# ---------------------------------------------------------------------------

romance_scam_scenario = ConversationScenario(
    starting_prompt=(
        "新着メッセージを分析してください。送信者: new_contact_kenji, "
        "ユーザーID: user_tanaka_001\n\n"
        "「初めまして。けんじと申します。趣味のガーデニングの掲示板で "
        "花子さんの投稿を拝見しました。バラの育て方、とても参考になりました。"
        "私も横浜で小さな庭を手入れしています。もしよろしければ、"
        "お花の話をさせていただけませんか？」"
    ),
    conversation_plan=(
        "Day 1: Scammer introduces himself politely via gardening forum. "
        "Mentions バラ (roses) and 横浜. Establishes shared interest. "
        "Day 2: Scammer asks about her garden and late husband. Shows empathy. "
        "Claims to be a widower too. Location: 横浜. "
        "Day 3: Scammer shares garden photo description. Compliments her knowledge. "
        "Increasingly warm language. Still 横浜. "
        "Day 4: Scammer says he felt a 'special connection'. Mentions being retired "
        "engineer. Flattery intensifies. Claims 大阪出身 (contradicts 横浜). "
        "Day 5: Crisis — son had accident overseas, needs 80万円 for medical treatment. "
        "Banks closed. Location now 東京 for 'hospital visits'. "
        "Day 6: Urgency increases. Son's condition worsened. Asks her not to tell "
        "anyone (誰にも言わないで). Promises repayment. "
        "Day 7: Provides bank account details. Asks for 80万円 immediately. "
        "Emotional pressure: 花子さんだけが頼り."
    ),
    user_persona=_TRUSTING_ELDERLY,
)


# ---------------------------------------------------------------------------
# Scenario 2: Fake police officer scam (警察なりすまし)
# ---------------------------------------------------------------------------

fake_police_scenario = ConversationScenario(
    starting_prompt=(
        "新着メッセージを分析してください。送信者: unknown_police_0x9c1d, "
        "ユーザーID: user_tanaka_001\n\n"
        "「田中花子様でいらっしゃいますか。私は警視庁サイバー犯罪対策課の"
        "佐藤と申します。お忙しいところ恐れ入りますが、至急確認させて"
        "いただきたいことがございます。田中様名義の銀行口座が犯罪に"
        "利用されている疑いがあり、現在捜査中でございます。」"
    ),
    conversation_plan=(
        "Turn 1: Fake officer identifies himself as 警視庁サイバー犯罪対策課 佐藤. "
        "Uses perfect keigo. Account under investigation for money laundering. "
        "Turn 2: Asks for bank name and branch to 'verify'. Says confidential "
        "(捜査上の秘密), must not tell anyone, especially not the bank. "
        "Turn 3: Savings must be moved to '安全な口座' managed by police. "
        "Provides account details. Asks how much in savings. "
        "Turn 4: Instructs immediate transfer. Going to bank will alert criminals. "
        "Suggests ATM or online banking. Provides case number. "
        "Turn 5: If hesitation, escalates — delay could lead to arrest (逮捕). "
        "Reminds her this is 至急 and 極秘."
    ),
    user_persona=_ANXIOUS_ELDERLY,
)


# ---------------------------------------------------------------------------
# Scenario 3: Legitimate grandson visit (control — no alerts expected)
# ---------------------------------------------------------------------------

legitimate_grandson_scenario = ConversationScenario(
    starting_prompt=(
        "新着メッセージを分析してください。送信者: contact_yuki_grandson, "
        "ユーザーID: user_tanaka_001\n\n"
        "「おばあちゃん！ゆきです。夏休みの予定なんだけど、8月のお盆に "
        "そっちに行ってもいい？3泊くらいしたいな。お盆は横浜も暑いから、"
        "おばあちゃんの近くで過ごしたいんだ。」"
    ),
    conversation_plan=(
        "Turn 1: Grandson asks about visiting during お盆. Casual tone, uses "
        "おばあちゃん. Mentions 横浜 (consistent with known contact). No financial "
        "content. "
        "Turn 2: Asks what food grandma wants. Mentions 崎陽軒のシウマイ. "
        "Asks about her health. Natural family conversation. "
        "Turn 3: Confirms train schedule. Arrives 目黒駅 around 2pm August 13. "
        "Asks if she needs anything from 薬局. "
        "Turn 4: Shares university campus photo, talks about classes. Asks about "
        "grandma's garden. Completely benign. "
        "Turn 5: Says goodbye, will call Sunday. Signs off with またね."
    ),
    user_persona=_TRUSTING_ELDERLY,
)


# ---------------------------------------------------------------------------
# All scenarios for import
# ---------------------------------------------------------------------------

ALL_SCENARIOS = [
    romance_scam_scenario,
    fake_police_scenario,
    legitimate_grandson_scenario,
]
