"""Run Elder Scam Shield evaluations — static eval sets + LLM-backed simulation.

Usage:
    python evals/run_evaluation.py                  # run all
    python evals/run_evaluation.py --static-only    # static eval cases only
    python evals/run_evaluation.py --simulation-only # simulation scenarios only

Demonstrates three hackathon criteria:
  1. Agent Evaluation  — AgentEvaluator with EvalSet + EvalConfig
  2. Agent Simulation  — LlmBackedUserSimulator with ConversationScenarios
  3. Agent Observability — OpenTelemetry tracing with console exporter
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Observability — OpenTelemetry setup (before any ADK imports)
# ---------------------------------------------------------------------------

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource

resource = Resource.create({
    "service.name": "elder-scam-shield-eval",
    "service.version": "1.0.0",
    "deployment.environment": "evaluation",
})

provider = TracerProvider(resource=resource)
console_exporter = ConsoleSpanExporter()
provider.add_span_processor(BatchSpanProcessor(console_exporter))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("elder_scam_shield.eval")

# ---------------------------------------------------------------------------
# 2. ADK evaluation imports
# ---------------------------------------------------------------------------

from google.adk.evaluation import AgentEvaluator
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_metrics import (
    EvalMetric,
    EvalMetricResult,
    PrebuiltMetrics,
)
from google.adk.evaluation.simulation.llm_backed_user_simulator import (
    LlmBackedUserSimulator,
    LlmBackedUserSimulatorConfig,
)

# Local scenario definitions
from evals.simulation_scenarios import ALL_SCENARIOS

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

EVAL_DIR = Path(__file__).parent
EVALSET_PATH = EVAL_DIR / "scam_detection.evalset.json"
EVAL_CONFIG_PATH = EVAL_DIR / "eval_config.json"
AGENT_MODULE = "agents"


def _load_eval_config() -> dict:
    """Load eval_config.json and return the criteria dict."""
    with open(EVAL_CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Static evaluation — pre-defined test cases
# ---------------------------------------------------------------------------

def run_static_evaluation() -> dict:
    """Run AgentEvaluator.evaluate() against the static evalset.

    Returns:
        Dict with per-case and aggregate metrics.
    """
    with tracer.start_as_current_span("static_evaluation") as span:
        config = _load_eval_config()
        span.set_attribute("eval.config_id", config.get("eval_config_id", ""))
        span.set_attribute("eval.num_runs", config.get("num_runs", 2))

        print("=" * 70)
        print("STATIC EVALUATION — scam_detection.evalset.json")
        print("=" * 70)

        results = AgentEvaluator.evaluate(
            agent_module=AGENT_MODULE,
            eval_dataset_file_path_or_dir=str(EVALSET_PATH),
            num_runs=config.get("num_runs", 2),
        )

        # Log results
        span.set_attribute("eval.num_cases", len(results))
        for case_id, metrics in results.items():
            with tracer.start_as_current_span(f"eval_case.{case_id}") as case_span:
                case_span.set_attribute("eval.case_id", case_id)
                for metric_name, value in metrics.items():
                    case_span.set_attribute(f"eval.metric.{metric_name}", value)
                    print(f"  [{case_id}] {metric_name}: {value}")

        print()
        return results


# ---------------------------------------------------------------------------
# Simulation evaluation — LLM-backed user simulator
# ---------------------------------------------------------------------------

def run_simulation_evaluation() -> dict:
    """Run LLM-backed simulation with ConversationScenarios.

    Returns:
        Dict with per-scenario results.
    """
    with tracer.start_as_current_span("simulation_evaluation") as span:
        print("=" * 70)
        print("SIMULATION EVALUATION — LLM-backed user scenarios")
        print("=" * 70)

        simulator_config = LlmBackedUserSimulatorConfig(
            model="gemini-2.5-flash",
            max_turns=10,
        )
        simulator = LlmBackedUserSimulator(config=simulator_config)

        all_results = {}

        for scenario in ALL_SCENARIOS:
            with tracer.start_as_current_span(
                f"simulation.{scenario.name}"
            ) as scenario_span:
                scenario_span.set_attribute("scenario.name", scenario.name)
                scenario_span.set_attribute(
                    "scenario.plan_steps", len(scenario.conversation_plan)
                )
                scenario_span.set_attribute(
                    "scenario.persona", scenario.user_persona.name
                )

                print(f"\n--- Scenario: {scenario.name} ---")
                print(f"    Persona: {scenario.user_persona.name}")
                print(f"    Plan steps: {len(scenario.conversation_plan)}")

                result = AgentEvaluator.evaluate(
                    agent_module=AGENT_MODULE,
                    eval_dataset_file_path_or_dir=str(EVALSET_PATH),
                    num_runs=1,
                    conversation_scenario=scenario,
                    user_simulator=simulator,
                )

                all_results[scenario.name] = result

                for case_id, metrics in result.items():
                    scenario_span.set_attribute(
                        f"result.{case_id}",
                        json.dumps(metrics, default=str),
                    )
                    print(f"    [{case_id}] {metrics}")

        print()
        return all_results


# ---------------------------------------------------------------------------
# Metric comparison — before/after summary
# ---------------------------------------------------------------------------

def print_metric_summary(
    static_results: dict | None, simulation_results: dict | None
) -> None:
    """Print a before/after style metric comparison."""
    config = _load_eval_config()
    criteria = config.get("criteria", {})

    print("=" * 70)
    print("METRIC SUMMARY — thresholds vs. observed")
    print("=" * 70)

    print("\nConfigured thresholds:")
    for name, spec in criteria.items():
        threshold = spec.get("threshold", "N/A")
        print(f"  {name}: {threshold}")

    if static_results:
        print("\nStatic evaluation results:")
        for case_id, metrics in static_results.items():
            print(f"  {case_id}:")
            if isinstance(metrics, dict):
                for k, v in metrics.items():
                    print(f"    {k}: {v}")
            else:
                print(f"    result: {metrics}")

    if simulation_results:
        print("\nSimulation evaluation results:")
        for scenario_name, results in simulation_results.items():
            print(f"  {scenario_name}:")
            if isinstance(results, dict):
                for k, v in results.items():
                    print(f"    {k}: {v}")
            else:
                print(f"    result: {results}")

    print("\n" + "=" * 70)
    print("Observability: OpenTelemetry spans exported to console above.")
    print("In production, replace ConsoleSpanExporter with:")
    print("  - Cloud Trace: opentelemetry-exporter-gcp-trace")
    print("  - Jaeger: opentelemetry-exporter-jaeger")
    print("  - OTLP: opentelemetry-exporter-otlp")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Elder Scam Shield — Agent Evaluation & Simulation"
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Run only static evaluation (no simulation)",
    )
    parser.add_argument(
        "--simulation-only",
        action="store_true",
        help="Run only simulation evaluation (no static cases)",
    )
    args = parser.parse_args()

    static_results = None
    simulation_results = None

    with tracer.start_as_current_span("elder_scam_shield_evaluation") as root_span:
        root_span.set_attribute("eval.evalset_path", str(EVALSET_PATH))
        root_span.set_attribute("eval.agent_module", AGENT_MODULE)

        if not args.simulation_only:
            static_results = run_static_evaluation()

        if not args.static_only:
            simulation_results = run_simulation_evaluation()

        print_metric_summary(static_results, simulation_results)

    # Flush remaining spans
    provider.force_flush()

    print("\nEvaluation complete.")


if __name__ == "__main__":
    main()
