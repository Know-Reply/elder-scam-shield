"""Run a naive baseline classifier against all eval cases for before/after comparison.

Uses a simple prompt with NO signal taxonomy, NO corpus grounding, NO NPA patterns.
This produces the "before" metrics for Track 2's before/after comparison.

Usage:
    python evals/run_baseline_eval.py [--limit N]
"""

import argparse
import asyncio
import glob
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

# Block Firestore before any transitive imports
class _FakeFS:
    def Client(self, *a, **kw): return None
    def __getattr__(self, n): return None
_fs = _FakeFS()
sys.modules['google.cloud.firestore'] = _fs
sys.modules['google.cloud.firestore_v1'] = _fs

from google import genai

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"

MODEL = "gemini-3.1-flash-lite"

NAIVE_PROMPT = """You are a spam filter. Classify the following message as safe, spam, or scam.
Output JSON only: {"classification": "safe|spam|scam", "confidence": 0.0-1.0, "reasoning": "brief"}"""


def load_eval_cases() -> list[dict]:
    """Load all eval cases from all eval set files."""
    cases = []
    for fname in ["scam_detection.evalset.json", "scam_detection_full.evalset.json",
                   "scam_detection_english.evalset.json"]:
        path = EVALS_DIR / fname
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            for case in data.get("eval_cases", []):
                case["_source_file"] = fname
                cases.append(case)
    return cases


def extract_expected(case: dict) -> dict:
    """Extract expected classification from eval case."""
    try:
        resp_text = case["conversation"][0]["final_response"]["parts"][0]["text"]
        return json.loads(resp_text)
    except (KeyError, json.JSONDecodeError):
        return {"classification": "unknown"}


def extract_user_message(case: dict) -> str:
    """Extract the user message text from eval case."""
    return case["conversation"][0]["user_content"]["parts"][0]["text"]


