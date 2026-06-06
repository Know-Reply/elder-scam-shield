"""Corpus validation pass — dedup, tag quality, coverage, calibration.

Runs 7 checks and outputs data/CORPUS_VALIDATION_REPORT.md.
"""

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / "processed"
REPORT_PATH = Path(__file__).parent / "CORPUS_VALIDATION_REPORT.md"

CORPUS_FILES = [
    "scam_corpus.jsonl",
    "jp_scenarios.jsonl",
    "edge_cases.jsonl",
    "gov_sources.jsonl",
    "antiphishing_corpus.jsonl",
    "conversation_corpus.jsonl",
]

# ── Signal detection (same as derive_baselines.py) ──────────────────────

PM_PATTERNS = {
    "PM-1": {"en": r"\b(urgent|immediately|right now|today only|act now|asap|within 24|don.?t delay)\b", "ja": r"(今すぐ|急いで|本日中|至急|すぐに|直ちに|緊急)"},
    "PM-2": {"en": r"\b(don.?t tell|keep.?secret|confidential|between us|do not share|private matter)\b", "ja": r"(誰にも言わないで|内緒|秘密|他の人には|口外しない)"},
    "PM-3": {"en": r"\b(send money|transfer|wire|payment|pay|fee|cost|amount|dollar|usd|\$\d|bank account|routing number)\b", "ja": r"(振込|送金|万円|お金|支払|口座|費用|料金)"},
    "PM-4": {"en": r"\b(police|officer|fbi|irs|government|federal|department of|social security|agent|inspector|official)\b", "ja": r"(警察|警視庁|市役所|税務署|年金|役所|官|庁)"},
    "PM-5": {"en": r"\b(gift card|itunes|google play|bitcoin|crypto|western union|money ?gram|wire transfer|prepaid)\b", "ja": r"(ギフトカード|コンビニ払い|プリペイド|暗号|電子マネー)"},
    "PM-6": {"en": r"\b(legal action|lawsuit|arrest|warrant|prosecute|court|jail|prison|penalty|fine|sue|attorney)\b", "ja": r"(法的措置|訴訟|逮捕|裁判|罰|罪|弁護士)"},
    "PM-7": {"en": r"\b(password|ssn|social security|pin|account number|login|credential|verify your|confirm your identity|card number)\b", "ja": r"(暗証番号|パスワード|マイナンバー|口座番号|ログイン|本人確認)"},
    "PM-8": {"en": r"\b(congratulations|you.?ve won|winner|lottery|prize|sweepstake|jackpot|selected|lucky)\b", "ja": r"(当選|おめでとう|賞|当たり|抽選)"},
    "PM-9": {"en": r"\b(refund|reimburse|overpaid|tax return|rebate|claim your|owed money|reimbursement)\b", "ja": r"(還付|返金|払い戻し|過払い)"},
    "PM-10": {"en": r"\b(accident|hospital|emergency|dying|cancer|surgery|injured|critical condition)\b", "ja": r"(事故|入院|病院|緊急|手術|怪我|大変なこと)"},
    "PM-11": {"en": r"\b(it.?s me|this is your|i.?m your|grandson|granddaughter|son|daughter|nephew|niece)\b", "ja": r"(おれだよ|私です|孫|息子|娘|甥|姪|おばあちゃん)"},
    "PM-12": {"en": r"\b(beautiful|handsome|special|amazing|wonderful|dear|my love|sweetheart|darling|beloved)\b", "ja": r"(素敵|素晴らしい|優しい|特別|大切|愛して)"},
    "PM-13": {"en": r"\b(spf|dkim|dmarc|authentication.fail|spoofed)\b", "ja": r"(認証失敗|なりすまし送信)"},
}

# Longitudinal signals — detected from multi-turn text
LG_PATTERNS = {
    "LG-1": {"en": r"(contradiction|inconsisten|changed.+story|previously.+said|before.+now)", "ja": r"(矛盾|以前|前は|変わった)"},
    "LG-2": {"en": r"(contact.+mismatch|not.+in.+contacts|don.?t.+know|no.+record)", "ja": r"(連絡先|知らない|登録されていない)"},
    "LG-3": {"en": r"(frequency|daily|every day|keeps.+contacting|multiple.+messages)", "ja": r"(毎日|頻繁|何度も)"},
    "LG-4": {"en": r"(emotional|intimate|love|feelings|special.+connection|closer)", "ja": r"(気持ち|特別|親しく|感情|つながり)"},
    "LG-5": {"en": r"(first.+mention.+money|finally.+ask|after.+trust|now.+need.+money)", "ja": r"(お金の話|初めて|やっと|ようやく)"},
    "LG-6": {"en": r"(don.?t tell|secret|just between|isolat|alone|private)", "ja": r"(誰にも|秘密|二人だけ|内緒)"},
    "LG-7": {"en": r"(style.+change|formality|tone.+shift|different.+writing)", "ja": r"(文体|口調|書き方|変わった)"},
    "LG-8": {"en": r"(crisis|emergency|accident|hospital|after.+trust|sudden)", "ja": r"(大変|緊急|事故|入院|突然)"},
    "LG-9": {"en": r"(fast|rapid|quickly|too.+soon|already|right away)", "ja": r"(すぐに|早い|もう|急に)"},
    "LG-10": {"en": r"(small.+favor|little.+help|just.+this|start.+small|escalat)", "ja": r"(少しだけ|ちょっと|お願い|最初は)"},
}

