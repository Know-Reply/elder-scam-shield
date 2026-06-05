#!/usr/bin/env python3
"""
Process downloaded datasets into a unified scam corpus.

Loads both HuggingFace datasets from data/raw/, normalizes schema,
deduplicates, and writes to data/processed/scam_corpus.jsonl.
"""

import hashlib
import json
import os
from pathlib import Path
from datasets import load_from_disk

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = PROCESSED_DIR / "scam_corpus.jsonl"


def normalize_text(text: str) -> str:
    """Basic text normalization for dedup comparison."""
    if not text:
        return ""
    # Collapse whitespace, strip, lowercase for comparison
    return " ".join(text.lower().split())


def text_fingerprint(text: str) -> str:
    """SHA-256 of normalized text for exact dedup."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def process_phishing_email_dataset():
    """
    zefang-liu/phishing-email-dataset
    Columns: 'Email Text', 'Email Type' (Safe Email / Phishing Email)
    """
    path = RAW_DIR / "phishing_email_dataset"
    if not path.exists():
        print(f"  SKIP: {path} not found (run download_datasets.py first)")
        return []

    ds = load_from_disk(str(path))
    records = []
    idx = 0

    for split_name in ds:
        for row in ds[split_name]:
            text = row.get("Email Text", "") or ""
            email_type = row.get("Email Type", "") or ""

            if not text.strip():
                continue

            label = "safe" if "safe" in email_type.lower() else "scam"
            scam_type = "phishing" if label == "scam" else None

            records.append({
                "id": f"zefang_{idx:06d}",
                "source": "zefang-liu/phishing-email-dataset",
                "text": text.strip(),
                "label": label,
                "scam_type": scam_type,
                "language": "en",
            })
            idx += 1

    print(f"  zefang-liu/phishing-email-dataset: {len(records)} records")
    return records


def process_phishing_detection_v2():
    """
    cybersectony/PhishingEmailDetectionv2.0
    Columns: 'content', 'label' (0=safe email, 1=phishing email, 2+=URL rows we skip)
    """
    path = RAW_DIR / "phishing_detection_v2"
    if not path.exists():
        print(f"  SKIP: {path} not found (run download_datasets.py first)")
        return []

    ds = load_from_disk(str(path))
    records = []
    idx = 0
    skipped_url = 0

    for split_name in ds:
        for row in ds[split_name]:
            row_label = row.get("label", -1)

            # Only keep email rows: label 0 (safe) or 1 (phishing)
            if row_label not in (0, 1):
                skipped_url += 1
                continue

            text = row.get("content", "") or row.get("text", "") or ""
            if not text.strip():
                continue

            label = "safe" if row_label == 0 else "scam"
            scam_type = "phishing" if label == "scam" else None

            records.append({
                "id": f"cybersec_{idx:06d}",
                "source": "cybersectony/PhishingEmailDetectionv2.0",
                "text": text.strip(),
                "label": label,
                "scam_type": scam_type,
                "language": "en",
            })
            idx += 1

    print(f"  cybersectony/PhishingEmailDetectionv2.0: {len(records)} records (skipped {skipped_url} URL rows)")
    return records


def deduplicate(records: list[dict]) -> list[dict]:
    """Remove exact duplicates by normalized text fingerprint."""
    seen = set()
    deduped = []
    for rec in records:
        fp = text_fingerprint(rec["text"])
        if fp not in seen:
            seen.add(fp)
            deduped.append(rec)
    removed = len(records) - len(deduped)
    print(f"  Dedup: removed {removed} exact duplicates, {len(deduped)} remain")
    return deduped


def write_corpus(records: list[dict], output_path: Path):
    """Write records as JSONL."""
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  Wrote {len(records)} records to {output_path}")


def print_stats(records: list[dict]):
    """Print corpus statistics."""
    print("\n=== Corpus Statistics ===")
    print(f"Total records: {len(records)}")

    # By label
    label_counts = {}
    for r in records:
        label_counts[r["label"]] = label_counts.get(r["label"], 0) + 1
    print("\nBy label:")
    for k, v in sorted(label_counts.items()):
        print(f"  {k}: {v}")

    # By source
    source_counts = {}
    for r in records:
        source_counts[r["source"]] = source_counts.get(r["source"], 0) + 1
    print("\nBy source:")
    for k, v in sorted(source_counts.items()):
        print(f"  {k}: {v}")

    # By language
    lang_counts = {}
    for r in records:
        lang_counts[r["language"]] = lang_counts.get(r["language"], 0) + 1
    print("\nBy language:")
    for k, v in sorted(lang_counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    print("Processing datasets...")

    all_records = []
    all_records.extend(process_phishing_email_dataset())
    all_records.extend(process_phishing_detection_v2())

    if not all_records:
        print("No records found. Run download_datasets.py first.")
        exit(1)

    all_records = deduplicate(all_records)
    write_corpus(all_records, OUTPUT_FILE)
    print_stats(all_records)
