#!/usr/bin/env python3
"""Download phishing/scam datasets from HuggingFace and save to data/raw/."""

import os
from pathlib import Path
from datasets import load_dataset

RAW_DIR = Path(__file__).parent / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

def download_phishing_email_dataset():
    """Download zefang-liu/phishing-email-dataset (18.7k emails)."""
    print("Downloading zefang-liu/phishing-email-dataset...")
    ds = load_dataset("zefang-liu/phishing-email-dataset")
    out = RAW_DIR / "phishing_email_dataset"
    out.mkdir(exist_ok=True)
    ds.save_to_disk(str(out))
    # Also save as parquet for easy inspection
    for split_name, split_ds in ds.items():
        split_ds.to_parquet(str(out / f"{split_name}.parquet"))
    total = sum(len(s) for s in ds.values())
    print(f"  Saved {total} rows to {out}")

def download_phishing_detection_v2():
    """Download cybersectony/PhishingEmailDetectionv2.0 (200k items)."""
    print("Downloading cybersectony/PhishingEmailDetectionv2.0...")
    ds = load_dataset("cybersectony/PhishingEmailDetectionv2.0")
    out = RAW_DIR / "phishing_detection_v2"
    out.mkdir(exist_ok=True)
    ds.save_to_disk(str(out))
    for split_name, split_ds in ds.items():
        split_ds.to_parquet(str(out / f"{split_name}.parquet"))
    total = sum(len(s) for s in ds.values())
    print(f"  Saved {total} rows to {out}")

if __name__ == "__main__":
    download_phishing_email_dataset()
    download_phishing_detection_v2()
    print("Done downloading datasets.")
