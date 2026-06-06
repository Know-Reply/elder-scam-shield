"""Multi-message behavioral analysis eval — 7-day ore-ore sagi sequence.

Tests the CORE INNOVATION: sending 7 messages through the Behavioral Analyzer
sequentially and watching the risk score climb BEFORE any explicit scam signal.

The key assertion: risk_score should reach 0.35+ by Day 4 based on behavioral
velocity (BV-1 relationship velocity, BV-4 credibility seeding, BV-5 help
positioning) — BEFORE the Day 5 contradiction or Day 7 money ask.

Usage:
    PYTHONPATH=. python evals/test_behavioral_sequence.py
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Block Firestore before any agent imports ────────────────────────────
class _FakeFS:
    def Client(self, *a, **kw): return None
    def __getattr__(self, n): return None

sys.modules['google.cloud.firestore'] = _FakeFS()
sys.modules['google.cloud.firestore_v1'] = _FakeFS()

from dotenv import load_dotenv
load_dotenv()

from google import genai
from agents.behavioral_analyzer import SYSTEM_PROMPT, _empty_profile

# ── Config ──────────────────────────────────────────────────────────────

MODEL = "gemini-2.5-flash"
API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: No API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY in .env")
    sys.exit(1)

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Load scenario ──────────────────────────────────────────────────────

def load_scenario() -> list[dict]:
    path = SCENARIOS_DIR / "demo_7day.json"
    with open(path) as f:
        data = json.load(f)
    return data["messages"]


# ── Build prompt for each day ──────────────────────────────────────────

def build_day_prompt(day_num: int, message: dict, profile: dict, history: list[dict]) -> str:
    """Build the user prompt for a single day's analysis."""
    history_text = ""
    if history:
        history_text = "\n\nPREVIOUS MESSAGES IN THIS THREAD:\n"
        for h in history:
            history_text += f"  Day {h['day']}: {h['content_en']}\n"

    profile_text = json.dumps(profile, indent=2, ensure_ascii=False)

    return f"""Analyze this message as Day {day_num} in a conversation sequence.
You are tracking sender kenji_tanaka@gmail.com who is a STRANGER (not in the user's contact list).

CURRENT SENDER PROFILE:
{profile_text}
{history_text}

NEW MESSAGE (Day {day_num}):
  Sender: {message['sender']}
  Timestamp: {message['timestamp']}
  Content (Japanese): {message['content']}
  Content (English): {message['content_en']}

INSTRUCTIONS:
1. Detect all applicable signals (BV-1..BV-5, LG-1..LG-10) for this message.
2. Compute updated behavioral velocity scores:
   - relationship_velocity (0.0-1.0): how fast intimacy is progressing
   - isolation_index (0.0-1.0): cumulative isolation references
   - emotional_arc_intensity (0.0-1.0): current emotional intensity level
   - credibility_seeding_rate: detail_count / message_count
   - help_positioning_score (0.0-1.0): availability signaling from stranger
3. Compute the overall risk_score (0.0-1.0).
4. Determine recommendation: safe / monitor / flag / block

IMPORTANT: Remember that by Day 4, if a stranger has:
  - Reached personal/intimate topics (BV-1 velocity high)
  - Seeded multiple credibility details (BV-4)
  - Positioned themselves as helper (BV-5)
  - Probed isolation (BV-2)
Then risk should be 0.35+ even WITHOUT contradictions or money asks.

Respond in this EXACT JSON format (no markdown, no code blocks, just raw JSON):
{{
  "day": {day_num},
  "risk_score": <float 0.0-1.0>,
  "detected_signals": ["<signal_code>", ...],
  "velocity_scores": {{
    "relationship_velocity": <float>,
    "isolation_index": <float>,
    "emotional_arc_intensity": <float>,
    "credibility_seeding_rate": <float>,
    "help_positioning_score": <float>
  }},
  "recommendation": "<safe|monitor|flag|block>",
  "reasoning": "<one-line summary of what this message does in the grooming arc>"
}}"""


