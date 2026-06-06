"""Process multi-turn scam conversation datasets into corpus format.

Sources:
- BothBosu/scam-dialogue: 1,600 multi-turn phone call transcripts (synthetic, Llama 3 70B)
- BothBosu/multi-agent-scam-conversation: 1,600 multi-turn with personality types (synthetic, AutoGen)

These are the highest-priority datasets for the Behavioral Analyzer —
multi-turn conversations are what differentiates us from per-message classifiers.
"""

import json
from pathlib import Path
from datasets import load_from_disk

DATA_DIR = Path(__file__).parent
OUTPUT = DATA_DIR / "processed" / "conversation_corpus.jsonl"

# Map BothBosu scam types to NPA pattern slugs
TYPE_MAP = {
    "ssn": "gov-impersonation",       # Social Security Number scam → government impersonation
    "refund": "refund-scam",           # Refund scam
    "support": "credential-phishing",  # Tech support scam → credential phishing
    "reward": "lottery-prize",         # Reward/gift card → lottery/prize
    "delivery": None,                  # Legitimate delivery
    "insurance": None,                 # Legitimate insurance
    "telemarketing": None,             # Legitimate telemarketing
    "wrong": None,                     # Wrong number (legitimate)
    "appointment": None,               # Legitimate appointment
}


def count_turns(dialogue: str) -> int:
    """Count conversation turns in a dialogue."""
    turns = 0
    for marker in ["caller:", "receiver:", "Innocent:", "Suspect:"]:
        turns += dialogue.lower().count(marker.lower())
    return max(turns, 1)


def process_scam_dialogue():
    """Process BothBosu/scam-dialogue."""
    ds = load_from_disk(str(DATA_DIR / "raw" / "scam_dialogue"))
    entries = []
    idx = 0

    for split in ["train", "test"]:
        for row in ds[split]:
            dialogue = row["dialogue"]
            scam_type_raw = row["type"]
            label_int = row["label"]

            label = "scam" if label_int == 1 else "safe"
            scam_type = TYPE_MAP.get(scam_type_raw, "generic-scam") if label == "scam" else None
            turns = count_turns(dialogue)

            entries.append({
                "id": f"conv_sd_{idx:04d}",
                "source": "BothBosu/scam-dialogue",
                "text": dialogue,
                "label": label,
                "scam_type": scam_type,
                "language": "en",
                "content_type": "multi_turn_conversation",
                "turn_count": turns,
                "scam_subtype": scam_type_raw,
                "synthetic": True,
                "synthetic_method": "Meta Llama 3 70B Instruct",
            })
            idx += 1

    return entries


def process_multi_agent():
    """Process BothBosu/multi-agent-scam-conversation."""
    ds = load_from_disk(str(DATA_DIR / "raw" / "multi_agent_scam"))
    entries = []
    idx = 0

    for split in ["train", "test"]:
        for row in ds[split]:
            dialogue = row["dialogue"]
            personality = row["personality"]
            scam_type_raw = row["type"]
            label_int = row["labels"]

            label = "scam" if label_int == 1 else "safe"
            scam_type = TYPE_MAP.get(scam_type_raw, "generic-scam") if label == "scam" else None
            turns = count_turns(dialogue)

            entries.append({
                "id": f"conv_ma_{idx:04d}",
                "source": "BothBosu/multi-agent-scam-conversation",
                "text": dialogue,
                "label": label,
                "scam_type": scam_type,
                "language": "en",
                "content_type": "multi_turn_conversation",
                "turn_count": turns,
                "scam_subtype": scam_type_raw,
                "personality": personality,
                "synthetic": True,
                "synthetic_method": "AutoGen + Together Inference API",
            })
            idx += 1

    return entries


def main():
    print("Processing multi-turn conversation datasets...")

    sd_entries = process_scam_dialogue()
    print(f"  BothBosu/scam-dialogue: {len(sd_entries)} conversations")

    ma_entries = process_multi_agent()
    print(f"  BothBosu/multi-agent-scam-conversation: {len(ma_entries)} conversations")

    all_entries = sd_entries + ma_entries

    # Stats
    from collections import Counter
    labels = Counter(e["label"] for e in all_entries)
    types = Counter(e["scam_type"] for e in all_entries if e["scam_type"])
    turns = [e["turn_count"] for e in all_entries]
    personalities = Counter(e.get("personality", "n/a") for e in all_entries if e.get("personality"))

    print(f"\n  Total: {len(all_entries)} conversations")
    print(f"  By label: {dict(labels)}")
    print(f"  By scam_type: {dict(types)}")
    print(f"  Turn count: min={min(turns)}, max={max(turns)}, avg={sum(turns)/len(turns):.1f}")
    if personalities:
        print(f"  Personalities: {dict(personalities)}")

    # Write
    with open(OUTPUT, "w") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n  Saved {len(all_entries)} entries to {OUTPUT}")


if __name__ == "__main__":
    main()
