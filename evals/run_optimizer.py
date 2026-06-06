"""Run the ADK SimplePromptOptimizer against the Elder Scam Shield eval set.

Uses Vertex AI (GOOGLE_GENAI_USE_VERTEXAI=TRUE) with InMemoryEvalSetsManager
to drive the optimization loop locally without needing a remote eval service.

Usage:
    source .venv/bin/activate
    export $(cat .env | xargs)
    PYTHONPATH=. python evals/run_optimizer.py
"""

from __future__ import annotations

# ── Firestore stub (must be before any google.cloud import) ────────────
import sys

class _FirestoreStub:
    def Client(self, *a, **kw):
        return None
    def __getattr__(self, n):
        return None

sys.modules["google.cloud.firestore"] = _FirestoreStub()
sys.modules["google.cloud.firestore_v1"] = _FirestoreStub()

# ── Real imports ───────────────────────────────────────────────────────
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from google.adk import Agent
from google.adk.evaluation.eval_case import EvalCase
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.in_memory_eval_sets_manager import InMemoryEvalSetsManager
from google.adk.optimization.local_eval_sampler import (
    LocalEvalSampler,
    LocalEvalSamplerConfig,
)
from google.adk.optimization.simple_prompt_optimizer import (
    SimplePromptOptimizer,
    SimplePromptOptimizerConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("optimizer")

# Also capture ADK internal logs at INFO
logging.getLogger("google_adk").setLevel(logging.INFO)

# ── Paths ──────────────────────────────────────────────────────────────
EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"

# ── Config ─────────────────────────────────────────────────────────────
APP_NAME = "elder_scam_shield"
EVAL_SET_ID = "scam_detection_v1"
NUM_ITERATIONS = 5
BATCH_SIZE = 5  # we only have 5 cases, use all of them each round

# Use response_match_score only — our eval set has final_response expectations
# but no strict tool trajectory to match (tools may be unavailable during
# optimization runs).
EVAL_CONFIG = EvalConfig(
    criteria={
        "response_match_score": 0.5,
    },
)


def load_eval_set() -> EvalSet:
    """Load and parse the eval set JSON."""
    path = EVALS_DIR / "scam_detection.evalset.json"
    with open(path) as f:
        data = json.load(f)
    return EvalSet(**data)


def build_agent(prompt: str) -> Agent:
    """Build a classifier agent with only pure-function tools (no Firestore)."""
    # Import tools that work without Firestore
    from agents.tools.search_scam_corpus import search_scam_corpus
    from agents.tools.graph_builder import update_graph_from_message

    # Lightweight tool stubs so the agent can still call tools the eval
    # expects without hitting Firestore.
    def read_contact_list(user_id: str) -> dict:
        """Read user's known contacts for sender verification."""
        return {"contacts": [], "blocklist": []}

    def write_classification(user_id: str, sender_id: str, message_id: str,
                             classification_result: str) -> dict:
        """Write classification result."""
        return {"status": "written"}

    def publish_classified_event(sender_id: str, classification: str,
                                 confidence: float, extracted_facts: str,
                                 detected_signals: str) -> dict:
        """Publish classification event."""
        return {"event": "message.classified", "classification": classification}

    def check_sender_risk(sender_id: str) -> dict:
        """Check sender risk score."""
        if "flagged" in sender_id:
            return {"sender_id": sender_id, "risk_score": 0.88}
        return {"sender_id": sender_id, "risk_score": 0.1}

    def check_known_payee(recipient_id: str, user_id: str) -> dict:
        """Check if recipient is a known payee."""
        return {"known": False, "recipient_id": recipient_id}

    def hold_outbound(user_id: str, held_action: str, recipient_id: str,
                      content: str, signals: list, sender_risk: float,
                      reason: str) -> dict:
        """Hold outbound message for review."""
        return {
            "hold": {"resolution": "pending"},
            "a2a_publish": {"event": "outbound.held"},
        }

    return Agent(
        model="gemini-2.0-flash",
        name="inbound_classifier",
        description=(
            "Scam-detection SENSE agent. Classifies inbound messages as "
            "safe/suspicious/scam/spam using per-message signals."
        ),
        instruction=prompt,
        tools=[
            read_contact_list,
            write_classification,
            publish_classified_event,
            search_scam_corpus,
            update_graph_from_message,
            check_sender_risk,
            check_known_payee,
            hold_outbound,
        ],
    )


def setup_eval_sets_manager(eval_set: EvalSet) -> InMemoryEvalSetsManager:
    """Create an in-memory EvalSetsManager populated with our eval set."""
    manager = InMemoryEvalSetsManager()
    manager.create_eval_set(APP_NAME, EVAL_SET_ID)

    for case in eval_set.eval_cases:
        manager.add_eval_case(APP_NAME, EVAL_SET_ID, case)

    return manager


async def run():
    ts_start = time.time()
    ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    log.info("=" * 70)
    log.info("Elder Scam Shield — ADK Prompt Optimizer (Vertex AI)")
    log.info("=" * 70)

    # ── 1. Load eval set ───────────────────────────────────────────────
    eval_set = load_eval_set()
    log.info("Loaded eval set: %s (%d cases)", EVAL_SET_ID, len(eval_set.eval_cases))
    for case in eval_set.eval_cases:
        log.info("  - %s", case.eval_id)

    # ── 2. Set up eval infrastructure ──────────────────────────────────
    manager = setup_eval_sets_manager(eval_set)

    # Load the real system prompt from the agent module
    from agents.inbound_classifier import SYSTEM_PROMPT
    initial_agent = build_agent(SYSTEM_PROMPT)
    log.info("Initial prompt length: %d chars", len(SYSTEM_PROMPT))
    log.info("Initial prompt preview: %.200s...", SYSTEM_PROMPT)

    # ── 3. Configure sampler + optimizer ───────────────────────────────
    sampler_config = LocalEvalSamplerConfig(
        eval_config=EVAL_CONFIG,
        app_name=APP_NAME,
        train_eval_set=EVAL_SET_ID,
    )
    sampler = LocalEvalSampler(config=sampler_config, eval_sets_manager=manager)

    optimizer_config = SimplePromptOptimizerConfig(
        optimizer_model="gemini-2.5-flash",
        num_iterations=NUM_ITERATIONS,
        batch_size=BATCH_SIZE,
    )
    optimizer = SimplePromptOptimizer(config=optimizer_config)

    log.info("Optimizer: %d iterations, batch_size=%d, model=%s",
             NUM_ITERATIONS, BATCH_SIZE, optimizer_config.optimizer_model)

    # ── 4. Run optimization ────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("Starting optimization loop...")
    log.info("=" * 70)

    result = await optimizer.optimize(
        initial_agent=initial_agent,
        sampler=sampler,
    )

    elapsed = time.time() - ts_start
    best = result.optimized_agents[0]
    optimized_prompt = best.optimized_agent.instruction
    final_score = best.overall_score

    # ── 5. Report ──────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("OPTIMIZATION COMPLETE")
    log.info("=" * 70)
    log.info("  Iterations:       %d", NUM_ITERATIONS)
    log.info("  Final score:      %.3f", final_score if final_score else 0.0)
    log.info("  Elapsed:          %.1f seconds", elapsed)
    log.info("  Original prompt:  %d chars", len(SYSTEM_PROMPT))
    log.info("  Optimized prompt: %d chars", len(optimized_prompt))
    log.info("")
    log.info("--- OPTIMIZED PROMPT (first 500 chars) ---")
    log.info("%.500s", optimized_prompt)
    log.info("--- END PREVIEW ---")

    # ── 6. Save results ───────────────────────────────────────────────
    RESULTS_DIR.mkdir(exist_ok=True)

    # Save optimized prompt
    prompt_path = RESULTS_DIR / f"optimized_prompt_{ts_label}.txt"
    with open(prompt_path, "w") as f:
        f.write(optimized_prompt)
    log.info("Optimized prompt saved to: %s", prompt_path)

    # Save full trace
    trace = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "num_iterations": NUM_ITERATIONS,
            "batch_size": BATCH_SIZE,
            "optimizer_model": optimizer_config.optimizer_model,
            "agent_model": "gemini-2.0-flash",
            "eval_set": EVAL_SET_ID,
            "eval_cases": [c.eval_id for c in eval_set.eval_cases],
            "eval_config_criteria": {k: v for k, v in EVAL_CONFIG.criteria.items()},
        },
        "results": {
            "final_score": final_score,
            "elapsed_seconds": round(elapsed, 1),
            "original_prompt_length": len(SYSTEM_PROMPT),
            "optimized_prompt_length": len(optimized_prompt),
        },
        "original_prompt": SYSTEM_PROMPT,
        "optimized_prompt": optimized_prompt,
    }

    trace_path = RESULTS_DIR / f"optimizer_trace_{ts_label}.json"
    with open(trace_path, "w") as f:
        json.dump(trace, f, indent=2, ensure_ascii=False, default=str)
    log.info("Optimization trace saved to: %s", trace_path)

    # ── 7. Before/after comparison ─────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("BEFORE / AFTER COMPARISON")
    log.info("=" * 70)
    log.info("  BEFORE: %d chars", len(SYSTEM_PROMPT))
    log.info("  AFTER:  %d chars (score: %.3f)", len(optimized_prompt),
             final_score if final_score else 0.0)
    log.info("")

    # Quick diff: show lines unique to optimized prompt
    orig_lines = set(SYSTEM_PROMPT.strip().splitlines())
    opt_lines = set(optimized_prompt.strip().splitlines())
    new_lines = opt_lines - orig_lines
    removed_lines = orig_lines - opt_lines
    if new_lines:
        log.info("  Lines ADDED (%d):", len(new_lines))
        for line in sorted(new_lines)[:15]:
            log.info("    + %s", line.strip()[:120])
    if removed_lines:
        log.info("  Lines REMOVED (%d):", len(removed_lines))
        for line in sorted(removed_lines)[:15]:
            log.info("    - %s", line.strip()[:120])

    log.info("=" * 70)
    log.info("Done.")


if __name__ == "__main__":
    asyncio.run(run())