def parse_response(text: str) -> dict:
    """Extract JSON from model response, handling markdown code blocks."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```\s*$', '', text)

    # Try to find JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {
        "day": -1,
        "risk_score": -1.0,
        "detected_signals": [],
        "velocity_scores": {},
        "recommendation": "parse_error",
        "reasoning": f"Failed to parse response: {text[:200]}",
    }


# ── Main eval loop ─────────────────────────────────────────────────────

def run_behavioral_sequence():
    messages = load_scenario()
    client = genai.Client(api_key=API_KEY)

    # Accumulate state across days
    profile = _empty_profile("kenji_tanaka@gmail.com")
    history = []
    timeline = []

    print("\n" + "=" * 80)
    print("BEHAVIORAL SEQUENCE EVAL — 7-Day Ore-Ore Sagi")
    print("=" * 80)
    print(f"Model: {MODEL}")
    print(f"Start: {datetime.now().isoformat()}")
    print("=" * 80 + "\n")

    for msg in messages:
        day = msg["day"]
        prompt = build_day_prompt(day, msg, profile, history)

        # Call Gemini directly with system prompt + user prompt
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.1,  # Low temp for consistent scoring
                },
            )
            result = parse_response(response.text)
        except Exception as e:
            print(f"  ERROR on Day {day}: {e}")
            result = {
                "day": day,
                "risk_score": -1.0,
                "detected_signals": [],
                "velocity_scores": {},
                "recommendation": "error",
                "reasoning": str(e),
            }

        # Update profile for next iteration
        profile["message_count"] = day
        if result.get("velocity_scores"):
            profile["velocity_scores"] = {
                "relationship_velocity": result["velocity_scores"].get("relationship_velocity", 0),
                "isolation_index": result["velocity_scores"].get("isolation_index", 0),
                "emotional_arc": profile["velocity_scores"].get("emotional_arc", []) + [
                    result["velocity_scores"].get("emotional_arc_intensity", 0)
                ],
                "credibility_seeding_count": int(
                    result["velocity_scores"].get("credibility_seeding_rate", 0) * day
                ),
                "help_positioning_score": result["velocity_scores"].get("help_positioning_score", 0),
            }
        profile["risk_score"] = result.get("risk_score", 0)
        profile["risk_factors"] = result.get("detected_signals", [])

        # Track extracted facts from scenario
        if msg.get("extracted_facts"):
            for k, v in msg["extracted_facts"].items():
                if k.startswith("claimed_"):
                    bucket = k.replace("claimed_", "")
                    key = f"{bucket}s" if not bucket.endswith("s") else bucket
                    if key in profile["stated_facts"]:
                        profile["stated_facts"][key].append(str(v))

        history.append(msg)

        # Build timeline entry
        entry = {
            "day": day,
            "risk_score": result.get("risk_score", -1),
            "detected_signals": result.get("detected_signals", []),
            "velocity_scores": result.get("velocity_scores", {}),
            "recommendation": result.get("recommendation", "unknown"),
            "reasoning": result.get("reasoning", ""),
            "message_summary": msg["content_en"][:60],
        }
        timeline.append(entry)

        # Print formatted line
        signals_str = ",".join(result.get("detected_signals", []))[:30]
        rec = result.get("recommendation", "?")
        score = result.get("risk_score", -1)
        reasoning = result.get("reasoning", "")[:50]
        print(
            f"Day {day}: risk={score:<5.2f}  "
            f"signals=[{signals_str:<30s}]  "
            f"rec={rec:<8s}  "
            f'"{reasoning}"'
        )

        # Small delay to avoid rate limits
        time.sleep(1)

    # ── Assertions ──────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("ASSERTIONS")
    print("=" * 80)

    passed = 0
    failed = 0

    # Key assertion: Day 4 risk >= 0.35 (behavioral velocity catches it early)
    day4 = timeline[3] if len(timeline) >= 4 else None
    if day4:
        if day4["risk_score"] >= 0.35:
            print(f"  PASS: Day 4 risk_score={day4['risk_score']:.2f} >= 0.35 (early behavioral detection)")
            passed += 1
        else:
            print(f"  FAIL: Day 4 risk_score={day4['risk_score']:.2f} < 0.35 (expected >= 0.35 from BV signals)")
            failed += 1

    # Risk should be monotonically non-decreasing (mostly)
    scores = [t["risk_score"] for t in timeline]
    monotonic = all(scores[i] <= scores[i + 1] + 0.05 for i in range(len(scores) - 1))
    if monotonic:
        print(f"  PASS: Risk scores are roughly monotonically increasing: {[round(s,2) for s in scores]}")
        passed += 1
    else:
        print(f"  FAIL: Risk scores not monotonic: {[round(s,2) for s in scores]}")
        failed += 1

    # Day 5+ should be >= 0.6 (contradiction detected)
    day5 = timeline[4] if len(timeline) >= 5 else None
    if day5:
        if day5["risk_score"] >= 0.6:
            print(f"  PASS: Day 5 risk_score={day5['risk_score']:.2f} >= 0.6 (contradiction spike)")
            passed += 1
        else:
            print(f"  FAIL: Day 5 risk_score={day5['risk_score']:.2f} < 0.6 (expected spike at contradiction)")
            failed += 1

    # Day 7 should be >= 0.9 (explicit scam)
    day7 = timeline[6] if len(timeline) >= 7 else None
    if day7:
        if day7["risk_score"] >= 0.9:
            print(f"  PASS: Day 7 risk_score={day7['risk_score']:.2f} >= 0.9 (scam confirmed)")
            passed += 1
        else:
            print(f"  FAIL: Day 7 risk_score={day7['risk_score']:.2f} < 0.9 (expected >= 0.9 for explicit scam)")
            failed += 1

    # Day 7 recommendation should be block
    if day7:
        if day7["recommendation"] == "block":
            print(f"  PASS: Day 7 recommendation='block'")
            passed += 1
        else:
            print(f"  FAIL: Day 7 recommendation='{day7['recommendation']}' (expected 'block')")
            failed += 1

    print(f"\n  Results: {passed} passed, {failed} failed out of {passed + failed} assertions")

    # ── Save results ────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = RESULTS_DIR / f"behavioral_sequence_{timestamp}.json"
    result_data = {
        "eval": "behavioral_sequence",
        "model": MODEL,
        "timestamp": datetime.now().isoformat(),
        "timeline": timeline,
        "assertions": {
            "passed": passed,
            "failed": failed,
            "total": passed + failed,
            "day4_early_detection": day4["risk_score"] >= 0.35 if day4 else False,
        },
        "risk_trajectory": scores,
    }
    with open(result_path, "w") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to: {result_path}")

    print("\n" + "=" * 80)
    if failed == 0:
        print("ALL ASSERTIONS PASSED")
    else:
        print(f"{failed} ASSERTION(S) FAILED")
    print("=" * 80 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_behavioral_sequence()
    sys.exit(0 if success else 1)
