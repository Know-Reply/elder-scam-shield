"""Longitudinal eval runner — tests ConversationRiskLedger across multi-message scenarios.

Runs each scenario through:
  1. Full pipeline: LLM signal detection + risk ledger accumulation
  2. Naive baseline: LLM classification only, no tools, no corpus, no ledger

Compares: classification accuracy, time-to-detection, false positive rate.

Usage:
    python evals/run_longitudinal_eval.py
    python evals/run_longitudinal_eval.py --scenario oreore_slow_6msg
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:8080"
SCENARIOS_PATH = Path(__file__).parent / "longitudinal_scenarios.json"
RESULTS_PATH = Path(__file__).parent / "results" / "longitudinal_results.json"


def post(path, data, timeout=300):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def reset():
    """Reset all server-side state between scenarios."""
    post("/api/conversation/reset", {"session_id": "eval_reset"})


def run_scenario(scenario):
    """Run one scenario through full pipeline + naive baseline."""
    sid = scenario["id"]
    # Legitimate-family scenarios run from senders present in the elder's
    # contact graph, as they would be in production (a real daughter is a
    # known contact). Scam scenarios run from unknown senders.
    sender_id = scenario.get("sender_id", f"eval_{sid}")
    messages = scenario["messages"]

    reset()

    results = []
    for i, msg in enumerate(messages):
        t0 = time.time()

        # Full pipeline: LLM signal detection + risk ledger
        classify_resp = post("/api/classify", {
            "sender": sender_id,
            "content": msg["text"],
        })
        full_result = classify_resp.get("result", {})
        full_time = time.time() - t0

        # Naive baseline
        t1 = time.time()
        naive_resp = post("/api/classify-naive", {
            "sender": sender_id,
            "content": msg["text"],
        })
        naive_result = naive_resp.get("result", {})
        naive_time = time.time() - t1

        # Pace requests — sustained bursts trip Vertex per-minute quota,
        # which surfaces as long retry stalls inside ADK
        time.sleep(2)

        results.append({
            "message_index": i,
            "text_preview": msg["text"][:60],
            "expected_signals": msg.get("expected_signals", []),
            "expected_class": msg.get("expected_class", "safe"),
            # Full pipeline results
            "full": {
                "classification": full_result.get("classification", "safe"),
                "confidence": full_result.get("confidence", 0),
                "risk_score": full_result.get("risk_score", 0),
                "detected_signals": full_result.get("detected_signals", []),
                "family_alert": full_result.get("family_alert_fired", False),
                "latency_ms": round(full_time * 1000),
            },
            # Naive baseline results
            "naive": {
                "classification": naive_result.get("classification", "safe"),
                "confidence": naive_result.get("confidence", 0),
                "detected_signals": naive_result.get("detected_signals", []),
                "latency_ms": round(naive_time * 1000),
            },
        })

    return results


GRADING_NOTES = [
    "high_risk is graded as suspicious (adjacent band, same user-visible action).",
    "Expected 'monitoring' accepts monitoring OR suspicious from EITHER system — "
    "the naive classifier's taxonomy (safe/spam/scam/suspicious) cannot emit "
    "'monitoring', so those labels are graded leniently for both systems.",
    "Spam scenarios accept 'spam' OR 'safe' from EITHER system — commercial spam "
    "poses no fraud risk to the elder, so both responses are correct.",
    "False positives count user-visible actions: for the full pipeline, "
    "'monitoring' is an internal state (no alert fires below suspicious); for "
    "the naive baseline, any non-safe classification blocks the message.",
    "Sender identity: legitimate-family scenarios are sent from contacts "
    "present in the elder's social graph, matching production where family "
    "members are known contacts. Scam scenarios are sent from unknown "
    "senders. The graph's verdict reaches the risk ledger as a contribution "
    "modifier (verified contact dampens non-EA signals; unknown sender "
    "claiming a family relationship is boosted).",
]


def is_correct(pred, expected, scam_type):
    """Fair grading — see GRADING_NOTES."""
    if pred == "high_risk":
        pred = "suspicious"
    acceptable = {expected}
    if expected == "monitoring":
        acceptable.add("suspicious")
    if scam_type == "spam" and expected in ("safe", "spam"):
        acceptable |= {"safe", "spam"}
    return pred in acceptable


def compute_metrics(scenario, results):
    """Compute per-scenario metrics."""
    messages = scenario["messages"]
    n = len(messages)
    scam_type = scenario["scam_type"]

    # Classification accuracy
    full_correct = 0
    naive_correct = 0
    for i, r in enumerate(results):
        expected = r["expected_class"]
        if is_correct(r["full"]["classification"], expected, scam_type):
            full_correct += 1
        if is_correct(r["naive"]["classification"], expected, scam_type):
            naive_correct += 1

    # Time-to-detection: first message where classification != safe
    full_detect_at = None
    naive_detect_at = None
    for i, r in enumerate(results):
        if full_detect_at is None and r["full"]["classification"] not in ("safe",):
            full_detect_at = i
        if naive_detect_at is None and r["naive"]["classification"] not in ("safe",):
            naive_detect_at = i

    # Signal detection precision/recall vs expected
    full_signal_tp = 0
    full_signal_fp = 0
    full_signal_fn = 0
    for r in results:
        expected = set(r["expected_signals"])
        detected = set(r["full"]["detected_signals"])
        full_signal_tp += len(expected & detected)
        full_signal_fp += len(detected - expected)
        full_signal_fn += len(expected - detected)

    precision = full_signal_tp / max(full_signal_tp + full_signal_fp, 1)
    recall = full_signal_tp / max(full_signal_tp + full_signal_fn, 1)

    # Family alert timing
    alert_at = None
    for i, r in enumerate(results):
        if r["full"].get("family_alert"):
            alert_at = i
            break

    return {
        "scenario_id": scenario["id"],
        "scam_type": scenario["scam_type"],
        "message_count": n,
        "full_accuracy": round(full_correct / n, 3),
        "naive_accuracy": round(naive_correct / n, 3),
        "full_detect_at_message": full_detect_at,
        "naive_detect_at_message": naive_detect_at,
        "detection_advantage": (naive_detect_at or n) - (full_detect_at or n),
        "signal_precision": round(precision, 3),
        "signal_recall": round(recall, 3),
        "family_alert_at_message": alert_at,
        "first_full_class": results[0]["full"]["classification"],
        "first_naive_class": results[0]["naive"]["classification"],
        "final_full_class": results[-1]["full"]["classification"],
        "final_naive_class": results[-1]["naive"]["classification"],
        "final_risk_score": results[-1]["full"].get("risk_score", 0),
    }


def run_all(filter_id=None):
    with open(SCENARIOS_PATH) as f:
        data = json.load(f)

    scenarios = data["scenarios"]
    if filter_id:
        scenarios = [s for s in scenarios if s["id"] == filter_id]
        if not scenarios:
            print(f"Scenario '{filter_id}' not found.")
            sys.exit(1)

    all_results = []
    all_metrics = []

    for i, scenario in enumerate(scenarios):
        print(f"[{i+1}/{len(scenarios)}] {scenario['id']} ({scenario['scam_type']}, {len(scenario['messages'])} msgs)...", end=" ", flush=True)
        results = None
        for attempt in (1, 2):
            try:
                results = run_scenario(scenario)
                break
            except Exception as e:
                if attempt == 1:
                    print(f"retrying after: {e}...", end=" ", flush=True)
                    time.sleep(30)  # let the quota window clear
                else:
                    print(f"ERROR: {e}")
                    all_results.append({"scenario": scenario["id"], "error": str(e)})
        if results is None:
            continue
        metrics = compute_metrics(scenario, results)
        all_results.append({"scenario": scenario["id"], "results": results, "metrics": metrics})
        all_metrics.append(metrics)

        print(f"Full={metrics['final_full_class']}(score={metrics['final_risk_score']:.2f}) "
              f"Naive={metrics['final_naive_class']} "
              f"Detect: full@msg{metrics['full_detect_at_message']} naive@msg{metrics['naive_detect_at_message']} "
              f"Accuracy: full={metrics['full_accuracy']:.0%} naive={metrics['naive_accuracy']:.0%}")

    # Aggregate metrics
    if all_metrics:
        scam_metrics = [m for m in all_metrics if m["scam_type"] not in ("legitimate", "spam", "safe")]
        legit_metrics = [m for m in all_metrics if m["scam_type"] in ("legitimate", "safe")]

        aggregate = {
            "total_scenarios": len(all_metrics),
            "overall_full_accuracy": round(sum(m["full_accuracy"] for m in all_metrics) / len(all_metrics), 3),
            "overall_naive_accuracy": round(sum(m["naive_accuracy"] for m in all_metrics) / len(all_metrics), 3),
            "avg_signal_precision": round(sum(m["signal_precision"] for m in all_metrics) / len(all_metrics), 3),
            "avg_signal_recall": round(sum(m["signal_recall"] for m in all_metrics) / len(all_metrics), 3),
        }

        # First-message behavior (across all scenarios): does the system flag
        # before any evidence has accumulated?
        aggregate["full_nonsafe_on_first_message"] = sum(
            1 for m in all_metrics if m["first_full_class"] not in ("safe",))
        aggregate["naive_nonsafe_on_first_message"] = sum(
            1 for m in all_metrics if m["first_naive_class"] not in ("safe",))

        if scam_metrics:
            detect_advantages = [m["detection_advantage"] for m in scam_metrics if m["detection_advantage"] != 0]
            aggregate["scam_scenarios"] = len(scam_metrics)
            aggregate["avg_detection_advantage_msgs"] = round(sum(detect_advantages) / max(len(detect_advantages), 1), 2) if detect_advantages else 0
            aggregate["scam_caught_full"] = sum(1 for m in scam_metrics if m["final_full_class"] in ("scam", "high_risk", "suspicious", "monitoring"))
            aggregate["scam_caught_naive"] = sum(1 for m in scam_metrics if m["final_naive_class"] in ("scam", "suspicious"))

        if legit_metrics:
            aggregate["legit_scenarios"] = len(legit_metrics)
            aggregate["full_false_positives"] = sum(1 for m in legit_metrics if m["final_full_class"] not in ("safe", "monitoring"))
            aggregate["naive_false_positives"] = sum(1 for m in legit_metrics if m["final_naive_class"] not in ("safe",))

        print("\n" + "=" * 70)
        print("AGGREGATE RESULTS")
        print("=" * 70)
        for k, v in aggregate.items():
            print(f"  {k}: {v}")

        try:
            status_req = urllib.request.Request(f"{BASE}/api/status")
            with urllib.request.urlopen(status_req, timeout=10) as r:
                model = json.loads(r.read()).get("model", "unknown")
        except Exception:
            model = "unknown"

        output = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": model,
            "grading_notes": GRADING_NOTES,
            "aggregate": aggregate,
            "per_scenario": all_results,
        }

        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_PATH, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\nResults saved to {RESULTS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", help="Run a single scenario by ID")
    args = parser.parse_args()
    run_all(args.scenario)
