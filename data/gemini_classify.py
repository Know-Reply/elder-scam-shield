"""Classify generic-scam entries using Gemini flash-lite.

Sends batches of entries to Gemini with our 8-category taxonomy.
Entries classified with ≥0.6 confidence get re-tagged.
Entries below 0.6 stay generic-scam.
Logs all confidence scores for analysis.

Usage:
    python data/gemini_classify.py [--batch-size 20] [--limit 500] [--dry-run]
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from google import genai

DATA_DIR = Path(__file__).parent / "processed"
CORPUS_PATH = DATA_DIR / "scam_corpus.jsonl"
LOG_PATH = Path(__file__).parent / "gemini_classify_log.jsonl"

TAXONOMY_PROMPT = """You are a scam email classifier. Classify each message into exactly one category.

CATEGORIES:
1. credential-harvesting — Phishing for passwords, PINs, bank logins, card numbers, SSN, My Number. Asks victim to click a link, verify identity, or enter credentials.
2. advance-fee — Victim must pay upfront to receive something: inheritance, lottery prize, investment return, loan, job offer. Includes 419/Nigerian scams.
3. impersonation — Pretends to be a trusted person: family member, police officer, colleague, lawyer. Uses urgency/crisis to extract money or compliance.
4. billing-fraud — Fake invoices, unpaid fees, subscription charges, overdue notices. Threatens legal action for non-payment.
5. gov-impersonation — Impersonates government agency: tax office, pension bureau, social security, Medicare. Demands payment or personal info.
6. refund-bait — Claims victim is owed a refund (tax, insurance, overpayment). Requests bank details or ATM visit to "process" refund.
7. romance-trust — Builds romantic/friendship relationship over time before requesting money. Uses emotional manipulation, flattery, shared dreams.
8. generic-scam — Does not fit any above category. Use this ONLY if none of the 7 categories apply.

For EACH message, respond with a JSON array entry:
{"index": N, "category": "category-slug", "confidence": 0.0-1.0, "reasoning": "brief explanation"}

Classify these messages:
"""


def load_generic_entries() -> list[tuple[int, dict]]:
    """Load all generic-scam entries with their line indices."""
    entries = []
    with open(CORPUS_PATH) as f:
        for i, line in enumerate(f):
            if line.strip():
                entry = json.loads(line)
                if entry.get("scam_type") == "generic-scam" and entry.get("label") == "scam":
                    entries.append((i, entry))
    return entries


def classify_batch(client, entries: list[tuple[int, dict]], batch_num: int) -> list[dict]:
    """Send a batch to Gemini and parse classifications."""
    # Build prompt with numbered messages
    prompt = TAXONOMY_PROMPT + "\n"
    for j, (_, entry) in enumerate(entries):
        text = entry.get("text", "")[:500]  # Truncate long emails
        prompt += f"\n[{j}] {text}\n"

    prompt += "\nRespond with a JSON array of classifications. Only JSON, no markdown."

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
        )
        text = response.text.strip()

        # Parse JSON from response — handle markdown code blocks
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        results = json.loads(text)
        if isinstance(results, dict):
            results = [results]
        return results
    except Exception as e:
        print(f"  Batch {batch_num} error: {e}")
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None, help="Max entries to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying files")
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        # Try loading from .env
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        print("Error: GOOGLE_API_KEY not set")
        return

    client = genai.Client(api_key=api_key)

    # Load generic entries
    generic = load_generic_entries()
    print(f"Loaded {len(generic)} generic-scam entries")

    if args.limit:
        generic = generic[:args.limit]
        print(f"Limited to {len(generic)} entries")

    # Process in batches
    all_results = []
    reclassified = Counter()
    stayed_generic = 0
    confidence_scores = []

    total_batches = (len(generic) + args.batch_size - 1) // args.batch_size

    for batch_idx in range(0, len(generic), args.batch_size):
        batch = generic[batch_idx:batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} entries)...", end=" ", flush=True)

        results = classify_batch(client, batch, batch_num)
        print(f"got {len(results)} classifications")

        for result in results:
            idx = result.get("index", -1)
            category = result.get("category", "generic-scam")
            confidence = result.get("confidence", 0)
            reasoning = result.get("reasoning", "")

            if 0 <= idx < len(batch):
                line_idx, entry = batch[idx]
                confidence_scores.append(confidence)

                log_entry = {
                    "entry_id": entry.get("id", "?"),
                    "old_type": "generic-scam",
                    "new_type": category if confidence >= 0.6 else "generic-scam",
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "text_preview": entry.get("text", "")[:100],
                }
                all_results.append((line_idx, log_entry))

                if confidence >= 0.6 and category != "generic-scam":
                    reclassified[category] += 1
                else:
                    stayed_generic += 1

        # Rate limit — 1 second between batches
        time.sleep(1)

    # Summary
    print(f"\n=== CLASSIFICATION RESULTS ===")
    print(f"Total processed: {len(confidence_scores)}")
    print(f"Reclassified (≥0.6 confidence): {sum(reclassified.values())}")
    for k, v in reclassified.most_common():
        print(f"  → {k}: {v}")
    print(f"Stayed generic-scam (<0.6 or category=generic): {stayed_generic}")

    if confidence_scores:
        avg_conf = sum(confidence_scores) / len(confidence_scores)
        high = sum(1 for c in confidence_scores if c >= 0.8)
        mid = sum(1 for c in confidence_scores if 0.6 <= c < 0.8)
        low = sum(1 for c in confidence_scores if c < 0.6)
        print(f"\nConfidence distribution:")
        print(f"  ≥0.8: {high} ({high/len(confidence_scores)*100:.1f}%)")
        print(f"  0.6-0.8: {mid} ({mid/len(confidence_scores)*100:.1f}%)")
        print(f"  <0.6: {low} ({low/len(confidence_scores)*100:.1f}%)")
        print(f"  Average: {avg_conf:.2f}")

    # Write log
    with open(LOG_PATH, "w") as f:
        for _, log_entry in all_results:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    print(f"\nLog written to {LOG_PATH}")

    if args.dry_run:
        print("\n[DRY RUN — no files modified]")
        return

    # Apply reclassifications to corpus file
    print(f"\nApplying reclassifications to {CORPUS_PATH}...")
    reclassify_map = {}
    for line_idx, log_entry in all_results:
        if log_entry["new_type"] != "generic-scam":
            reclassify_map[line_idx] = log_entry["new_type"]

    if not reclassify_map:
        print("No reclassifications to apply.")
        return

    # Read, modify, write
    lines = []
    with open(CORPUS_PATH) as f:
        lines = f.readlines()

    modified = 0
    for line_idx, new_type in reclassify_map.items():
        if line_idx < len(lines):
            entry = json.loads(lines[line_idx])
            entry["sub_type"] = entry.get("sub_type") or entry.get("scam_type", "generic-scam")
            entry["scam_type"] = new_type
            entry["classified_by"] = "gemini-3.1-flash-lite"
            lines[line_idx] = json.dumps(entry, ensure_ascii=False) + "\n"
            modified += 1

    with open(CORPUS_PATH, "w") as f:
        f.writelines(lines)

    print(f"Modified {modified} entries in {CORPUS_PATH}")


if __name__ == "__main__":
    main()