def parse_response(text: str) -> dict:
    """Parse classification JSON from model response text."""
    m = re.search(r'\{[^{}]*"classification"[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip().strip('`').strip())
    except json.JSONDecodeError:
        return {"classification": "parse_error", "raw": text[:200]}


def load_latest_optimized_results() -> dict | None:
    """Load the most recent optimized eval results for comparison."""
    if not RESULTS_DIR.exists():
        return None
    files = sorted(RESULTS_DIR.glob("live_eval_*.json"))
    if not files:
        return None
    with open(files[-1]) as f:
        return json.load(f)


async def run_eval(limit: int = None):
    """Run the full baseline evaluation."""
    # Load API key from .env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                os.environ["GOOGLE_API_KEY"] = line.split("=", 1)[1].strip()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found in .env or environment")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    cases = load_eval_cases()
    if limit:
        cases = cases[:limit]

    print(f"Running BASELINE eval: {len(cases)} cases with naive prompt")
    print(f"Model: {MODEL}")
    print(f"Prompt: {NAIVE_PROMPT[:80]}...")
    print()

    results = []
    for i, case in enumerate(cases):
        eval_id = case.get("eval_id", f"case_{i}")
        user_text = extract_user_message(case)
        expected = extract_expected(case)

        print(f"  [{i+1}/{len(cases)}] {eval_id}...", end=" ", flush=True)

        start_time = time.time()
        predicted = {"classification": "no_response"}

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[
                    {"role": "user", "parts": [{"text": f"{NAIVE_PROMPT}\n\nMessage:\n{user_text}"}]}
                ],
            )
            if response.text:
                predicted = parse_response(response.text)
        except Exception as e:
            predicted = {"classification": "error", "error": str(e)[:200]}

        elapsed = time.time() - start_time

        expected_class = expected.get("classification", "unknown")
        predicted_class = predicted.get("classification", "unknown")

        # Detection match: scam/suspicious = positive
        detected_expected = expected_class in ("scam", "suspicious")
        detected_predicted = predicted_class in ("scam", "suspicious")

        exact_match = expected_class == predicted_class
        detection_match = detected_expected == detected_predicted

        match_symbol = "+" if detection_match else "X"
        print(f"{match_symbol} expected={expected_class}, "
              f"got={predicted_class} ({elapsed:.2f}s)")

        results.append({
            "eval_id": eval_id,
            "source_file": case.get("_source_file", "?"),
            "expected_classification": expected_class,
            "predicted_classification": predicted_class,
            "exact_match": exact_match,
            "detection_match": detection_match,
            "predicted_confidence": predicted.get("confidence"),
            "elapsed_seconds": round(elapsed, 2),
            "reasoning": predicted.get("reasoning", "")[:200],
        })

        # Rate limit
        await asyncio.sleep(0.5)

    # -- Compute metrics -------------------------------------------------
    total = len(results)
    exact_matches = sum(1 for r in results if r["exact_match"])
    detection_matches = sum(1 for r in results if r["detection_match"])

    by_expected = defaultdict(list)
    for r in results:
        by_expected[r["expected_classification"]].append(r)

    true_positives = sum(1 for r in results
                         if r["expected_classification"] in ("scam", "suspicious")
                         and r["predicted_classification"] in ("scam", "suspicious"))
    false_positives = sum(1 for r in results
                          if r["expected_classification"] in ("safe", "spam")
                          and r["predicted_classification"] in ("scam", "suspicious"))
    false_negatives = sum(1 for r in results
                          if r["expected_classification"] in ("scam", "suspicious")
                          and r["predicted_classification"] in ("safe", "spam"))
    true_negatives = sum(1 for r in results
                         if r["expected_classification"] in ("safe", "spam")
                         and r["predicted_classification"] in ("safe", "spam"))

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    failures = [r for r in results if not r["detection_match"]]

    # -- Print report ----------------------------------------------------
    print("\n" + "=" * 60)
    print("BASELINE EVALUATION RESULTS (Naive Prompt)")
    print("=" * 60)
    print(f"\nTotal cases: {total}")
    print(f"Exact classification match: {exact_matches}/{total} ({exact_matches/total*100:.1f}%)")
    print(f"Detection match (scam/suspicious vs safe): {detection_matches}/{total} ({detection_matches/total*100:.1f}%)")
    print(f"\nPrecision: {precision:.3f}")
    print(f"Recall:    {recall:.3f}")
    print(f"F1 Score:  {f1:.3f}")
    print(f"\nConfusion matrix:")
    print(f"  TP (correctly flagged scam):  {true_positives}")
    print(f"  FP (safe flagged as scam):    {false_positives}")
    print(f"  FN (scam missed as safe):     {false_negatives}")
    print(f"  TN (correctly passed safe):   {true_negatives}")

    print(f"\nPer-category accuracy:")
    for cat, cat_results in sorted(by_expected.items()):
        correct = sum(1 for r in cat_results if r["exact_match"])
        print(f"  {cat}: {correct}/{len(cat_results)} ({correct/len(cat_results)*100:.1f}%)")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  X {f['eval_id']}: expected={f['expected_classification']}, "
                  f"got={f['predicted_classification']}")
            if f.get("reasoning"):
                print(f"    reason: {f['reasoning'][:120]}")

    # -- Side-by-side comparison with optimized --------------------------
    optimized = load_latest_optimized_results()
    if optimized:
        print("\n" + "=" * 60)
        print("BEFORE / AFTER COMPARISON")
        print("=" * 60)

        b_exact = exact_matches / total * 100
        o_exact = optimized["exact_match_rate"] * 100
        b_detect = detection_matches / total * 100
        o_detect = optimized["detection_match_rate"] * 100
        b_prec = precision
        o_prec = optimized["precision"]
        b_rec = recall
        o_rec = optimized["recall"]
        b_f1 = f1
        o_f1 = optimized["f1_score"]
        b_fp = false_positives
        o_fp = optimized["confusion_matrix"]["false_positives"]
        b_fn = false_negatives
        o_fn = optimized["confusion_matrix"]["false_negatives"]

        def delta_str(b, o, fmt=".1f", suffix="%"):
            d = o - b
            sign = "+" if d >= 0 else ""
            return f"{sign}{d:{fmt}}{suffix}"

        def delta_str_int(b, o):
            d = o - b
            sign = "+" if d >= 0 else ""
            return f"{sign}{d}"

        print(f"{'':20s} {'Baseline':>12s} {'Optimized':>12s} {'Delta':>12s}")
        print(f"{'Exact match:':<20s} {b_exact:>11.1f}% {o_exact:>11.1f}% {delta_str(b_exact, o_exact):>12s}")
        print(f"{'Detection match:':<20s} {b_detect:>11.1f}% {o_detect:>11.1f}% {delta_str(b_detect, o_detect):>12s}")
        print(f"{'Precision:':<20s} {b_prec:>12.3f} {o_prec:>12.3f} {delta_str(b_prec, o_prec, '.3f', ''):>12s}")
        print(f"{'Recall:':<20s} {b_rec:>12.3f} {o_rec:>12.3f} {delta_str(b_rec, o_rec, '.3f', ''):>12s}")
        print(f"{'F1:':<20s} {b_f1:>12.3f} {o_f1:>12.3f} {delta_str(b_f1, o_f1, '.3f', ''):>12s}")
        print(f"{'False positives:':<20s} {b_fp:>12d} {o_fp:>12d} {delta_str_int(b_fp, o_fp):>12s}")
        print(f"{'False negatives:':<20s} {b_fn:>12d} {o_fn:>12d} {delta_str_int(b_fn, o_fn):>12s}")

    # -- Save results ----------------------------------------------------
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    results_path = RESULTS_DIR / f"baseline_eval_{ts}.json"

    report = {
        "timestamp": ts,
        "model": MODEL,
        "prompt": NAIVE_PROMPT,
        "eval_type": "baseline_naive",
        "total_cases": total,
        "exact_match_rate": round(exact_matches / total, 4),
        "detection_match_rate": round(detection_matches / total, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "confusion_matrix": {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "true_negatives": true_negatives,
        },
        "per_category": {
            cat: {
                "total": len(cat_results),
                "correct": sum(1 for r in cat_results if r["exact_match"]),
                "accuracy": round(sum(1 for r in cat_results if r["exact_match"]) / len(cat_results), 4),
            }
            for cat, cat_results in by_expected.items()
        },
        "failures": failures,
        "all_results": results,
    }

    if optimized:
        report["comparison_with_optimized"] = {
            "optimized_file": str(sorted(RESULTS_DIR.glob("live_eval_*.json"))[-1].name),
            "exact_match_delta": round(optimized["exact_match_rate"] - exact_matches / total, 4),
            "detection_match_delta": round(optimized["detection_match_rate"] - detection_matches / total, 4),
            "precision_delta": round(optimized["precision"] - precision, 4),
            "recall_delta": round(optimized["recall"] - recall, 4),
            "f1_delta": round(optimized["f1_score"] - f1, 4),
        }

    with open(results_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {results_path}")

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run_eval(args.limit))


if __name__ == "__main__":
    main()
