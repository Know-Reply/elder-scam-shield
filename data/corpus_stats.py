#!/usr/bin/env python3
"""Print corpus statistics across all processed data files."""

import json
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent / "processed"

FILES = {
    "scam_corpus.jsonl": "HuggingFace datasets",
    "jp_scenarios.jsonl": "NPA Japanese scenarios",
    "edge_cases.jsonl": "Edge cases",
}


def load_jsonl(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    all_records = []

    print("=" * 60)
    print("ELDER SCAM SHIELD — CORPUS STATISTICS")
    print("=" * 60)

    for fname, desc in FILES.items():
        path = PROCESSED_DIR / fname
        records = load_jsonl(path)
        if records:
            print(f"\n{fname} ({desc}): {len(records)} records")
        else:
            print(f"\n{fname} ({desc}): NOT FOUND or EMPTY")
        all_records.extend(records)

    print("\n" + "-" * 60)
    print(f"TOTAL CORPUS SIZE: {len(all_records)}")
    print("-" * 60)

    # By label
    label_counts = {}
    for r in all_records:
        label_counts[r["label"]] = label_counts.get(r["label"], 0) + 1
    print("\nBreakdown by label:")
    for k, v in sorted(label_counts.items()):
        pct = v / len(all_records) * 100 if all_records else 0
        print(f"  {k:12s}: {v:>8,}  ({pct:5.1f}%)")

    # By source
    source_counts = {}
    for r in all_records:
        source_counts[r["source"]] = source_counts.get(r["source"], 0) + 1
    print("\nBreakdown by source:")
    for k, v in sorted(source_counts.items()):
        pct = v / len(all_records) * 100 if all_records else 0
        print(f"  {k:50s}: {v:>8,}  ({pct:5.1f}%)")

    # By language
    lang_counts = {}
    for r in all_records:
        lang_counts[r["language"]] = lang_counts.get(r["language"], 0) + 1
    print("\nBreakdown by language:")
    for k, v in sorted(lang_counts.items()):
        pct = v / len(all_records) * 100 if all_records else 0
        print(f"  {k:12s}: {v:>8,}  ({pct:5.1f}%)")

    # Edge cases
    edge_count = sum(1 for r in all_records if r.get("difficulty") == "edge_case")
    print(f"\nEdge cases: {edge_count}")

    # Difficulty breakdown (for synthetic data)
    diff_counts = {}
    for r in all_records:
        d = r.get("difficulty")
        if d:
            diff_counts[d] = diff_counts.get(d, 0) + 1
    if diff_counts:
        print("\nDifficulty breakdown (synthetic data only):")
        for k, v in sorted(diff_counts.items()):
            print(f"  {k:20s}: {v:>6,}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
