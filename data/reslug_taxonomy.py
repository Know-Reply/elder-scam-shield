"""Reslug entire corpus to 8-category attack-mechanics taxonomy.

Categories:
  1. impersonation      — pretend to be trusted person (family, police, colleague)
  2. credential-harvesting — phish for passwords, PINs, bank logins, My Number
  3. advance-fee         — pay upfront (419, lottery, prize, investment)
  4. billing-fraud       — fake invoices, unpaid fees, subscriptions
  5. gov-impersonation   — fake government/tax/pension authority
  6. refund-bait         — fake refund requiring bank details or ATM
  7. romance-trust       — long-con relationship exploitation
  8. generic-scam        — genuinely unclassifiable scam

Also relabels commercial spam (viagra, conferencing, adult) as label=spam.
Preserves original scam_type as sub_type field.
"""

import json
import re
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent / "processed"
CORPUS_FILES = [
    "scam_corpus.jsonl",
    "jp_scenarios.jsonl",
    "edge_cases.jsonl",
    "gov_sources.jsonl",
    "antiphishing_corpus.jsonl",
    "conversation_corpus.jsonl",
]

# ── Old slug → new slug mapping ─────────────────────────────────────────

SLUG_MAP = {
    # → impersonation
    "ore-ore-sagi": "impersonation",
    "fake-grandchild": "impersonation",
    "fake-police": "impersonation",
    "impersonation": "impersonation",
    "cash-card": "impersonation",
    # → credential-harvesting
    "credential-phishing": "credential-harvesting",
    "fake-bank": "credential-harvesting",
    "phishing": "credential-harvesting",
    # → advance-fee
    "advance-fee-419": "advance-fee",
    "lottery-prize": "advance-fee",
    "investment-fraud": "advance-fee",
    # → billing-fraud
    "fictitious-billing": "billing-fraud",
    # → gov-impersonation (kept separate)
    "gov-impersonation": "gov-impersonation",
    # → refund-bait
    "refund-scam": "refund-bait",
    # → romance-trust
    "romance-scam": "romance-trust",
    # → generic-scam (will be re-examined)
    "generic-scam": "generic-scam",
}

# ── V2 keyword patterns for reclassifying generic-scam ──────────────────

RECLASS_PATTERNS = [
    ('credential-harvesting', re.compile(
        r'password|login|sign.?in|click here|verify.?your|confirm.?your|'
        r'update.?your|account.?has been|security.?alert|suspicious.?activity|'
        r'card.?number|expire|suspend|deactivat|unauthorized|validate|'
        r'paypal|ebay.?account|apple.?id|icloud|microsoft.?account|'
        r'click.?(?:the|this|below)|link.?below|https?://\S+(?:verify|login|secure|update)',
        re.I)),
    ('advance-fee', re.compile(
        r'million|inheritance|beneficiary|next.?of.?kin|dying.?wish|'
        r'lottery|won|winner|prize|congratulat|jackpot|selected|lucky|'
        r'invest|guaranteed.?(?:profit|return)|double.?your|forex|'
        r'gold.?bar|diplomat|trunk.?box|consignment|clearance.?fee|'
        r'processing.?fee|claim.?your|unclaim',
        re.I)),
    ('romance-trust', re.compile(
        r'lonely|looking.?for.?(?:love|friend|partner)|soul.?mate|'
        r'my.?heart|i.?love.?you|dear.?friend|widow|widower|'
        r'beautiful.?(?:lady|woman|girl)|handsome.?man|'
        r'god.?fearing|honest.?(?:man|woman)|caring|loving|'
        r'relationship|companion|marriage|dating|romantic',
        re.I)),
    ('billing-fraud', re.compile(
        r'invoice|subscription|renew|membership|overdue|'
        r'outstanding.?balance|unpaid|collection|final.?notice|'
        r'cancel.?your|auto.?renew|charged|receipt|order.?confirm',
        re.I)),
    ('impersonation', re.compile(
        r'grandson|grandma|grandpa|it.?s.?me|this.?is.?your.?(?:son|daughter)|'
        r'police|officer|detective|fbi|marshal|warrant|arrest|'
        r'accident|hospital|bail|jail|emergency.?(?:call|contact)|'
        r'don.?t.?tell',
        re.I)),
    ('gov-impersonation', re.compile(
        r'irs|tax.?(?:return|refund|office|department)|social.?security|'
        r'government|federal|department.?of|treasury|'
        r'medicare|medicaid|pension|benefit|stimulus',
        re.I)),
    ('refund-bait', re.compile(
        r'refund|overpaid|reimburs|claim.?(?:your|a).?(?:refund|payment)|'
        r'owed.?(?:money|a.?refund)|excess.?payment|rebate',
        re.I)),
]

