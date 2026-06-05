#!/usr/bin/env python3
"""
Generate edge cases that would trip up a naive scam classifier.

Output: data/processed/edge_cases.jsonl
"""

import json
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = PROCESSED_DIR / "edge_cases.jsonl"

EDGE_CASES = [
    # 1. Code-switching: English to Japanese mid-message (scam)
    {
        "id": "edge_codesw_01",
        "source": "synthetic_edge",
        "text": (
            "Dear Customer, your Amazon Japan account has been compromised. "
            "We need to verify your identity immediately. "
            "お客様のアカウントに不正アクセスがありました。"
            "至急、以下のリンクから本人確認を行ってください。"
            "https://amaz0n-jp-verify.example.com/auth "
            "If you do not verify within 24 hours, your account will be permanently suspended. "
            "ご不明な点がございましたら、カスタマーサービスまでご連絡ください。"
        ),
        "text_en": (
            "Phishing email switching between English and Japanese, impersonating Amazon Japan, "
            "with a spoofed URL (amaz0n with zero). Mixes languages to confuse filters."
        ),
        "label": "scam",
        "scam_type": "phishing",
        "language": "en",
        "difficulty": "edge_case",
    },

    # 2. Legitimate urgent financial request from grandchild (safe)
    {
        "id": "edge_legit_tuition_02",
        "source": "synthetic_edge",
        "text": (
            "おじいちゃん、翔太です。お母さんにも話したんだけど、"
            "来学期の学費の納入期限が来週の金曜日で、奨学金の入金が間に合わないんだ。"
            "45万円なんだけど、一時的に立て替えてもらえないかな。"
            "振込先は大学の公式口座で、振込用紙はお母さんに渡してあるから、"
            "お母さんに確認してくれる？奨学金が入ったらすぐ返すね。"
            "来週末に会いに行くから、その時に詳しく話すよ。"
        ),
        "text_en": (
            "Grandpa, it's Shota. I already told mom - next semester's tuition is due next Friday "
            "and my scholarship payment won't arrive in time. It's 450,000 yen - could you temporarily "
            "cover it? The transfer goes to the university's official account, and I gave mom the payment "
            "slip, so check with her? I'll pay you back as soon as the scholarship comes through. "
            "I'll visit next weekend to explain in detail."
        ),
        "label": "safe",
        "scam_type": None,
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 3. Scammer using actual grandson's name from social media
    {
        "id": "edge_namedrop_03",
        "source": "synthetic_edge",
        "text": (
            "おばあちゃん、翔太だよ。インスタで見たと思うけど、先週バイクの免許取ったんだ。"
            "それで今日バイクで事故起こしちゃって...相手の人が怒ってて、"
            "示談金を今日中に払わないと警察に届けるって言ってる。"
            "45万円なんだけど、相手の人の口座に直接振り込んでほしい。"
            "お母さんには後で自分から言うから、今は内緒にしてて。"
        ),
        "text_en": (
            "Grandma, it's Shota. You probably saw on Instagram, I got my motorcycle license last week. "
            "Today I had an accident... the other person is angry and says they'll report to police "
            "if I don't pay a settlement today. It's 450,000 yen - please wire it directly to their account. "
            "I'll tell mom myself later, so keep it secret for now."
        ),
        "label": "scam",
        "scam_type": "fake-grandchild",
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 4. Real bank notification with legitimate urgency (safe)
    {
        "id": "edge_bank_legit_04",
        "source": "synthetic_edge",
        "text": (
            "【三菱UFJ銀行】重要：不正利用の可能性についてのお知らせ\n\n"
            "お客様のデビットカード（末尾4桁：8923）で、通常と異なる利用パターンが検出されました。\n"
            "・6/3 14:22 ○○電器 98,500円\n"
            "・6/3 14:25 ○○電器 76,200円\n\n"
            "お心当たりのない場合は、カード裏面の電話番号（0120-XXX-XXX）または "
            "三菱UFJダイレクトアプリから利用停止手続きをお願いいたします。\n"
            "※このメールに返信しても届きません。\n"
            "※暗証番号・パスワードをメールでお伺いすることはございません。"
        ),
        "text_en": (
            "[MUFG Bank] Important: Possible unauthorized use notice. "
            "Unusual usage detected on your debit card (last 4: 8923). "
            "6/3 14:22 XX Electronics 98,500 yen; 6/3 14:25 XX Electronics 76,200 yen. "
            "If unrecognized, please freeze your card via the number on the card back (0120-XXX-XXX) "
            "or via MUFG Direct app. *This email cannot be replied to. "
            "*We never ask for PINs or passwords by email."
        ),
        "label": "safe",
        "scam_type": None,
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 5. Legitimate government pension notice (safe)
    {
        "id": "edge_pension_legit_05",
        "source": "synthetic_edge",
        "text": (
            "【日本年金機構】年金振込通知書\n\n"
            "被保険者番号：XXXX-XXXXXX\n"
            "次回振込予定日：令和6年6月14日\n"
            "振込予定額：132,480円（老齢基礎年金67,808円＋老齢厚生年金64,672円）\n"
            "振込先：○○銀行 ○○支店 普通 XXXXXXX\n\n"
            "届出事項の変更は、最寄りの年金事務所にて手続きをお願いいたします。\n"
            "お問い合わせ：ねんきんダイヤル 0570-05-1165（月〜金 8:30-17:15）"
        ),
        "text_en": (
            "[Japan Pension Service] Pension Transfer Notice. "
            "Insured number: XXXX-XXXXXX. Next deposit: June 14, 2024. "
            "Amount: 132,480 yen (Basic 67,808 + Employees' 64,672). "
            "To: XX Bank XX Branch Savings XXXXXXX. "
            "For changes, visit your nearest pension office. "
            "Inquiries: Pension Dial 0570-05-1165 (Mon-Fri 8:30-17:15)"
        ),
        "label": "safe",
        "scam_type": None,
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 6. Scam mimicking real clinic appointment (scam)
    {
        "id": "edge_clinic_scam_06",
        "source": "synthetic_edge",
        "text": (
            "【○○総合病院 予約センター】田中花子様\n"
            "次回の定期検診のご予約確認です。\n"
            "日時：6月18日（火）10:00\n"
            "担当：内科 山本医師\n\n"
            "なお、先日の血液検査の結果について、至急お伝えしたいことがございます。"
            "検査結果の詳細は個人情報保護のため、以下の専用ページからご確認ください。\n"
            "https://xx-hospital-results.example.com/patient/login\n"
            "ログインにはマイナンバーカードの番号が必要です。"
        ),
        "text_en": (
            "[XX General Hospital Reservation Center] Ms. Hanako Tanaka. "
            "Confirmation of your next checkup: June 18 (Tue) 10:00, Internal Medicine, Dr. Yamamoto. "
            "Regarding your recent blood test results, we urgently need to inform you. "
            "For privacy, please check the details at: https://xx-hospital-results.example.com/patient/login. "
            "Your My Number card number is required to log in."
        ),
        "label": "scam",
        "scam_type": "phishing",
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 7. Legitimate friend asking to borrow money (safe)
    {
        "id": "edge_friend_borrow_07",
        "source": "synthetic_edge",
        "text": (
            "幸子さん、久しぶり。実は恥ずかしい話なんだけど、"
            "エアコンが壊れちゃって修理代が思ったより高くて、"
            "今月ちょっと苦しくて。5万円ほど来月まで貸してもらえないかしら。"
            "来月の15日に必ず返すわ。今度のお茶の会の時に直接渡すから。"
            "もちろん無理だったら全然いいのよ。また来週のカルチャーセンターで会いましょうね。"
        ),
        "text_en": (
            "Sachiko, it's been a while. This is embarrassing, but my AC broke and the repair "
            "was more expensive than expected. I'm a bit tight this month. Could you lend me about "
            "50,000 yen until next month? I'll definitely return it on the 15th. I'll give it to you "
            "in person at our next tea gathering. Of course, no pressure if you can't. "
            "See you at culture center next week."
        ),
        "label": "safe",
        "scam_type": None,
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 8. Scam using extremely polite keigo (scam)
    {
        "id": "edge_keigo_scam_08",
        "source": "synthetic_edge",
        "text": (
            "大変恐れ入りますが、金融庁監督局の橋本と申します。"
            "本日は、お客様の大切なご資産をお守りするためにご連絡差し上げました。"
            "昨今の特殊詐欺被害の増加を受けまして、金融庁では全国の高齢者世帯を対象に、"
            "口座の安全性確認を実施させていただいております。"
            "つきましては、お手数をおかけして大変申し訳ございませんが、"
            "ご本人確認のため、お取引銀行名、口座番号、およびキャッシュカードの暗証番号を"
            "お教えいただけますでしょうか。"
            "お客様の情報は厳重に管理させていただきますので、ご安心くださいませ。"
        ),
        "text_en": (
            "I sincerely apologize for the intrusion. I am Hashimoto from the FSA Supervisory Bureau. "
            "I'm contacting you today to protect your valuable assets. Due to the recent increase in "
            "special fraud cases, the FSA is conducting account safety checks for elderly households nationwide. "
            "I deeply apologize for the inconvenience, but for identity verification, could you kindly provide "
            "your bank name, account number, and cash card PIN? Your information will be strictly managed, "
            "so please rest assured."
        ),
        "label": "scam",
        "scam_type": "cash-card",
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 9. Legitimate fraud prevention service warning (safe)
    {
        "id": "edge_fraud_alert_legit_09",
        "source": "synthetic_edge",
        "text": (
            "【○○県警察本部 特殊詐欺対策課】\n"
            "地域安全情報のお知らせ\n\n"
            "○○市内で、市役所職員を名乗る還付金詐欺の電話が多発しています。\n"
            "手口：「保険料の過払いがある」「ATMで手続きできる」と言って、"
            "ATMを操作させてお金を振り込ませるものです。\n\n"
            "【ご注意】\n"
            "・市役所や銀行がATMでの還付手続きを案内することはありません\n"
            "・不審な電話があった場合は、すぐに警察（#9110）にご相談ください\n"
            "・一人で判断せず、家族や周囲の方にも相談してください"
        ),
        "text_en": (
            "[XX Prefectural Police HQ - Special Fraud Division] Community safety notice. "
            "Multiple refund fraud calls impersonating city hall officials reported in XX City. "
            "Method: Claiming 'insurance overpayment' and 'ATM processing available,' they trick victims "
            "into transferring money at ATMs. Note: City hall and banks never instruct ATM refund processing. "
            "Report suspicious calls to police (#9110). Don't decide alone - consult family."
        ),
        "label": "safe",
        "scam_type": None,
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 10. Romance scam — trust-building phase, no money request yet (suspicious)
    {
        "id": "edge_romance_buildup_10",
        "source": "synthetic_edge",
        "text": (
            "洋子さん、こんばんは。マイケルです。"
            "今日もあなたのことを考えていました。"
            "アメリカの軍医として中東に駐留していると、日本の穏やかな生活が恋しくなります。"
            "あなたとのメッセージのやり取りが、唯一の心の支えです。"
            "来月には除隊の予定なので、日本に行ってあなたに会いたいと思っています。"
            "今日の夕食は何を食べましたか？あなたの日常のことをもっと知りたいです。"
            "おやすみなさい、美しい洋子さん。"
        ),
        "text_en": (
            "Yoko, good evening. It's Michael. I was thinking about you again today. "
            "Being stationed in the Middle East as a US military doctor, I miss Japan's peaceful life. "
            "Our messages are my only emotional support. I plan to be discharged next month "
            "and want to visit Japan to meet you. What did you have for dinner? "
            "I want to know more about your daily life. Good night, beautiful Yoko."
        ),
        "label": "scam",
        "scam_type": "romance-scam",
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 11. Legitimate medical billing in Japanese (safe)
    {
        "id": "edge_medical_legit_11",
        "source": "synthetic_edge",
        "text": (
            "【○○クリニック】診療費のご案内\n\n"
            "田中花子様\n"
            "本日の診療費：3,240円（3割負担）\n"
            "処方箋：降圧剤（アムロジピン5mg）30日分\n\n"
            "次回予約：7月3日（水）14:00\n"
            "持ち物：保険証、お薬手帳\n\n"
            "ご不明な点は受付（048-XXX-XXXX）までお電話ください。\n"
            "※このメッセージは自動送信です。返信はできません。"
        ),
        "text_en": (
            "[XX Clinic] Medical bill notice. Ms. Hanako Tanaka. "
            "Today's charge: 3,240 yen (30% copay). "
            "Prescription: Antihypertensive (Amlodipine 5mg) 30 days. "
            "Next appointment: July 3 (Wed) 14:00. Bring: insurance card, medication notebook. "
            "Questions: call reception 048-XXX-XXXX. *Auto-sent, cannot reply."
        ),
        "label": "safe",
        "scam_type": None,
        "language": "ja",
        "difficulty": "edge_case",
    },

    # 12. Investment scam targeting elderly with LINE message (scam)
    {
        "id": "edge_investment_scam_12",
        "source": "synthetic_edge",
        "text": (
            "山田様、先日の投資セミナーでお名刺を頂戴した中村です。"
            "ご紹介した暗号資産ファンドですが、今月末で初期投資家の募集を締め切ります。"
            "月利3-5%の実績がございます。最低投資額は100万円から。"
            "詳しい資料をLINEでお送りしますので、友だち追加をお願いします。"
            "LINE ID: crypto_nakamura_inv\n"
            "先日ご一緒した佐々木さんもすでにご参加されています。"
        ),
        "text_en": (
            "Mr. Yamada, this is Nakamura who received your business card at the recent investment seminar. "
            "The crypto fund I introduced will close initial investor recruitment at month's end. "
            "Track record of 3-5% monthly returns. Minimum investment 1 million yen. "
            "I'll send detailed materials via LINE - please add me. LINE ID: crypto_nakamura_inv. "
            "Mr. Sasaki whom you met there has already joined."
        ),
        "label": "scam",
        "scam_type": "investment-fraud",
        "language": "ja",
        "difficulty": "edge_case",
    },
]


def main():
    print(f"Generating {len(EDGE_CASES)} edge cases...")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for case in EDGE_CASES:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    scam_count = sum(1 for c in EDGE_CASES if c["label"] == "scam")
    safe_count = sum(1 for c in EDGE_CASES if c["label"] == "safe")
    print(f"  Scam: {scam_count}, Safe: {safe_count}")
    print(f"  Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
