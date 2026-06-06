#!/usr/bin/env python3
"""
Process scraped antiphishing.jp data into Elder Scam Shield corpus format.

Reads:  data/raw/antiphishing_cases.jsonl
Writes: data/processed/antiphishing_corpus.jsonl

Each output entry follows the corpus schema:
{
    "id": "antiphishing_001",
    "source": "antiphishing.jp",
    "text": "phishing message text in Japanese",
    "label": "scam",
    "scam_type": "fake-bank|credential-phishing|gov-impersonation|fictitious-billing",
    "language": "ja",
    "impersonated_brand": "Amazon|楽天|三菱UFJ|etc",
    "date": "2026-05-18",
    "content_type": "subject_line|phishing_url|combined"
}
"""

import json
import re
from pathlib import Path

RAW_PATH = Path(__file__).parent / "raw" / "antiphishing_cases.jsonl"
OUTPUT_PATH = Path(__file__).parent / "processed" / "antiphishing_corpus.jsonl"

# Map brands to NPA scam_type categories
BRAND_TO_SCAM_TYPE = {
    # Banks → fake-bank
    "三菱UFJ銀行": "fake-bank",
    "みずほ銀行": "fake-bank",
    "ゆうちょ銀行": "fake-bank",
    "りそな銀行": "fake-bank",
    "auじぶん銀行": "fake-bank",
    "三井住友信託銀行": "fake-bank",
    "住信SBIネット銀行": "fake-bank",
    "JAバンク": "fake-bank",
    "ろうきん": "fake-bank",
    "GMOあおぞらネット銀行": "fake-bank",
    "金融機関（複数）": "fake-bank",
    # Securities → credential-phishing (investment fraud angle)
    "楽天証券": "credential-phishing",
    "SBI証券": "credential-phishing",
    "SBIネオトレード証券": "credential-phishing",
    "野村證券": "credential-phishing",
    "松井証券": "credential-phishing",
    "マネックス証券": "credential-phishing",
    "大和証券": "credential-phishing",
    "みずほ証券": "credential-phishing",
    "SMBC日興証券": "credential-phishing",
    "三菱UFJモルガン・スタンレー証券": "credential-phishing",
    "岩井コスモ証券": "credential-phishing",
    "GMOクリック証券": "credential-phishing",
    # Government → gov-impersonation
    "国税庁": "gov-impersonation",
    "日本年金機構": "gov-impersonation",
    "国民健康保険": "gov-impersonation",
    "住民税": "gov-impersonation",
    "マイナポータル": "gov-impersonation",
    "マイナポイント事務局": "gov-impersonation",
    "国勢調査": "gov-impersonation",
    "東京都水道局": "gov-impersonation",
    # E-commerce → fictitious-billing
    "Amazon": "fictitious-billing",
    "楽天": "fictitious-billing",
    "イオンカード": "fictitious-billing",
    "ビックカメラ": "fictitious-billing",
    "ローソンチケット": "fictitious-billing",
    "宝くじ公式サイト": "fictitious-billing",
    # Payment → credential-phishing
    "PayPay": "credential-phishing",
    "LINE Pay": "credential-phishing",
    "LINE": "credential-phishing",
    "au PAY": "credential-phishing",
    "Kyash": "credential-phishing",
    # Telecom → fictitious-billing
    "ソフトバンク": "fictitious-billing",
    "NTT": "fictitious-billing",
    "au": "fictitious-billing",
    # Delivery / Transport → fictitious-billing
    "日本郵便": "fictitious-billing",
    "ヤマト運輸": "fictitious-billing",
    "佐川急便": "fictitious-billing",
    "ETC利用照会サービス": "fictitious-billing",
    "えきねっと": "fictitious-billing",
    "JR": "fictitious-billing",
    "ANA": "fictitious-billing",
    "WESTER": "fictitious-billing",
    # Insurance → fictitious-billing
    "第一生命": "fictitious-billing",
    "日本生命": "fictitious-billing",
    "保険会社（複数）": "fictitious-billing",
    # Credit cards → credential-phishing
    "JCB": "credential-phishing",
    "Mastercard": "credential-phishing",
    "セディナカード": "credential-phishing",
    # Consumer finance → fictitious-billing
    "アコム": "fictitious-billing",
    "プロミス": "fictitious-billing",
    "アイフル": "fictitious-billing",
    "レイク": "fictitious-billing",
    "ORIX MONEY": "fictitious-billing",
    # Tech → credential-phishing
    "OpenAI/ChatGPT": "credential-phishing",
    "Apple": "credential-phishing",
    "So-net": "credential-phishing",
    # Utilities → fictitious-billing
    "東京電力": "fictitious-billing",
    "東京ガス": "fictitious-billing",
}