# ── Spam detection (not scam — commercial junk) ─────────────────────────

SPAM_PATTERN = re.compile(
    r'viagra|cialis|pharmacy|prescription|weight.?loss|diet.?pill|'
    r'enlargement|penis|erectile|rolex|replica.?watch|'
    r'web.?conferencing|unlimited.?web|per.?month|'
    r'make.?money|work.?from.?home|earn.?thousands|'
    r'adult.?video|xxx|porn|sex.?tape|nude|'
    r'casino|poker|gambling|slot.?machine|bet.?online|'
    r'cheap.?(?:meds|pills|software|hosting)|'
    r'bulk.?email|mass.?mail|opt.?out|unsubscribe.?link',
    re.I)


def reslug_entry(entry: dict) -> dict:
    """Apply new taxonomy to a single entry."""
    old_type = entry.get("scam_type")
    label = entry.get("label", "safe")

    if label != "scam":
        return entry  # Don't touch safe/spam entries

    # Step 1: Direct slug mapping
    if old_type and old_type in SLUG_MAP and old_type != "generic-scam":
        entry["sub_type"] = old_type
        entry["scam_type"] = SLUG_MAP[old_type]
        return entry

    # Step 2: For generic-scam, try V2 keyword reclassification
    text = entry.get("text", "")

    # First check if it's actually spam, not scam
    if SPAM_PATTERN.search(text):
        entry["sub_type"] = old_type
        entry["label"] = "spam"
        entry["scam_type"] = None
        return entry

    # Try reclassification
    for slug, pattern in RECLASS_PATTERNS:
        if pattern.search(text):
            entry["sub_type"] = old_type or "generic-scam"
            entry["scam_type"] = slug
            return entry

    # Stays generic
    entry["sub_type"] = old_type
    entry["scam_type"] = "generic-scam"
    return entry


def main():
    for fname in CORPUS_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            continue

        entries = []
        with open(path) as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

        original_types = Counter(e.get("scam_type") for e in entries if e.get("label") == "scam")

        # Apply reslug
        for entry in entries:
            reslug_entry(entry)

        new_types = Counter(e.get("scam_type") for e in entries if e.get("label") == "scam")
        spam_count = sum(1 for e in entries if e.get("label") == "spam")

        # Write back
        with open(path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        print(f"{fname}: {len(entries)} entries processed")
        if spam_count:
            print(f"  Relabeled as spam: {spam_count}")

    # Final stats across all files
    print("\n=== FINAL TAXONOMY ===")
    all_entries = []
    for fname in CORPUS_FILES:
        path = DATA_DIR / fname
        if path.exists():
            with open(path) as f:
                for line in f:
                    if line.strip():
                        all_entries.append(json.loads(line))

    labels = Counter(e.get("label", "?") for e in all_entries)
    print(f"\nBy label:")
    for k, v in labels.most_common():
        print(f"  {k}: {v}")

    scam = [e for e in all_entries if e.get("label") == "scam"]
    types = Counter(e.get("scam_type", "?") for e in scam)
    print(f"\nScam entries by category:")
    for k, v in types.most_common():
        flag = " ⚠️ <50" if v < 50 else ""
        print(f"  {k}: {v}{flag}")

    # Sub-type preservation check
    with_sub = sum(1 for e in scam if e.get("sub_type"))
    print(f"\nSub-type preserved: {with_sub}/{len(scam)} scam entries")


if __name__ == "__main__":
    main()