OB_PATTERNS = {
    "OB-1": {"en": r"(my.+address|my.+name|personal.+info|identity|ssn|social.+security)", "ja": r"(住所|名前|個人情報|マイナンバー)"},
    "OB-2": {"en": r"(bank.+account|card.+number|pin|routing|sort.+code)", "ja": r"(口座番号|カード番号|暗証番号)"},
    "OB-3": {"en": r"(transfer|wire|send.+money|payment|pay.+you|remit)", "ja": r"(振込|送金|支払|送る)"},
    "OB-4": {"en": r"(reply|respond|answer|flagged|suspicious|risk)", "ja": r"(返信|応答|リスク|不審)"},
    "OB-5": {"en": r"(understood|will do|okay|i.?ll.+send|right away|immediately)", "ja": r"(わかりました|了解|すぐに|送ります)"},
}

CM_PATTERNS = {
    "CM-1": {"en": r"(spending|transaction|purchase|bought|paid)", "ja": r"(支出|取引|購入|買った)"},
    "CM-2": {"en": r"(amount.+match|exact.+amount|same.+sum)", "ja": r"(金額.*一致|同じ.*額)"},
    "CM-3": {"en": r"(new.+payee|first.+time|never.+before|unknown.+recipient)", "ja": r"(初めて|新しい.*宛先|知らない.*相手)"},
    "CM-4": {"en": r"(urgency.*amount|large.*urgent|compound.*risk)", "ja": r"(緊急.*金額|大きな.*急ぎ)"},
}

ALL_SIGNALS = {}
ALL_SIGNALS.update(PM_PATTERNS)
ALL_SIGNALS.update(LG_PATTERNS)
ALL_SIGNALS.update(OB_PATTERNS)
ALL_SIGNALS.update(CM_PATTERNS)


def detect_signals(text: str, language: str = "en") -> list[str]:
    signals = []
    text_lower = text.lower()
    for sig_id, patterns in ALL_SIGNALS.items():
        pattern = patterns.get(language, patterns.get("en", ""))
        if pattern and re.search(pattern, text_lower, re.IGNORECASE):
            signals.append(sig_id)
    return signals


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def load_corpus() -> list[dict]:
    corpus = []
    for fname in CORPUS_FILES:
        path = DATA_DIR / fname
        if path.exists():
            with open(path) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        entry["_source_file"] = fname
                        corpus.append(entry)
    return corpus


# ── Channel detection ───────────────────────────────────────────────────

def detect_channel(entry: dict) -> str:
    text = entry.get("text", "").lower()
    ct = entry.get("content_type", "")
    source = entry.get("source", "")

    if "multi_turn_conversation" in ct:
        if "caller:" in text or "receiver:" in text or "innocent:" in text or "suspect:" in text:
            return "phone"
    if "sms" in text or "ショートメッセージ" in text or "SMS" in entry.get("text", ""):
        return "sms"
    if "subject_line" in ct or "email" in source.lower() or "@" in text:
        return "email"
    if "dialogue" in ct:
        return "phone"
    if source in ("npa.go.jp/sos47",):
        return "phone"
    if source in ("antiphishing.jp",):
        return "email"
    if any(kw in text for kw in ["subject:", "from:", "reply-to:", "dear sir", "dear friend"]):
        return "email"
    return "unknown"