def classify_scam_type(brand: str) -> str:
    """Map brand to NPA scam_type. Falls back to heuristics."""
    if brand in BRAND_TO_SCAM_TYPE:
        return BRAND_TO_SCAM_TYPE[brand]

    # Heuristic fallbacks
    brand_lower = brand.lower()
    if any(kw in brand_lower for kw in ["銀行", "bank", "信金", "信用"]):
        return "fake-bank"
    if any(kw in brand_lower for kw in ["税", "年金", "保険料", "マイナ", "国民", "住民", "省", "庁"]):
        return "gov-impersonation"
    if any(kw in brand_lower for kw in ["証券", "securities"]):
        return "credential-phishing"
    if any(kw in brand_lower for kw in ["pay", "カード", "card"]):
        return "credential-phishing"

    return "credential-phishing"  # Default


def build_message_text(case: dict) -> list[dict]:
    """
    Build synthetic message texts from case data.

    Returns a list of corpus entries (one per subject line, plus combined entries).
    """
    entries = []
    brand = case.get("impersonated_brand", "unknown")
    date = case.get("date", "")
    scam_type = classify_scam_type(brand)

    subject_lines = case.get("subject_lines", [])
    phishing_urls = case.get("phishing_urls", [])

    # Entry for each subject line (these ARE the actual phishing text)
    for subj in subject_lines:
        entries.append({
            "text": subj,
            "content_type": "subject_line",
            "brand": brand,
            "date": date,
            "scam_type": scam_type,
        })

    # Combined entry: subject + representative phishing URL (simulates full message)
    if subject_lines and phishing_urls:
        # Pick up to 3 subject lines and combine with URL context
        for subj in subject_lines[:3]:
            url_sample = phishing_urls[0] if phishing_urls else ""
            combined = f"{subj}\n\n詳細はこちらからご確認ください。\n{url_sample}"
            entries.append({
                "text": combined,
                "content_type": "combined",
                "brand": brand,
                "date": date,
                "scam_type": scam_type,
            })

    # If no subject lines but we have full text, extract key phrases
    if not subject_lines:
        excerpt = case.get("full_text_excerpt", "")
        title = case.get("title", "")
        if title:
            entries.append({
                "text": title,
                "content_type": "alert_title",
                "brand": brand,
                "date": date,
                "scam_type": scam_type,
            })

    return entries


def main():
    if not RAW_PATH.exists():
        print(f"Raw data not found at {RAW_PATH}")
        print("Run scrape_antiphishing.py first, or the script will use embedded data.")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read raw cases
    cases = []
    with open(RAW_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    print(f"Loaded {len(cases)} raw cases")

    # Process into corpus entries
    corpus = []
    seen_texts = set()  # Deduplicate
    idx = 0

    for case in cases:
        entries = build_message_text(case)
        for entry in entries:
            text = entry["text"].strip()
            if not text or text in seen_texts:
                continue
            if len(text) < 5:  # Skip very short entries
                continue

            seen_texts.add(text)
            corpus_entry = {
                "id": f"antiphishing_{idx:04d}",
                "source": "antiphishing.jp",
                "text": text,
                "label": "scam",
                "scam_type": entry["scam_type"],
                "language": "ja",
                "impersonated_brand": entry["brand"],
                "date": entry["date"],
                "content_type": entry["content_type"],
            }
            corpus.append(corpus_entry)
            idx += 1

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for entry in corpus:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Wrote {len(corpus)} corpus entries to {OUTPUT_PATH}")

    # Stats
    by_type = {}
    by_brand = {}
    by_content = {}
    for e in corpus:
        t = e["scam_type"]
        by_type[t] = by_type.get(t, 0) + 1
        b = e["impersonated_brand"]
        by_brand[b] = by_brand.get(b, 0) + 1
        c = e["content_type"]
        by_content[c] = by_content.get(c, 0) + 1

    print("\nBy scam_type:")
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print("\nBy brand (top 15):")
    for k, v in sorted(by_brand.items(), key=lambda x: -x[1])[:15]:
        print(f"  {k}: {v}")

    print("\nBy content_type:")
    for k, v in sorted(by_content.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
