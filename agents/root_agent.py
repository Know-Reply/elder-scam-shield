"""Elder Scam Shield — Workflow-based pipeline orchestration.

Replaces the LLM-based root agent with an ADK Workflow DAG.
No LLM call is wasted on routing — deterministic FunctionNodes
handle pre-processing and conditional routing; Agent nodes handle
the LLM steps.

Pipeline:
  pre_pipeline (FunctionNode) → Inbound Classifier (Agent)
  → Behavioral Analyzer (Agent) → route (FunctionNode)
  → Family Alerter (Agent, conditional on risk > 0.6)

Event chain:
  pipeline_context → classification → risk_assessment → alert (if triggered)
"""

from google.adk.agents import Context
from google.adk.workflow import Workflow, FunctionNode, START

from .inbound_classifier import inbound_classifier
from .behavioral_analyzer import behavioral_analyzer
from .family_alerter import family_alerter
from .tools.pipeline import run_pre_classification_pipeline


# ---------------------------------------------------------------------------
# FunctionNode: Pre-LLM pipeline (Steps 1-4)
# ---------------------------------------------------------------------------

def pre_pipeline(ctx: Context):
    """Run linguistic analysis, entity extraction, corpus search, and
    graph validation BEFORE any LLM call. Writes results to session state
    so the Classifier agent can consume pre-computed evidence."""
    text = ctx.state.get("message_text", "")
    sender = ctx.state.get("sender_id", "unknown")
    user = ctx.state.get("user_id", "demo_user")
    result = run_pre_classification_pipeline(text, sender, user)
    ctx.state["pipeline_context"] = result


pre_pipeline_node = FunctionNode(func=pre_pipeline, name="pre_pipeline")


# ---------------------------------------------------------------------------
# FunctionNode: Conditional routing after behavioral analysis
# ---------------------------------------------------------------------------

def route_downstream(ctx: Context):
    """Route based on risk score. If risk > 0.6, trigger Family Alerter.
    Otherwise, pipeline ends — classification and risk data are in state."""
    risk = ctx.state.get("risk_assessment", {})
    score = risk.get("risk_score", 0) if isinstance(risk, dict) else 0
    return "alert" if score > 0.6 else "done"


route_node = FunctionNode(func=route_downstream, name="route_downstream")


# ---------------------------------------------------------------------------
# FunctionNode: No-op terminal (Workflow requires a node for every route)
# ---------------------------------------------------------------------------

def end(ctx: Context):
    """Terminal node — pipeline complete, results in session state."""
    pass


end_node = FunctionNode(func=end, name="end")


# ---------------------------------------------------------------------------
# Workflow DAG
# ---------------------------------------------------------------------------

root_agent = Workflow(
    name="elder_scam_shield",
    edges=[
        (START, pre_pipeline_node),
        (pre_pipeline_node, inbound_classifier),
        (inbound_classifier, behavioral_analyzer),
        (behavioral_analyzer, route_node),
        (route_node, {"alert": family_alerter, "done": end_node}),
    ],
)
