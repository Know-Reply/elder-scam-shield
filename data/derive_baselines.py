"""Derive signal weights and behavioral baselines from the scam corpus.

Analyzes the processed corpus to produce evidence-based statistics:
- Per-signal prevalence across scam patterns
- Pattern-specific risk profiles (when signals appear, at what frequency)
- Derived signal weights (replacing hardcoded values)

Output: data/processed/corpus_baselines.json
This file is loaded by the Behavioral Analyzer at runtime.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / "processed"
OUTPUT = DATA_DIR / "corpus_baselines.json"


# ---------------------------------------------------------------------------
# Signal detection heuristics (keyword-based, applied to corpus text)
# ---------------------------------------------------------------------------

# Per-message signals (PM-*) — detected from single message text
PM_PATTERNS = {
    "PM-1": {  # urgency_language
        "en": r"\b(urgent|immediately|right now|today only|act now|asap|time.?sensitive|within 24|don.?t delay)\b",
        "ja": r"(今すぐ|急いで|本日中|至急|すぐに|直ちに|緊急)",
    },
    "PM-2": {  # secrecy_demand
        "en": r"\b(don.?t tell|keep.?secret|confidential|between us|do not share|private matter)\b",
        "ja": r"(誰にも言わないで|内緒|秘密|他の人には|口外しない)",
    },
    "PM-3": {  # financial_solicitation
        "en": r"\b(send money|transfer|wire|payment|pay|fee|cost|amount|dollar|usd|\$\d|bank account|routing number)\b",
        "ja": r"(振込|送金|万円|お金|支払|口座|費用|料金)",
    },
    "PM-4": {  # authority_claim
        "en": r"\b(police|officer|fbi|irs|government|federal|department of|social security|agent|inspector|official)\b",
        "ja": r"(警察|警視庁|市役所|税務署|年金|役所|官|庁)",
    },
    "PM-5": {  # unusual_payment_method
        "en": r"\b(gift card|itunes|google play|bitcoin|crypto|western union|money ?gram|wire transfer|prepaid)\b",
        "ja": r"(ギフトカード|コンビニ払い|プリペイド|暗号|電子マネー|ビットコイン)",
    },
    "PM-6": {  # legal_threat
        "en": r"\b(legal action|lawsuit|arrest|warrant|prosecute|court|jail|prison|penalty|fine|sue|attorney)\b",
        "ja": r"(法的措置|訴訟|逮捕|裁判|罰|罪|弁護士)",
    },
    "PM-7": {  # credential_solicitation
        "en": r"\b(password|ssn|social security|pin|account number|login|credential|verify your|confirm your identity|card number)\b",
        "ja": r"(暗証番号|パスワード|マイナンバー|口座番号|ログイン|本人確認)",
    },
    "PM-8": {  # prize_notification
        "en": r"\b(congratulations|you.?ve won|winner|lottery|prize|sweepstake|jackpot|selected|lucky)\b",
        "ja": r"(当選|おめでとう|賞|当たり|ラッキー|抽選)",
    },
    "PM-9": {  # refund_lure
        "en": r"\b(refund|reimburse|overpaid|tax return|rebate|claim your|owed money|reimbursement)\b",
        "ja": r"(還付|返金|払い戻し|過払い)",
    },
    "PM-10": {  # emotional_crisis
        "en": r"\b(accident|hospital|emergency|dying|cancer|surgery|injured|critical condition|life.?threatening)\b",
        "ja": r"(事故|入院|病院|緊急|手術|怪我|大変なこと)",
    },
    "PM-11": {  # identity_claim
        "en": r"\b(it.?s me|this is your|i.?m your|grandson|granddaughter|son|daughter|nephew|niece|relative)\b",
        "ja": r"(おれだよ|私です|孫|息子|娘|甥|姪|おばあちゃん)",
    },
    "PM-12": {  # flattery_density
        "en": r"\b(beautiful|handsome|special|amazing|wonderful|dear|my love|sweetheart|darling|beloved|kind.?heart)\b",
        "ja": r"(素敵|素晴らしい|優しい|特別|大切|愛して)",
    },
}


def detect_signals(text: str, language: str = "en") -> list[str]:
    """Detect which PM signals are present in a message."""
    signals = []
    text_lower = text.lower()
    for sig_id, patterns in PM_PATTERNS.items():
        pattern = patterns.get(language, patterns.get("en", ""))
        if pattern and re.search(pattern, text_lower, re.IGNORECASE):
            signals.append(sig_id)
    return signals


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def main():
    # Load all corpus data
    corpus = []
    for fname in ["scam_corpus.jsonl", "jp_scenarios.jsonl", "jp_scenarios_v2.jsonl", "edge_cases.jsonl"]:
        path = DATA_DIR / fname
        if path.exists():
            with open(path) as f:
                for line in f:
                    if line.strip():
                        corpus.append(json.loads(line))

    print(f"Analyzing {len(corpus)} corpus entries...")

    # Separate scam vs safe
    scam_entries = [e for e in corpus if e.get("label") == "scam"]
    safe_entries = [e for e in corpus if e.get("label") == "safe"]
    print(f"  Scam: {len(scam_entries)}, Safe: {len(safe_entries)}")

    # --- 1. Signal prevalence in scam vs safe messages ---
    scam_signals = Counter()
    safe_signals = Counter()
    scam_with_signal = defaultdict(int)
    safe_with_signal = defaultdict(int)

    for entry in scam_entries:
        lang = entry.get("language", "en")
        signals = detect_signals(entry.get("text", ""), lang)
        for s in signals:
            scam_signals[s] += 1
            scam_with_signal[s] += 1

    for entry in safe_entries:
        lang = entry.get("language", "en")
        signals = detect_signals(entry.get("text", ""), lang)
        for s in signals:
            safe_signals[s] += 1
            safe_with_signal[s] += 1

    # --- 2. Compute discriminative power (precision for scam detection) ---
    signal_stats = {}
    for sig_id in sorted(PM_PATTERNS.keys()):
        scam_count = scam_with_signal.get(sig_id, 0)
        safe_count = safe_with_signal.get(sig_id, 0)
        total = scam_count + safe_count

        prevalence_in_scam = scam_count / len(scam_entries) if scam_entries else 0
        prevalence_in_safe = safe_count / len(safe_entries) if safe_entries else 0
        precision = scam_count / total if total > 0 else 0
        lift = (prevalence_in_scam / prevalence_in_safe) if prevalence_in_safe > 0 else float("inf")

        signal_stats[sig_id] = {
            "scam_count": scam_count,
            "safe_count": safe_count,
            "prevalence_in_scam": round(prevalence_in_scam, 4),
            "prevalence_in_safe": round(prevalence_in_safe, 4),
            "precision_for_scam": round(precision, 4),
            "lift_over_safe": round(lift, 2) if lift != float("inf") else "inf",
        }

    # --- 3. Derive weights from precision (normalized to sum to 1.0) ---
    precisions = {k: v["precision_for_scam"] for k, v in signal_stats.items()}
    total_precision = sum(precisions.values())
    derived_weights = {}
    if total_precision > 0:
        for sig_id, prec in precisions.items():
            derived_weights[sig_id] = round(prec / total_precision, 4)
    else:
        # Fallback: equal weights
        n = len(PM_PATTERNS)
        derived_weights = {k: round(1.0 / n, 4) for k in PM_PATTERNS}

    # --- 4. Pattern-specific profiles ---
    pattern_profiles = defaultdict(lambda: {"count": 0, "signals": Counter()})
    for entry in scam_entries:
        scam_type = entry.get("scam_type", "unknown")
        lang = entry.get("language", "en")
        signals = detect_signals(entry.get("text", ""), lang)
        pattern_profiles[scam_type]["count"] += 1
        for s in signals:
            pattern_profiles[scam_type]["signals"][s] += 1

    # Convert to serializable + compute per-pattern signal prevalence
    pattern_data = {}
    for pattern, profile in sorted(pattern_profiles.items()):
        count = profile["count"]
        sig_prevalence = {}
        for sig_id, sig_count in profile["signals"].most_common():
            sig_prevalence[sig_id] = {
                "count": sig_count,
                "prevalence": round(sig_count / count, 4) if count > 0 else 0,
            }
        pattern_data[pattern] = {
            "corpus_count": count,
            "signal_prevalence": sig_prevalence,
        }

    # --- 5. Build output ---
    baselines = {
        "corpus_size": len(corpus),
        "scam_count": len(scam_entries),
        "safe_count": len(safe_entries),
        "signal_stats": signal_stats,
        "derived_weights": derived_weights,
        "pattern_profiles": pattern_data,
        "methodology": (
            "Weights derived from signal precision (P(scam|signal)) normalized "
            "to sum to 1.0. Prevalence = fraction of scam/safe entries containing "
            "the signal. Lift = prevalence_in_scam / prevalence_in_safe. "
            "Pattern profiles show per-pattern signal prevalence."
        ),
    }

    with open(OUTPUT, "w") as f:
        json.dump(baselines, f, indent=2, ensure_ascii=False)

    # --- Print summary ---
    print("\n=== DERIVED SIGNAL WEIGHTS (from corpus) ===")
    print(f"{'Signal':<8} {'Weight':>8} {'Precision':>10} {'Scam%':>8} {'Safe%':>8} {'Lift':>8}")
    print("-" * 54)
    for sig_id in sorted(derived_weights.keys()):
        w = derived_weights[sig_id]
        s = signal_stats[sig_id]
        print(f"{sig_id:<8} {w:>8.4f} {s['precision_for_scam']:>10.4f} "
              f"{s['prevalence_in_scam']:>7.1%} {s['prevalence_in_safe']:>7.1%} "
              f"{s['lift_over_safe']:>8}")

    print(f"\n=== PATTERN PROFILES ({len(pattern_data)} patterns) ===")
    for pattern, data in sorted(pattern_data.items(), key=lambda x: -x[1]["corpus_count"]):
        top_signals = list(data["signal_prevalence"].keys())[:3]
        print(f"  {pattern}: {data['corpus_count']} entries, "
              f"top signals: {', '.join(top_signals) if top_signals else 'none'}")

    print(f"\nSaved to {OUTPUT}")


if __name__ == "__main__":
    main()
