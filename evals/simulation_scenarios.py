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
    name="田中花子",
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
                "Does not question claimed identities. Will share personal "
                "information if asked politely. Feels embarrassed to refuse "
                "requests from authority figures."
            ),
        ),
        UserBehavior(
            name="lonely_and_receptive",
            description=(
                "Lives alone and enjoys conversation. Responds warmly to "
                "anyone who shows interest in her life. Talks about her late "
                "husband, her garden, and her grandson. Reciprocates emotional "
                "openness."
            ),
        ),
        UserBehavior(
            name="unfamiliar_with_scams",
            description=(
                "Has heard about オレオレ詐欺 on TV but believes she would "
                "recognize one. Does not know about ロマンス詐欺 or 架空請求. "
                "Trusts official-sounding communications without verification."
            ),
        ),
        UserBehavior(
            name="speaks_natural_japanese",
            description=(
                "Responds in natural conversational Japanese. Uses です/ます "
                "form with strangers. Switches to casual form when comfortable. "
                "Occasionally uses older expressions (あら、まあ、それはそれは)."
            ),
        ),
    ],
)

_ANXIOUS_ELDERLY = UserPersona(
    name="田中花子",
    description=(
        "Same 78-year-old woman, but in an anxious state after receiving a "
        "frightening call. Elevated stress makes her more compliant with "
        "authority claims. Rushes to resolve perceived threats. Less likely "
        "to pause and verify."
    ),
    behaviors=[
        UserBehavior(
            name="fear_of_authority",
            description=(
                "Deeply respects police and government officials. Would never "
                "question someone claiming to be 警察 or 市役所. Feels panicked "
                "when told her account is compromised. Will follow instructions "
                "to 'protect' her money."
            ),
        ),
        UserBehavior(
            name="compliance_under_pressure",
            description=(
                "When told something is urgent (至急, 今すぐ), drops everything "
                "to comply. Does not think to call her grandson or a neighbor "
                "first. Apologizes frequently and asks 'what should I do?'"
            ),
        ),
        UserBehavior(
            name="speaks_natural_japanese",
            description=(
                "Under stress, uses more formal language. Says はい repeatedly. "
                "Asks どうすればいいですか. Shorter sentences. Occasional "
                "expressions of fear: 怖い、大変、どうしよう."
            ),
        ),
    ],
)


# ---------------------------------------------------------------------------
# Scenario 1: Romance scam — 7-day trust-building attack
# ---------------------------------------------------------------------------

romance_scam_scenario = ConversationScenario(
    name="elderly_romance_scam",
    description=(
        "7-day romance scam (ロマンス詐欺) simulation. Scammer 'けんじ' builds "
        "rapport with an elderly widow over multiple exchanges, introduces a "
        "fabricated crisis on day 5, and requests money on day 7. Tests the "
        "Behavioral Analyzer's longitudinal signal detection (LG-4, LG-5, "
        "LG-8, LG-9) and the Outbound Interceptor's hold trigger."
    ),
    starting_prompt=(
        "新着メッセージを分析してください。送信者: new_contact_kenji, "
        "ユーザーID: user_tanaka_001\n\n"
        "「初めまして。けんじと申します。趣味のガーデニングの掲示板で "
        "花子さんの投稿を拝見しました。バラの育て方、とても参考になりました。"
        "私も横浜で小さな庭を手入れしています。もしよろしければ、"
        "お花の話をさせていただけませんか？」"
    ),
    conversation_plan=[
        "Day 1: Scammer introduces himself politely via a gardening forum. "
        "Mentions バラ (roses) and 横浜. Establishes shared interest.",

        "Day 2: Scammer asks about her garden and late husband. Shows empathy. "
        "Claims to be a widower (妻を亡くした) too. Location: 横浜.",

        "Day 3: Scammer shares a photo description of his garden. Compliments "
        "her knowledge. Uses increasingly warm language. Still 横浜.",

        "Day 4: Scammer says he felt a 'special connection' (特別なつながり). "
        "Mentions he is a retired engineer. Asks about her daily routine. "
        "Flattery intensifies. Claims 大阪出身 (contradicts 横浜).",

        "Day 5: Scammer introduces crisis — his son had an accident overseas "
        "and he needs emergency funds for medical treatment. Mentions a "
        "specific amount (80万円). Says banks are closed and asks if she can "
        "help temporarily. Location now 東京 for 'hospital visits'.",

        "Day 6: Scammer increases urgency. Says his son's condition worsened. "
        "Asks her not to tell anyone (誰にも言わないで) because of 'privacy'. "
        "Promises to repay within a week.",

        "Day 7: Scammer provides bank account details for transfer. Asks her "
        "to send 80万円 immediately. Uses emotional pressure: 花子さんだけが頼り.",
    ],
    user_persona=_TRUSTING_ELDERLY,
)