def main():
    random.seed(42)
    corpus = load_corpus()
    report = []
    r = report.append

    r("# Corpus Validation Report")
    r(f"\nGenerated from {len(corpus)} entries across {len(CORPUS_FILES)} source files.\n")
    r("---\n")

    # ── 1. Dedup ────────────────────────────────────────────────────────
    r("## 1. Deduplication\n")
    hashes = {}
    dupes = []
    for i, entry in enumerate(corpus):
        h = text_hash(entry.get("text", ""))
        if h in hashes:
            dupes.append((i, hashes[h], entry.get("_source_file"), entry.get("id", "?")))
        else:
            hashes[h] = i

    r(f"- Total entries: {len(corpus)}")
    r(f"- Unique texts: {len(hashes)}")
    r(f"- Exact duplicates found: {len(dupes)}")
    if dupes:
        dupe_sources = Counter(d[2] for d in dupes)
        r(f"- Duplicates by source: {dict(dupe_sources)}")
        r(f"- Sample duplicates (first 5):")
        for idx, orig, src, eid in dupes[:5]:
            r(f"  - `{eid}` from `{src}` duplicates entry #{orig}")
    r("")

    # Deduplicated corpus for remaining checks
    seen = set()
    deduped = []
    for entry in corpus:
        h = text_hash(entry.get("text", ""))
        if h not in seen:
            seen.add(h)
            deduped.append(entry)

    r(f"**Deduplicated corpus: {len(deduped)} entries**\n")

    # ── 2. Tag quality audit ────────────────────────────────────────────
    r("## 2. Tag Quality Audit\n")
    r("Spot-check of 50 random entries per source for NPA pattern tag accuracy.\n")

    sources = defaultdict(list)
    for entry in deduped:
        sources[entry.get("source", "unknown")].append(entry)

    for source_name in sorted(sources.keys()):
        entries = sources[source_name]
        sample = random.sample(entries, min(50, len(entries)))
        correct = 0
        questionable = 0
        for entry in sample:
            scam_type = entry.get("scam_type")
            label = entry.get("label", "")
            text = entry.get("text", "")[:200].lower()

            if label == "safe" and scam_type is None:
                correct += 1
                continue

            if scam_type is None and label == "scam":
                questionable += 1
                continue

            # Heuristic check: does the text match expected patterns for the tag?
            tag_ok = True
            if scam_type == "fake-bank" and not any(kw in text for kw in ["bank", "card", "account", "verify", "銀行", "カード", "口座", "認証"]):
                tag_ok = False
            elif scam_type == "gov-impersonation" and not any(kw in text for kw in ["government", "irs", "tax", "official", "federal", "social security", "国税", "年金", "役所", "税", "マイナ", "厚生"]):
                tag_ok = False
            elif scam_type == "lottery-prize" and not any(kw in text for kw in ["won", "lottery", "prize", "winner", "congratulations", "当選", "賞", "宝くじ"]):
                tag_ok = False
            elif scam_type == "refund-scam" and not any(kw in text for kw in ["refund", "reimburse", "overpaid", "tax return", "還付", "返金", "払い戻し"]):
                tag_ok = False
            elif scam_type == "romance-scam" and not any(kw in text for kw in ["love", "heart", "beautiful", "relationship", "darling", "romance", "愛", "恋", "交際", "出会い", "素敵"]):
                tag_ok = False

            if tag_ok:
                correct += 1
            else:
                questionable += 1

        total = len(sample)
        acc = correct / total * 100 if total > 0 else 0
        r(f"| `{source_name}` | {total} sampled | {correct} correct | {questionable} questionable | **{acc:.0f}% accuracy** |")

    r("")

    # ── 3. Channel tagging ──────────────────────────────────────────────
    r("## 3. Channel Distribution\n")
    channels = Counter()
    for entry in deduped:
        ch = detect_channel(entry)
        entry["_channel"] = ch
        channels[ch] += 1

    r("| Channel | Count | % |")
    r("|---|---|---|")
    for ch, count in channels.most_common():
        r(f"| {ch} | {count:,} | {count/len(deduped)*100:.1f}% |")
    r("")

    # ── 4. Signal coverage matrix ───────────────────────────────────────
    r("## 4. Signal Coverage Matrix\n")
    r("Entries containing each signal (keyword-based detection).\n")

    signal_counts = Counter()
    for entry in deduped:
        lang = entry.get("language", "en")
        signals = detect_signals(entry.get("text", ""), lang)
        for s in signals:
            signal_counts[s] += 1

    undertrained = []
    r("| Signal | Count | Status |")
    r("|---|---|---|")
    for sig_id in sorted(ALL_SIGNALS.keys()):
        count = signal_counts.get(sig_id, 0)
        status = "OK" if count >= 10 else f"**UNDERTRAINED ({count})**"
        if count < 10:
            undertrained.append(sig_id)
        r(f"| {sig_id} | {count:,} | {status} |")

    r(f"\n**Undertrained signals (<10 examples): {len(undertrained)}** — {', '.join(undertrained) if undertrained else 'none'}\n")

    # ── 5. Pattern coverage report ──────────────────────────────────────
    r("## 5. NPA Pattern Coverage\n")
    pattern_counts = Counter()
    for entry in deduped:
        st = entry.get("scam_type")
        if st:
            pattern_counts[st] += 1

    undercovered = []
    r("| Pattern | Count | Status |")
    r("|---|---|---|")
    for pattern, count in pattern_counts.most_common():
        status = "OK" if count >= 50 else f"**UNDERCOVERED ({count})**"
        if count < 50:
            undercovered.append(pattern)
        r(f"| {pattern} | {count:,} | {status} |")

    r(f"\n**Undercovered patterns (<50 examples): {len(undercovered)}** — {', '.join(undercovered) if undercovered else 'none'}\n")

    # ── 6. Signal weight recalibration ──────────────────────────────────
    r("## 6. Signal Weight Recalibration\n")

    scam_entries = [e for e in deduped if e.get("label") == "scam"]
    safe_entries = [e for e in deduped if e.get("label") == "safe"]

    # Load old weights
    baselines_path = DATA_DIR / "corpus_baselines.json"
    old_weights = {}
    if baselines_path.exists():
        with open(baselines_path) as f:
            old_data = json.load(f)
            old_weights = old_data.get("derived_weights", {})

    # Compute new weights
    scam_sig = Counter()
    safe_sig = Counter()
    for entry in scam_entries:
        for s in detect_signals(entry.get("text", ""), entry.get("language", "en")):
            scam_sig[s] += 1
    for entry in safe_entries:
        for s in detect_signals(entry.get("text", ""), entry.get("language", "en")):
            safe_sig[s] += 1

    new_precisions = {}
    for sig_id in sorted(PM_PATTERNS.keys()):
        sc = scam_sig.get(sig_id, 0)
        sa = safe_sig.get(sig_id, 0)
        total = sc + sa
        new_precisions[sig_id] = sc / total if total > 0 else 0

    total_prec = sum(new_precisions.values())
    new_weights = {k: round(v / total_prec, 4) if total_prec > 0 else 0 for k, v in new_precisions.items()}

    r("| Signal | Old Weight | New Weight | Delta |")
    r("|---|---|---|---|")
    for sig_id in sorted(new_weights.keys()):
        old = old_weights.get(sig_id, 0)
        new = new_weights[sig_id]
        delta = new - old
        flag = " ⚠️" if abs(delta) > 0.02 else ""
        r(f"| {sig_id} | {old:.4f} | {new:.4f} | {delta:+.4f}{flag} |")
    r("")

    # ── 7. Legitimate message baseline ──────────────────────────────────
    r("## 7. Legitimate Message Baseline\n")
    labels = Counter(e.get("label", "unknown") for e in deduped)
    total = len(deduped)
    safe_pct = labels.get("safe", 0) / total * 100

    r(f"| Label | Count | % |")
    r("|---|---|---|")
    for label, count in labels.most_common():
        r(f"| {label} | {count:,} | {count/total*100:.1f}% |")

    r("")
    if safe_pct < 20:
        r(f"**⚠️ GAP: Only {safe_pct:.1f}% of corpus is confirmed legitimate. Need ≥20% for reliable false-positive measurement.**\n")
    else:
        r(f"**✓ Legitimate baseline adequate: {safe_pct:.1f}% ({labels.get('safe', 0):,} entries)**\n")

    # ── Summary ─────────────────────────────────────────────────────────
    r("---\n")
    r("## Summary\n")
    r(f"- **Corpus size:** {len(deduped):,} (after dedup from {len(corpus):,})")
    r(f"- **Duplicates removed:** {len(dupes)}")
    r(f"- **Undertrained signals:** {len(undertrained)} ({', '.join(undertrained) if undertrained else 'none'})")
    r(f"- **Undercovered patterns:** {len(undercovered)} ({', '.join(undercovered) if undercovered else 'none'})")
    r(f"- **Legitimate baseline:** {safe_pct:.1f}%")
    r(f"- **Channels:** {dict(channels)}")

    # Write report
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(report))
    print(f"Report written to {REPORT_PATH}")
    print(f"\nQuick summary:")
    print(f"  Corpus: {len(corpus)} → {len(deduped)} after dedup ({len(dupes)} removed)")
    print(f"  Undertrained signals: {undertrained}")
    print(f"  Undercovered patterns: {undercovered}")
    print(f"  Legitimate: {safe_pct:.1f}%")


if __name__ == "__main__":
    main()
