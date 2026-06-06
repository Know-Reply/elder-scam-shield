#!/usr/bin/env python3
"""
Scrape phishing case data from antiphishing.jp (Council of Anti-Phishing Japan).

This script:
1. Fetches the database index page at https://www.antiphishing.jp/news/database/
2. Extracts case URLs matching /news/alert/xxx.html
3. For each case page, extracts subject lines, phishing URLs, brand info, and dates
4. Saves raw data to data/raw/antiphishing_cases.jsonl

Usage:
    python data/scrape_antiphishing.py [--limit N]

Rate-limited to 1 request per second with proper User-Agent.
"""

import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.antiphishing.jp"
DATABASE_URL = f"{BASE_URL}/news/database/"
OUTPUT_PATH = Path(__file__).parent / "raw" / "antiphishing_cases.jsonl"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Known brand patterns for classification
BRAND_PATTERNS = {
    # Banks
    "三菱UFJ": "三菱UFJ銀行",
    "みずほ": "みずほ銀行",
    "ゆうちょ": "ゆうちょ銀行",
    "りそな": "りそな銀行",
    "auじぶん銀行": "auじぶん銀行",
    "三井住友信託": "三井住友信託銀行",
    "住信SBI": "住信SBIネット銀行",
    "JAバンク": "JAバンク",
    "農業協同組合": "JAバンク",
    "ろうきん": "ろうきん",
    "GMOあおぞら": "GMOあおぞらネット銀行",
    "金融機関": "金融機関（複数）",
    # Securities
    "楽天証券": "楽天証券",
    "SBI証券": "SBI証券",
    "SBIネオトレード": "SBIネオトレード証券",
    "野村證券": "野村證券",
    "松井証券": "松井証券",
    "マネックス": "マネックス証券",
    "大和証券": "大和証券",
    "みずほ証券": "みずほ証券",
    "SMBC日興": "SMBC日興証券",
    "三菱UFJモルガン": "三菱UFJモルガン・スタンレー証券",
    "岩井コスモ": "岩井コスモ証券",
    "GMOクリック": "GMOクリック証券",
    # Government / Tax
    "国税庁": "国税庁",
    "税務署": "国税庁",
    "年金": "日本年金機構",
    "国民健康保険": "国民健康保険",
    "住民税": "住民税",
    "マイナポータル": "マイナポータル",
    "マイナポイント": "マイナポイント事務局",
    "国勢調査": "国勢調査",
    # E-commerce / Services
    "Amazon": "Amazon",
    "楽天": "楽天",
    "イオン": "イオンカード",
    "ビックカメラ": "ビックカメラ",
    "ローソン": "ローソンチケット",
    # Payment
    "PayPay": "PayPay",
    "LINE Pay": "LINE Pay",
    "LINE": "LINE",
    "au PAY": "au PAY",
    "Kyash": "Kyash",
    # Telecom
    "ソフトバンク": "ソフトバンク",
    "Softbank": "ソフトバンク",
    "NTT": "NTT",
    "au": "au",
    # Delivery / Transport
    "日本郵便": "日本郵便",
    "日本郵政": "日本郵便",
    "ヤマト": "ヤマト運輸",
    "佐川": "佐川急便",
    "ETC": "ETC利用照会サービス",
    "えきねっと": "えきねっと",
    "JR": "JR",
    "ANA": "ANA",
    # Insurance
    "第一生命": "第一生命",
    "日本生命": "日本生命",
    "保険会社": "保険会社（複数）",
    # Credit cards
    "JCB": "JCB",
    "Mastercard": "Mastercard",
    "セディナ": "セディナカード",
    # Other
    "OpenAI": "OpenAI/ChatGPT",
    "ChatGPT": "OpenAI/ChatGPT",
    "Apple": "Apple",
    "宝くじ": "宝くじ公式サイト",
    "東京電力": "東京電力",
    "東京ガス": "東京ガス",
    "東京都水道局": "東京都水道局",
    "So-net": "So-net",
    "アコム": "アコム",
    "プロミス": "プロミス",
    "アイフル": "アイフル",
    "レイク": "レイク",
    "ORIX": "ORIX MONEY",
    "WESTER": "WESTER",
}


