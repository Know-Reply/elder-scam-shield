#!/usr/bin/env python3
"""Re-classify generic 'phishing' entries into NPA tokushu sagi pattern categories."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "processed" / "scam_corpus.jsonl"

# Priority-ordered patterns (most specific first).
# Each tuple: (scam_type_slug, compiled_regex)
PATTERNS = [
    (
        "advance-fee-419",
        re.compile(
            r"nigerian|prince|minister|inheritance|million\s*(?:usd|dollars?|pounds?)"
            r"|transfer\s*funds|beneficiary|next\s*of\s*kin|dying\s*wish"
            r"|confidential\s*business|diplomatic|consignment",
            re.IGNORECASE,
        ),
    ),
    (
        "romance-scam",
        re.compile(
            r"dear\s*friend|lonely|looking\s*for\s*love|beautiful\s*woman"
            r"|handsome\s*man|relationship|my\s*heart|soul\s*mate"
            r"|i\s*love\s*you|widow|inheritance\s*from\s*late\s*husband",
            re.IGNORECASE,
        ),
    ),
    (
        "impersonation",
        re.compile(
            r"i'?m\s*your\s*(?:son|daughter|grandson|granddaughter|nephew|niece|cousin|brother|sister)"
            r"|it'?s\s*me|urgent\s*help|emergency|accident|arrested|hospital|don'?t\s*tell",
            re.IGNORECASE,
        ),
    ),
    (
        "fake-police",
        re.compile(
            r"police|officer|warrant|arrest|investigation|criminal|seized|evidence",
            re.IGNORECASE,
        ),
    ),
    (
        "lottery-prize",
        re.compile(
            r"congratulations\s*you\s*won|lottery|prize|winner|sweepstakes"
            r"|claim\s*your\s*prize|million\s*dollars",
            re.IGNORECASE,
        ),
    ),
    (
        "refund-scam",
        re.compile(
            r"refund|tax\s*return|overpayment|reimbursement|claim\s*your|rebate",
            re.IGNORECASE,
        ),
    ),
    (
        "gov-impersonation",
        re.compile(
            r"\birs\b|tax|government|social\s*security|medicare|official\s*notice"
            r"|department\s*of|federal",
            re.IGNORECASE,
        ),
    ),
    (
        "fictitious-billing",
        re.compile(
            r"invoice|unpaid|billing|subscription|account\s*suspended|pay\s*now"
            r"|overdue|balance\s*due|collection\s*agency|final\s*notice",
            re.IGNORECASE,
        ),
    ),
    (
        "fake-bank",
        re.compile(
            r"bank|account\s*verification|card\s*expired|update\s*your\s*information"
            r"|verify\s*your\s*identity|security\s*alert"
            r"|suspicious\s*activity\s*on\s*your\s*account",
            re.IGNORECASE,
        ),
    ),
    (
        "credential-phishing",
        re.compile(
            r"password|username|click\s*here\s*to\s*verify|confirm\s*your\s*account"
            r"|reset\s*your|login\s*credentials|\bssn\b",
            re.IGNORECASE,
        ),
    ),
]


def classify(text: str) -> str:
    """Return the most specific NPA pattern slug, or 'generic-scam'."""
    for slug, pattern in PATTERNS:
        if pattern.search(text):
            return slug
    return "generic-scam"


def main():
    if not CORPUS_PATH.exists():
        print(f"ERROR: corpus not found at {CORPUS_PATH}", file=sys.stderr)
        sys.exit(1)

    records = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    retagged = Counter()
    unchanged = 0

    for rec in records:
        if rec.get("scam_type") == "phishing":
            new_type = classify(rec.get("text", ""))
            rec["scam_type"] = new_type
            retagged[new_type] += 1
        else:
            unchanged += 1

    # Write back
    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Re-tagged {sum(retagged.values())} phishing entries:")
    print("-" * 45)
    for slug, count in retagged.most_common():
        print(f"  {slug:<25s} {count:>5d}")
    print("-" * 45)
    print(f"  Unchanged entries:       {unchanged:>5d}")
    print(f"  Total records:           {len(records):>5d}")


if __name__ == "__main__":
    main()
