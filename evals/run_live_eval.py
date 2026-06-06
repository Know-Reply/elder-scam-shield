"""Run the full eval suite through live Gemini inference and record results.

Processes all eval cases (JP + EN), sends each through the inbound classifier,
compares predicted vs expected classification, and produces a metrics report.

Usage:
    python evals/run_live_eval.py [--limit N] [--model gemini-3.1-flash-lite]
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# Block Firestore before importing agents
class _FakeFS:
    def Client(self, *a, **kw): return None
    def __getattr__(self, n): return None
_fs = _FakeFS()
sys.modules['google.cloud.firestore'] = _fs
sys.modules['google.cloud.firestore_v1'] = _fs

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.inbound_classifier import inbound_classifier

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"


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


def parse_agent_response(text: str) -> dict:
    """Parse classification JSON from agent response text."""
    # Try to find JSON in the response
    m = re.search(r'\{[^{}]*"classification"[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # Try the whole text
    try:
        return json.loads(text.strip().strip('`').strip())
    except json.JSONDecodeError:
        return {"classification": "parse_error", "raw": text[:200]}


async def run_single_case(runner, session_service, case: dict, case_idx: int) -> dict:
    """Run a single eval case through the agent."""
    user_text = extract_user_message(case)
    expected = extract_expected(case)
    eval_id = case.get("eval_id", f"case_{case_idx}")

    session = await session_service.create_session(app_name='eval', user_id='eval_user')
    msg = types.Content(role='user', parts=[types.Part(text=user_text)])

    start_time = time.time()
    predicted = {"classification": "no_response"}

    try:
        async for event in runner.run_async(user_id='eval_user', session_id=session.id, new_message=msg):
            # Walk every attribute that might carry classification data.
            # ADK events vary: some have .content, some have .actions,
            # some carry tool calls in nested structures.

            # ── 1. Text responses ───────────────────────────────────
            if hasattr(event, 'content') and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        parsed = parse_agent_response(part.text)
                        if parsed.get("classification") not in ("parse_error", None):
                            predicted = parsed

            # ── 2. Function calls (Gemini wants to call a tool) ─────
            # Capture classification from ANY tool call that carries it,
            # not just publish_classified_event.
            if hasattr(event, 'content') and event.content and event.content.parts:
                for part in event.content.parts:
                    fc = getattr(part, 'function_call', None)
                    if fc and hasattr(fc, 'args') and fc.args:
                        args = fc.args
                        # Direct classification field in any tool call
                        if args.get("classification"):
                            predicted.update({
                                k: args[k] for k in
                                ("classification", "confidence",
                                 "detected_signals", "extracted_facts")
                                if k in args
                            })
                        # JSON-encoded classification (older tool signature)
                        if args.get("classification_result"):
                            try:
                                cr = json.loads(args["classification_result"])
                                if cr.get("classification"):
                                    predicted.update(cr)
                            except (json.JSONDecodeError, TypeError):
                                pass

            # ── 3. Function responses (tool returned a result) ──────
            if hasattr(event, 'content') and event.content and event.content.parts:
                for part in event.content.parts:
                    fr = getattr(part, 'function_response', None)
                    if fr and hasattr(fr, 'response'):
                        resp = fr.response if isinstance(fr.response, dict) else {}
                        if resp.get("classification"):
                            predicted.update({
                                k: resp[k] for k in
                                ("classification", "confidence",
                                 "detected_signals", "extracted_facts")
                                if k in resp
                            })
                        # A2A event payload
                        if resp.get("event") == "message.classified":
                            predicted.update({
                                k: resp[k] for k in
                                ("classification", "confidence",
                                 "detected_signals", "extracted_facts")
                                if k in resp
                            })

            # ── 4. Catch-all: scan any dict-like event attribute ────
            for attr_name in ('actions', 'tool_calls', 'function_calls'):
                items = getattr(event, attr_name, None)
                if items and isinstance(items, (list, tuple)):
                    for item in items:
                        if isinstance(item, dict) and item.get("classification"):
                            predicted.update(item)

    except Exception as e:
        predicted = {"classification": "error", "error": str(e)[:200]}

    elapsed = time.time() - start_time

    expected_class = expected.get("classification", "unknown")
    predicted_class = predicted.get("classification", "unknown")

    # Classification match logic
    # "scam" and "suspicious" both count as "detected" for recall
    detected_expected = expected_class in ("scam", "suspicious")
    detected_predicted = predicted_class in ("scam", "suspicious")

    exact_match = expected_class == predicted_class
    detection_match = detected_expected == detected_predicted

    return {
        "eval_id": eval_id,
        "source_file": case.get("_source_file", "?"),
        "expected_classification": expected_class,
        "predicted_classification": predicted_class,
        "exact_match": exact_match,
        "detection_match": detection_match,
        "expected_signals": expected.get("detected_signals", []),
        "predicted_signals": predicted.get("detected_signals", []),
        "predicted_confidence": predicted.get("confidence"),
        "elapsed_seconds": round(elapsed, 2),
        "reasoning": predicted.get("reasoning", "")[:200],
    }


async def run_eval(limit: int = None):
    """Run the full evaluation suite."""
    # Load API key
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                os.environ["GOOGLE_API_KEY"] = line.split("=", 1)[1].strip()

    cases = load_eval_cases()
    if limit:
        cases = cases[:limit]

    print(f"Running {len(cases)} eval cases through live Gemini inference...")
    print(f"Model: {inbound_classifier.model}")
    print()

    session_service = InMemorySessionService()
    runner = Runner(agent=inbound_classifier, app_name='eval', session_service=session_service)

    results = []
    for i, case in enumerate(cases):
        eval_id = case.get("eval_id", f"case_{i}")
        print(f"  [{i+1}/{len(cases)}] {eval_id}...", end=" ", flush=True)
        result = await run_single_case(runner, session_service, case, i)
        match_symbol = "✓" if result["detection_match"] else "✗"
        exact_symbol = "=" if result["exact_match"] else "≠"
        print(f"{match_symbol} expected={result['expected_classification']}, "
              f"got={result['predicted_classification']} ({result['elapsed_seconds']}s)")
        results.append(result)
        # Brief pause to avoid rate limiting
        await asyncio.sleep(0.5)

    # ── Compute metrics ─────────────────────────────────────────────────
    total = len(results)
    exact_matches = sum(1 for r in results if r["exact_match"])
    detection_matches = sum(1 for r in results if r["detection_match"])

    # Per-category accuracy
    by_expected = defaultdict(list)
    for r in results:
        by_expected[r["expected_classification"]].append(r)

    # Detection metrics (scam+suspicious = positive, safe+spam = negative)
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

    # Failures
    failures = [r for r in results if not r["detection_match"]]

    # ── Print report ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("LIVE EVALUATION RESULTS")
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
            print(f"  ✗ {f['eval_id']}: expected={f['expected_classification']}, "
                  f"got={f['predicted_classification']}")
            if f.get("reasoning"):
                print(f"    reason: {f['reasoning'][:120]}")

    # ── Save results ────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    results_path = RESULTS_DIR / f"live_eval_{ts}.json"

    report = {
        "timestamp": ts,
        "model": str(inbound_classifier.model),
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