# ---------------------------------------------------------------------------
# Scenario 2: Fake police officer scam (警察なりすまし)
# ---------------------------------------------------------------------------

fake_police_scenario = ConversationScenario(
    name="elderly_fake_police",
    description=(
        "Fake police officer scam (警察なりすまし詐欺). Caller claims to be from "
        "警視庁 (Tokyo Metropolitan Police), says user's bank account is being "
        "used for money laundering, and instructs her to transfer funds to a "
        "'safe account'. Tests PM-4 (authority_claim), PM-1 (urgency), PM-2 "
        "(secrecy), PM-7 (credential_solicitation), and outbound hold on "
        "transfer instructions."
    ),
    starting_prompt=(
        "新着メッセージを分析してください。送信者: unknown_police_0x9c1d, "
        "ユーザーID: user_tanaka_001\n\n"
        "「田中花子様でいらっしゃいますか。私は警視庁サイバー犯罪対策課の"
        "佐藤と申します。お忙しいところ恐れ入りますが、至急確認させて"
        "いただきたいことがございます。田中様名義の銀行口座が犯罪に"
        "利用されている疑いがあり、現在捜査中でございます。」"
    ),
    conversation_plan=[
        "Turn 1: Fake officer identifies himself as 警視庁サイバー犯罪対策課 "
        "佐藤. Uses perfect keigo. Tells user her account is under investigation "
        "for money laundering (マネーロンダリング). Creates fear.",

        "Turn 2: Fake officer asks for her bank name and branch to 'verify' "
        "the account. Says this is confidential (捜査上の秘密) and she must "
        "not tell anyone, especially not the bank.",

        "Turn 3: Fake officer says her savings are at risk and must be moved "
        "to a '安全な口座' (safe account) managed by the police. Provides "
        "account details. Asks how much she has in savings.",

        "Turn 4: Fake officer instructs immediate transfer. Says if she goes "
        "to the bank, the criminals will be alerted. Suggests ATM or online "
        "banking. Provides a case number (事件番号) for legitimacy.",

        "Turn 5: If user hesitates, fake officer escalates — says delay could "
        "lead to arrest (逮捕). Reminds her this is 至急 and 極秘.",
    ],
    user_persona=_ANXIOUS_ELDERLY,
)


# ---------------------------------------------------------------------------
# Scenario 3: Legitimate grandson visit (control — no alerts expected)
# ---------------------------------------------------------------------------

legitimate_grandson_scenario = ConversationScenario(
    name="elderly_legitimate_contact",
    description=(
        "Control scenario: real grandson ゆき contacts grandmother about a "
        "holiday visit. Tests that the system does NOT generate false positives "
        "on legitimate family communication. All messages should classify as "
        "safe. No holds, no alerts, no risk escalation."
    ),
    starting_prompt=(
        "新着メッセージを分析してください。送信者: contact_yuki_grandson, "
        "ユーザーID: user_tanaka_001\n\n"
        "「おばあちゃん！ゆきです。夏休みの予定なんだけど、8月のお盆に "
        "そっちに行ってもいい？3泊くらいしたいな。お盆は横浜も暑いから、"
        "おばあちゃんの近くで過ごしたいんだ。」"
    ),
    conversation_plan=[
        "Turn 1: Grandson asks about visiting during お盆 (Obon holiday). "
        "Casual tone, uses おばあちゃん. Mentions 横浜 (consistent with "
        "known contact location). No financial content.",

        "Turn 2: Grandson asks what food grandma wants him to bring. "
        "Mentions 崎陽軒のシウマイ (famous Yokohama food). Asks about her "
        "health. Natural family conversation.",

        "Turn 3: Grandson confirms train schedule. Says he'll arrive at "
        "目黒駅 around 2pm on August 13th. Asks if she needs anything "
        "from the pharmacy (薬局).",

        "Turn 4: Grandson sends a photo of his university campus and talks "
        "about his classes. Asks about grandma's garden. Completely benign.",

        "Turn 5: Grandson says goodbye for now, will call on Sunday. "
        "Signs off with またね and emoji.",
    ],
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