def fetch_page(url: str, session: requests.Session) -> BeautifulSoup | None:
    """Fetch a page and return parsed BeautifulSoup, or None on error."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}")
        return None


def extract_case_urls(soup: BeautifulSoup) -> list[str]:
    """Extract all case URLs from the database index page.

    Catches both /news/alert/ (active cases) and /news/database/ (archived cases).
    """
    urls = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Match both active alerts and archived database entries
        is_case = (
            ("/news/alert/" in href or "/news/database/" in href)
            and href.endswith(".html")
            and href != "/news/database/"  # skip the index itself
        )
        if is_case:
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = BASE_URL + href
            else:
                full_url = BASE_URL + "/" + href
            if full_url not in urls:
                urls.append(full_url)
    return urls


def extract_brand_from_title(title: str) -> str:
    """Identify the impersonated brand from the alert title."""
    for pattern, brand in BRAND_PATTERNS.items():
        if pattern in title:
            return brand
    # Fallback: extract from 「Xをかたる」 or 「Xをよそおう」 pattern
    m = re.search(r"(.+?)(?:をかたる|をよそおう|からの|の納付|の支払)", title)
    if m:
        return m.group(1).strip()
    return "unknown"


def extract_date_from_url(url: str) -> str:
    """Extract date from URL like /news/alert/xxx_20260518.html → 2026-05-18."""
    m = re.search(r"_(\d{4})(\d{2})(\d{2})\.html", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def extract_case_data(soup: BeautifulSoup, url: str) -> dict:
    """Extract phishing case data from an individual alert page."""
    title = ""
    title_tag = soup.find("h1") or soup.find("h2")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Extract all text from the page body
    body = soup.find("div", class_="contents") or soup.find("article") or soup.find("main") or soup.body
    full_text = body.get_text("\n", strip=True) if body else ""

    # Extract subject lines (usually in 「」brackets or after 件名: patterns)
    subject_lines = []
    # Pattern 1: text in Japanese brackets
    bracket_matches = re.findall(r"[「『](.*?)[」』]", full_text)
    for m in bracket_matches:
        # Filter to likely subject lines (contain keywords typical of phishing subjects)
        if any(kw in m for kw in [
            "重要", "緊急", "至急", "確認", "お知らせ", "通知", "停止",
            "ロック", "セキュリティ", "未払", "請求", "督促", "更新",
            "キャンペーン", "ポイント", "プレゼント", "当選", "失効",
            "アカウント", "カード", "認証", "パスワード", "ログイン",
            "支払", "料金", "納付", "差押", "保険", "年金", "税",
        ]):
            if m not in subject_lines and len(m) > 5:
                subject_lines.append(m)

    # Extract phishing URLs
    phishing_urls = []
    url_matches = re.findall(r"https?://[^\s<>\"'）」\]]+", full_text)
    for u in url_matches:
        # Skip legitimate antiphishing.jp URLs
        if "antiphishing.jp" in u:
            continue
        # Keep URLs that look like phishing (contain redaction markers or suspicious TLDs)
        if u not in phishing_urls:
            phishing_urls.append(u)

    date = extract_date_from_url(url)
    brand = extract_brand_from_title(title)

    return {
        "url": url,
        "title": title,
        "date": date,
        "impersonated_brand": brand,
        "subject_lines": subject_lines,
        "phishing_urls": phishing_urls,
        "full_text_excerpt": full_text[:2000],  # First 2000 chars for context
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape antiphishing.jp case data")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max number of case pages to fetch (default: 100)")
    args = parser.parse_args()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    print(f"Fetching index page: {DATABASE_URL}")
    index_soup = fetch_page(DATABASE_URL, session)
    if not index_soup:
        print("Failed to fetch index page. Exiting.")
        return

    case_urls = extract_case_urls(index_soup)
    print(f"Found {len(case_urls)} case URLs")

    # Check for pagination — the site may have multiple pages
    # Look for pagination links
    page_links = []
    for a_tag in index_soup.find_all("a", href=True):
        href = a_tag["href"]
        if "database" in href and ("page" in href or re.search(r"/\d+/?$", href)):
            if href.startswith("/"):
                href = BASE_URL + href
            if href not in page_links and href != DATABASE_URL:
                page_links.append(href)

    for page_url in page_links[:5]:  # Limit pagination
        print(f"Fetching paginated index: {page_url}")
        time.sleep(1)
        page_soup = fetch_page(page_url, session)
        if page_soup:
            more_urls = extract_case_urls(page_soup)
            for u in more_urls:
                if u not in case_urls:
                    case_urls.append(u)
            print(f"  Total case URLs now: {len(case_urls)}")

    # Limit to requested number
    case_urls = case_urls[:args.limit]
    print(f"Will fetch {len(case_urls)} case pages (limit={args.limit})")

    cases = []
    for i, case_url in enumerate(case_urls):
        print(f"  [{i+1}/{len(case_urls)}] {case_url}")
        time.sleep(1)  # Rate limiting
        soup = fetch_page(case_url, session)
        if soup:
            data = extract_case_data(soup, case_url)
            cases.append(data)
            subj_count = len(data["subject_lines"])
            url_count = len(data["phishing_urls"])
            print(f"    → {data['impersonated_brand']}: {subj_count} subjects, {url_count} URLs")

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    print(f"\nDone. Wrote {len(cases)} cases to {OUTPUT_PATH}")

    # Summary stats
    brands = {}
    for c in cases:
        b = c["impersonated_brand"]
        brands[b] = brands.get(b, 0) + 1
    print("\nBrand distribution:")
    for b, count in sorted(brands.items(), key=lambda x: -x[1]):
        print(f"  {b}: {count}")


if __name__ == "__main__":
    main()
