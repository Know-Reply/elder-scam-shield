"""ADK Agent Observability — trace tool calls, LLM reasoning, and decision paths.

Runs 3 targeted test cases through the inbound classifier with full
OpenTelemetry tracing (console + file export). Captures tool calls,
LLM reasoning steps, classification decisions, and timing per step.

Usage:
    source .venv/bin/activate && export $(cat .env | xargs) && \
    PYTHONPATH=. python evals/run_observability.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Stub Firestore before any agent imports ────────────────────────────
class _FakeFirestore:
    def Client(self, *a, **kw): return None
    def __getattr__(self, n): return None

_fs = _FakeFirestore()
sys.modules["google.cloud.firestore"] = _fs
sys.modules["google.cloud.firestore_v1"] = _fs

# ── OpenTelemetry setup (console + in-memory for file export) ──────────
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource


class InMemorySpanExporter(SpanExporter):
    """Collects spans in memory for post-run analysis and file export."""

    def __init__(self):
        self.spans: list[ReadableSpan] = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True

    def to_dicts(self) -> list[dict]:
        out = []
        for s in self.spans:
            attrs = dict(s.attributes) if s.attributes else {}
            out.append({
                "name": s.name,
                "span_id": format(s.context.span_id, "016x"),
                "trace_id": format(s.context.trace_id, "032x"),
                "parent_span_id": (
                    format(s.parent.span_id, "016x") if s.parent else None
                ),
                "start_ns": s.start_time,
                "end_ns": s.end_time,
                "duration_ms": (
                    round((s.end_time - s.start_time) / 1e6, 1)
                    if s.start_time and s.end_time else None
                ),
                "attributes": attrs,
            })
        return out


# Enable content capture in spans
os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] = "true"

memory_exporter = InMemorySpanExporter()
resource = Resource.create({"service.name": "elder-scam-shield-observability"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
# Console exporter — minimal, just shows span names + durations
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)

# ── Now import ADK + agents ────────────────────────────────────────────
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.inbound_classifier import inbound_classifier

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"

# ── Test cases ─────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "id": "obvious_scam",
        "label": "Obvious scam — advance-fee legal threat",
        "message": (
            "【緊急】あなたの口座が不正利用されています。"
            "本日中に50万円を以下の口座に振り込まないと法的措置を取ります。"
            "警察に届けても無駄です。至急対応してください。"
        ),
        "expected_classification": "scam",
        "expected_signals": ["PM-1", "PM-3", "PM-4", "PM-6"],
        "analysis_focus": "Clean reasoning trace — should be caught easily",
    },
    {
        "id": "subtle_trust_builder",
        "label": "Subtle trust-building (Day 3 of romance scam)",
        "message": (
            "花子さん、おはようございます。昨日の話、とても楽しかったです。"
            "私も横浜に住んでいて、近くの公園をよく散歩しています。"
            "今度、美味しいお茶のお店を見つけたので、一緒に行きませんか？"
            "お会いできるのを楽しみにしています。健一より"
        ),
        "expected_classification": "safe",  # Day 3 — no signals yet
        "expected_signals": [],
        "analysis_focus": (
            "How the classifier reasons about ambiguity — "
            "no explicit scam signals but romance-scam trajectory"
        ),
    },
    {
        "id": "false_positive_grandson",
        "label": "False positive — legitimate grandson asking for tuition",
        "message": (
            "おばあちゃん、ゆきです。大学の学費の締め切りが来週なんだけど、"
            "今月ちょっと足りなくて...15万円だけ貸してもらえないかな？"
            "来月のバイト代で必ず返すから。口座番号はいつものでいいよ。"
            "ごめんね、急に。"
        ),
        "expected_classification": "safe",
        "expected_signals": [],
        "analysis_focus": (
            "WHERE reasoning goes wrong — financial request + identity claim "
            "triggers signals even though this is a known grandson"
        ),
    },
]

# ── Event capture helpers ──────────────────────────────────────────────

def parse_classification(text: str) -> dict:
    """Extract classification JSON from agent response text."""
    m = re.search(r"\{[^{}]*\"classification\"[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip().strip("`").strip())
    except json.JSONDecodeError:
        return {}


class TraceCollector:
    """Collects structured trace events during a single agent run."""

    def __init__(self):
        self.events: list[dict] = []
        self.start_time: float = 0
        self.classification: dict = {}
        self.tool_calls: list[dict] = []
        self.tool_responses: list[dict] = []
        self.llm_texts: list[str] = []

    def start(self):
        self.start_time = time.time()

    def elapsed(self) -> float:
        return round(time.time() - self.start_time, 1)

    def record_tool_call(self, name: str, args: dict):
        entry = {
            "type": "tool_call",
            "time": self.elapsed(),
            "tool": name,
            "args": args,
        }
        self.events.append(entry)
        self.tool_calls.append(entry)

    def record_tool_response(self, name: str, response: dict):
        entry = {
            "type": "tool_response",
            "time": self.elapsed(),
            "tool": name,
            "response": response,
        }
        self.events.append(entry)
        self.tool_responses.append(entry)

    def record_llm_text(self, text: str):
        self.events.append({
            "type": "llm_text",
            "time": self.elapsed(),
            "text": text[:500],
        })
        self.llm_texts.append(text)

    def record_classification(self, cls: dict):
        self.classification = cls
        self.events.append({
            "type": "classification",
            "time": self.elapsed(),
            "classification": cls,
        })

    def summary_line(self) -> str:
        cls = self.classification.get("classification", "?")
        conf = self.classification.get("confidence", "?")
        signals = self.classification.get("detected_signals", [])
        corpus_matches = 0
        for tr in self.tool_responses:
            if tr["tool"] == "search_scam_corpus":
                corpus_matches = tr["response"].get("match_count", 0)
        return (
            f"FINAL: {cls} ({conf}) — "
            f"{len(signals)} signals, {corpus_matches} corpus matches"
        )


async def run_case(
    runner: Runner,
    session_service: InMemorySessionService,
    case: dict,
) -> TraceCollector:
    """Run a single test case and collect trace events."""
    collector = TraceCollector()

    session = await session_service.create_session(
        app_name="observability", user_id="user_tanaka_001"
    )
    msg = types.Content(
        role="user", parts=[types.Part(text=case["message"])]
    )

    collector.start()

    async for event in runner.run_async(
        user_id="user_tanaka_001",
        session_id=session.id,
        new_message=msg,
    ):
        if not hasattr(event, "content") or not event.content:
            continue
        if not event.content.parts:
            continue

        for part in event.content.parts:
            # ── Function calls (tool invocations) ──
            fc = getattr(part, "function_call", None)
            if fc and hasattr(fc, "name") and fc.name:
                args = dict(fc.args) if fc.args else {}
                collector.record_tool_call(fc.name, args)
                # Check for classification in tool args
                if args.get("classification"):
                    collector.record_classification(args)

            # ── Function responses ──
            fr = getattr(part, "function_response", None)
            if fr and hasattr(fr, "response"):
                resp = fr.response if isinstance(fr.response, dict) else {}
                name = fr.name if hasattr(fr, "name") and fr.name else "unknown"
                collector.record_tool_response(name, resp)
                # A2A event carries classification
                if resp.get("event") == "message.classified":
                    collector.record_classification(resp)
                elif resp.get("classification"):
                    collector.record_classification(resp)

            # ── Text responses (LLM reasoning) ──
            if hasattr(part, "text") and part.text:
                collector.record_llm_text(part.text)
                parsed = parse_classification(part.text)
                if parsed.get("classification"):
                    collector.record_classification(parsed)

    return collector


# ── Decision path inference ────────────────────────────────────────────

def infer_decision_path(collector: TraceCollector, case: dict) -> str:
    """Infer the decision path from collected trace events."""
    steps = []

    for ev in collector.events:
        if ev["type"] == "tool_call":
            if ev["tool"] == "search_scam_corpus":
                steps.append("corpus search")
            elif ev["tool"] == "read_contact_list":
                steps.append("contact lookup")
            elif ev["tool"] == "write_classification":
                steps.append("classification write")
            elif ev["tool"] == "publish_classified_event":
                steps.append("event publish")
            elif ev["tool"] == "update_graph_from_message":
                steps.append("graph update")
        elif ev["type"] == "tool_response":
            if ev["tool"] == "search_scam_corpus":
                mc = ev["response"].get("match_count", 0)
                steps.append(f"corpus evidence ({mc} matches)")
        elif ev["type"] == "classification":
            cls = ev["classification"].get("classification", "?")
            signals = ev["classification"].get("detected_signals", [])
            if signals:
                steps.append(f"signal detection ({', '.join(signals)})")
            conf = ev["classification"].get("confidence", 0)
            if isinstance(conf, (int, float)):
                if conf >= 0.8:
                    steps.append(f"high confidence -> {cls}")
                elif conf >= 0.5:
                    steps.append(f"moderate confidence -> {cls}")
                else:
                    steps.append(f"low confidence -> {cls}")

    return " -> ".join(steps) if steps else "no path captured"


def analyze_failure(collector: TraceCollector, case: dict) -> str | None:
    """Analyze where reasoning went wrong for misclassifications."""
    expected = case["expected_classification"]
    actual = collector.classification.get("classification", "?")

    if expected == actual:
        return None

    lines = []
    lines.append(f"Expected: {expected}, Got: {actual}")

    # Check specific failure modes
    signals = collector.classification.get("detected_signals", [])

    if expected == "safe" and actual in ("suspicious", "scam"):
        # False positive
        if "PM-3" in signals:
            lines.append(
                "Financial mention triggered PM-3 even though sender "
                "is a known contact (grandson)"
            )
        if "PM-11" in signals:
            lines.append(
                "Identity claim (PM-11) flagged — classifier doesn't "
                "check contact list match before flagging"
            )
        if "PM-1" in signals:
            lines.append(
                "Urgency language (PM-1) detected in what is "
                "actually a polite, normal request"
            )

        # Check if contact list was consulted
        consulted_contacts = any(
            tc["tool"] == "read_contact_list" for tc in collector.tool_calls
        )
        if not consulted_contacts:
            lines.append(
                "CRITICAL: classifier never called read_contact_list — "
                "cannot verify sender identity without it"
            )
        else:
            lines.append(
                "Contact list was consulted but classification "
                "still over-flagged — signal weights need tuning"
            )

    elif expected in ("scam", "suspicious") and actual == "safe":
        # False negative
        lines.append("Scam signals missed — classifier too lenient")

    return "\n".join(lines)


# ── Formatted output ──────────────────────────────────────────────────

def print_trace(case: dict, collector: TraceCollector):
    """Print a formatted trace for a single case."""
    print(f"\n{'=' * 60}")
    print(f"CASE: {case['id']}")
    print(f"Label: {case['label']}")
    print(f"Focus: {case['analysis_focus']}")
    print(f"{'=' * 60}")

    for ev in collector.events:
        ts = f"[{ev['time']}s]"

        if ev["type"] == "tool_call":
            # Format args concisely
            args_str = ""
            args = ev.get("args", {})
            if "message_text" in args:
                args_str = f'("{args["message_text"][:50]}...")'
            elif "classification" in args:
                args_str = (
                    f'(classification="{args["classification"]}", '
                    f'signals={args.get("detected_signals", [])})'
                )
            elif "user_id" in args and "sender_id" in args:
                args_str = f'(user={args["user_id"]}, sender={args["sender_id"]})'
            elif "user_id" in args:
                args_str = f'(user_id="{args["user_id"]}")'
            elif args:
                # Generic short form
                parts = [f'{k}="{str(v)[:30]}"' for k, v in list(args.items())[:3]]
                args_str = f'({", ".join(parts)})'

            print(f"{ts} -> {ev['tool']}{args_str}")

        elif ev["type"] == "tool_response":
            resp = ev.get("response", {})
            if ev["tool"] == "search_scam_corpus":
                mc = resp.get("match_count", 0)
                matches = resp.get("matches", [])
                match_types = []
                for m in matches[:3]:
                    label = m.get("label", "?")
                    stype = m.get("scam_type", "")
                    match_types.append(f"{label}" + (f"/{stype}" if stype else ""))
                types_str = f" ({', '.join(match_types)})" if match_types else ""
                print(f"{ts} <- {mc} matches found{types_str}")
            elif ev["tool"] == "read_contact_list":
                contacts = resp.get("contacts", [])
                names = [c.get("name", c) if isinstance(c, dict) else str(c) for c in contacts[:5]]
                print(f"{ts} <- contacts: [{', '.join(names)}]")
            elif ev["tool"] == "write_classification":
                status = resp.get("status", "?")
                print(f"{ts} <- write {status}")
            elif ev["tool"] == "publish_classified_event":
                cls = resp.get("classification", "?")
                conf = resp.get("confidence", "?")
                print(f"{ts} <- event published: {cls} ({conf})")
            elif ev["tool"] == "update_graph_from_message":
                conf = resp.get("confidence", "?")
                mc = resp.get("message_count", 0)
                print(f"{ts} <- graph updated: confidence={conf}, msgs={mc}")
            else:
                print(f"{ts} <- {ev['tool']}: {json.dumps(resp)[:100]}")

        elif ev["type"] == "llm_text":
            # Show first line of LLM text, truncated
            text = ev["text"].replace("\n", " ").strip()[:120]
            print(f"{ts} LLM: {text}")

        elif ev["type"] == "classification":
            cls = ev["classification"]
            print(
                f"{ts} CLASSIFIED: {cls.get('classification', '?')} "
                f"(confidence={cls.get('confidence', '?')}) "
                f"signals={cls.get('detected_signals', [])}"
            )

    # Summary
    print(f"\n{collector.summary_line()}")
    path = infer_decision_path(collector, case)
    print(f"DECISION PATH: {path}")

    # Failure analysis
    failure = analyze_failure(collector, case)
    if failure:
        print(f"\nFAILURE ANALYSIS:")
        for line in failure.split("\n"):
            print(f"  {line}")

    # Expected vs actual
    expected = case["expected_classification"]
    actual = collector.classification.get("classification", "?")
    match = "PASS" if expected == actual else "MISMATCH"
    print(f"\nVERDICT: {match} (expected={expected}, got={actual})")


# ── Main ───────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("ELDER SCAM SHIELD — ADK AGENT OBSERVABILITY")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Model: {inbound_classifier.model}")
    print(f"Vertex AI: {os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', 'not set')}")
    print(f"Project: {os.environ.get('GOOGLE_CLOUD_PROJECT', 'not set')}")
    print("=" * 60)

    session_service = InMemorySessionService()
    runner = Runner(
        agent=inbound_classifier,
        app_name="observability",
        session_service=session_service,
    )

    all_results = {}

    for case in TEST_CASES:
        print(f"\n--- Running: {case['id']} ---")
        try:
            collector = await run_case(runner, session_service, case)
            print_trace(case, collector)
            all_results[case["id"]] = {
                "case": {
                    "id": case["id"],
                    "label": case["label"],
                    "message": case["message"],
                    "expected_classification": case["expected_classification"],
                    "expected_signals": case["expected_signals"],
                    "analysis_focus": case["analysis_focus"],
                },
                "trace_events": collector.events,
                "classification": collector.classification,
                "tool_calls": [
                    {"tool": tc["tool"], "args": tc["args"], "time": tc["time"]}
                    for tc in collector.tool_calls
                ],
                "tool_responses": [
                    {"tool": tr["tool"], "response": tr["response"], "time": tr["time"]}
                    for tr in collector.tool_responses
                ],
                "decision_path": infer_decision_path(collector, case),
                "failure_analysis": analyze_failure(collector, case),
                "verdict": (
                    "PASS"
                    if case["expected_classification"]
                    == collector.classification.get("classification")
                    else "MISMATCH"
                ),
            }
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_results[case["id"]] = {
                "case": case,
                "error": str(e),
                "verdict": "ERROR",
            }

    # ── Collect OTel spans ─────────────────────────────────────────────
    provider.force_flush()
    otel_spans = memory_exporter.to_dicts()

    # ── Save to file ───────────────────────────────────────────────────
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = RESULTS_DIR / f"observability_traces_{ts}.json"

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": str(inbound_classifier.model),
        "vertex_ai": os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "not set"),
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT", "not set"),
        "cases": all_results,
        "otel_spans": otel_spans,
        "otel_span_count": len(otel_spans),
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'=' * 60}")
    print(f"Traces saved to {output_path}")
    print(f"Total OTel spans captured: {len(otel_spans)}")
    print(f"{'=' * 60}")

    # ── Summary table ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Case':<30} {'Expected':<12} {'Got':<12} {'Verdict':<10}")
    print("-" * 64)
    for case_id, result in all_results.items():
        if "error" in result:
            print(f"{case_id:<30} {'?':<12} {'ERROR':<12} {'ERROR':<10}")
        else:
            expected = result["case"]["expected_classification"]
            got = result["classification"].get("classification", "?")
            verdict = result["verdict"]
            print(f"{case_id:<30} {expected:<12} {got:<12} {verdict:<10}")

    return output_path


if __name__ == "__main__":
    result_path = asyncio.run(main())
