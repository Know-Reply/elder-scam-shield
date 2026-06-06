"""Process antiphishing.jp scraped data — v2 using URL-based brand extraction.

The site renders case content via JavaScript, so requests/BeautifulSoup
misses the article body. But we have 730 URLs with brand slugs embedded
in the URL pattern (e.g., /alert/amazon_20240101.html → Amazon).

We extract brands from URLs, map to NPA scam types, and use whatever
subject lines the parser did find.
"""

import json
import re
from collections import Counter
from pathlib import Path

RAW_PATH = Path(__file__).parent / "raw" / "antiphishing_cases.jsonl"
OUTPUT = Path(__file__).parent / "processed" / "antiphishing_corpus.jsonl"

# URL slug → (display brand, NPA scam_type)
BRAND_MAP = {
    # Banks
    "smbc": ("三井住友銀行", "fake-bank"),
    "smbccard": ("三井住友カード", "fake-bank"),
    "mufg": ("三菱UFJ銀行", "fake-bank"),
    "mufgcard": ("三菱UFJニコス", "fake-bank"),
    "mizuho": ("みずほ銀行", "fake-bank"),
    "mizuhosc": ("みずほ証券", "fake-bank"),
    "japannetbank": ("PayPay銀行", "fake-bank"),
    "aeoncard": ("イオンカード", "fake-bank"),
    "eposcard": ("エポスカード", "fake-bank"),
    "saison": ("セゾンカード", "fake-bank"),
    "omc_plus": ("OMCカード", "fake-bank"),
    "jcb": ("JCB", "fake-bank"),
    "myjcb": ("MyJCB", "fake-bank"),
    "mastercard": ("Mastercard", "fake-bank"),
    "visa": ("VISA", "fake-bank"),
    "orico": ("オリコカード", "fake-bank"),
    "life_card": ("ライフカード", "fake-bank"),
    "viewsnet": ("ビューカード", "fake-bank"),
    "cedyna": ("セディナ", "fake-bank"),
    "citibank": ("シティバンク", "fake-bank"),
    "chasebank_online": ("Chase Bank", "fake-bank"),
    # Securities
    "rakutensec": ("楽天証券", "fake-bank"),
    "sbineotrade": ("SBIネオトレード証券", "fake-bank"),
    # Government
    "nta": ("国税庁", "gov-impersonation"),
    "nenkin": ("日本年金機構", "gov-impersonation"),
    "kokumin": ("国民健康保険", "gov-impersonation"),
    "mhlw": ("厚生労働省", "gov-impersonation"),
    "rtax": ("住民税", "gov-impersonation"),
    "mynumber": ("マイナンバー", "gov-impersonation"),
    "mynapoint": ("マイナポイント", "gov-impersonation"),
    "soumu": ("総務省", "gov-impersonation"),
    # E-commerce
    "amazon": ("Amazon", "fictitious-billing"),
    "rakuten": ("楽天", "fictitious-billing"),
    "mercari": ("メルカリ", "fictitious-billing"),
    "apple": ("Apple", "credential-phishing"),
    "microsoft": ("Microsoft", "credential-phishing"),
    # Payment
    "paypay": ("PayPay", "credential-phishing"),
    "line": ("LINE", "credential-phishing"),
    "linepay": ("LINE Pay", "credential-phishing"),
    "aupay": ("au PAY", "credential-phishing"),
    # Telecom
    "softbank": ("ソフトバンク", "fictitious-billing"),
    "nttdocomo": ("NTTドコモ", "fictitious-billing"),
    "au": ("au", "fictitious-billing"),
    "ocn": ("OCN", "credential-phishing"),
    # Delivery
    "japanpost": ("日本郵便", "fictitious-billing"),
    "yamato": ("ヤマト運輸", "fictitious-billing"),
    "sagawa": ("佐川急便", "fictitious-billing"),
    "ekinet": ("えきねっと", "fictitious-billing"),
    "etc": ("ETC利用照会", "fictitious-billing"),
    # Web services
    "yahoo_japan": ("Yahoo! JAPAN", "credential-phishing"),
    "paypal": ("PayPal", "credential-phishing"),
    "netflix": ("Netflix", "fictitious-billing"),
    # Other
    "daiichilife": ("第一生命", "fictitious-billing"),
    "seihoPayPay": ("生命保険PayPay", "fictitious-billing"),
    "lawsonticket": ("ローソンチケット", "fictitious-billing"),
    "aeon": ("イオン", "fictitious-billing"),
}


def extract_brand_from_url(url: str) -> tuple[str, str, str]:
    """Extract (slug, brand_name, scam_type) from URL."""
    m = re.search(r"/(?:alert|database)/([a-zA-Z_]+?)_?\d{4,8}\.html", url)
    if not m:
        m = re.search(r"/(?:alert|database)/([a-zA-Z_]+?)\.html", url)
    if m:
        slug = m.group(1)
        if slug in BRAND_MAP:
            return slug, BRAND_MAP[slug][0], BRAND_MAP[slug][1]
        return slug, slug, "credential-phishing"  # default for unknown brands
    return "unknown", "unknown", "credential-phishing"


def main():
    with open(RAW_PATH) as f:
        cases = [json.loads(l) for l in f if l.strip()]
    print(f"Loaded {len(cases)} raw cases")

    entries = []
    for i, case in enumerate(cases):
        url = case.get("url", "")
        slug, brand, scam_type = extract_brand_from_url(url)
        date = case.get("date", "")
        subject_lines = case.get("subject_lines", [])
        full_text = case.get("full_text_excerpt", "").strip()

        # Create entries from subject lines (best signal — actual phishing text)
        if subject_lines:
            for j, subj in enumerate(subject_lines):
                entries.append({
                    "id": f"antiphish_{i:04d}_s{j}",
                    "source": "antiphishing.jp",
                    "text": subj,
                    "label": "scam",
                    "scam_type": scam_type,
                    "language": "ja",
                    "impersonated_brand": brand,
                    "date": date,
                    "content_type": "subject_line",
                    "source_url": url,
                })

        # Also create a combined entry with brand + date as context
        # even if no subject lines were extracted
        desc = f"{brand}をかたるフィッシング ({date})"
        entries.append({
            "id": f"antiphish_{i:04d}_case",
            "source": "antiphishing.jp",
            "text": desc,
            "label": "scam",
            "scam_type": scam_type,
            "language": "ja",
            "impersonated_brand": brand,
            "date": date,
            "content_type": "case_record",
            "source_url": url,
        })

    # Write
    with open(OUTPUT, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Wrote {len(entries)} corpus entries to {OUTPUT}")

    # Stats
    types = Counter(e["scam_type"] for e in entries)
    print(f"\nBy scam_type:")
    for k, v in types.most_common():
        print(f"  {k}: {v}")

    brands = Counter(e["impersonated_brand"] for e in entries)
    print(f"\nTop 20 brands:")
    for k, v in brands.most_common(20):
        print(f"  {k}: {v}")

    ct = Counter(e["content_type"] for e in entries)
    print(f"\nBy content_type: {dict(ct)}")


if __name__ == "__main__":
    main()
