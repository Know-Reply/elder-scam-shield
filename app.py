"""Elder Shield — FastAPI application entry point.

Serves the web demo, exposes the agent pipeline as REST endpoints,
and provides the 7-day demo scenario data for judges to walk through.

Designed for Cloud Run deployment with ADK Python 2.0.
"""

import json
import os
import re
import sys
from pathlib import Path

# Firestore optional for local dev
class _FakeFS:
    def Client(self, *a, **kw): return None
    def __getattr__(self, n): return None
# Always stub Firestore for demo — use FIRESTORE_ENABLED=true to connect for real
if os.environ.get("FIRESTORE_ENABLED", "").lower() != "true":
    sys.modules['google.cloud.firestore'] = _FakeFS()
    sys.modules['google.cloud.firestore_v1'] = _FakeFS()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from agents.root_agent import root_agent
from agents.inbound_classifier import inbound_classifier
from agents.naive_classifier import naive_classifier
from agents.fact_extractor import fact_extractor
from agents.outbound_interceptor import outbound_interceptor
from agents.tools.pipeline import run_pre_classification_pipeline, victim_state_analysis
from agents.tools.conversation_graph import process_conversation_turn

# Load .env if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ADK runners for live inference
_session_service = InMemorySessionService()

# Classifier runner — fast path for interactive simulator (1 LLM call)
_classifier_runner = Runner(
    agent=inbound_classifier,
    app_name="elder_scam_shield",
    session_service=_session_service,
)

# Fact extractor — lightweight extraction for conversation analyzer (no tools, no corpus)
_extractor_runner = Runner(
    agent=fact_extractor,
    app_name="elder_scam_shield_extractor",
    session_service=_session_service,
)

# Naive classifier — baseline for Pre-ADK comparison (no tools, no corpus)
_naive_runner = Runner(
    agent=naive_classifier,
    app_name="elder_scam_shield_naive",
    session_service=_session_service,
)

# Full pipeline runner — Workflow DAG for /api/pipeline (pre-processing → classification → behavioral analysis → routing)
_pipeline_runner = Runner(
    agent=root_agent,
    app_name="elder_scam_shield",
    session_service=_session_service,
)

# Outbound interception runner — separate flow for user replies
_intercept_runner = Runner(
    agent=outbound_interceptor,
    app_name="elder_scam_shield",
    session_service=_session_service,
)

# Session cache — reuse sessions per user for longitudinal state
_session_cache: dict[str, str] = {}


async def _get_or_create_session(user_id: str, state: dict | None = None) -> object:
    """Reuse existing session or create new one with optional initial state."""
    if user_id in _session_cache:
        session = await _session_service.get_session(
            app_name="elder_scam_shield",
            user_id=user_id,
            session_id=_session_cache[user_id],
        )
        if session:
            # Update state with new message data
            if state:
                for k, v in state.items():
                    session.state[k] = v
            return session
    session = await _session_service.create_session(
        app_name="elder_scam_shield",
        user_id=user_id,
        state=state or {},
    )
    _session_cache[user_id] = session.id
    return session

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Elder Shield",
    description="Multi-agent scam protection for the elderly",
    version="0.1.0",
)

# CORS — open for demo; tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (demo UI assets)
STATIC_DIR = Path(__file__).parent / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Demo scenario data path
SCENARIO_PATH = Path(__file__).parent / "scenarios" / "demo_7day.json"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class EmailAuthMetadata(BaseModel):
    """Email authentication results from the mail server."""
    spf: str | None = None        # "pass" | "fail" | "softfail" | "none"
    dkim: str | None = None       # "pass" | "fail" | "none"
    dmarc: str | None = None      # "pass" | "fail" | "none"


class ClassifyRequest(BaseModel):
    """Inbound email to classify.

    Compatible with Faxi's inbound email pipeline. Accepts either:
    - Production format: {from_address, subject, body, auth}
    - Simulator format: {sender, content}
    """
    # Production email fields
    from_address: str | None = None
    subject: str | None = None
    body: str | None = None
    auth: EmailAuthMetadata | None = None

    # Simulator fallback fields
    sender: str | None = None
    content: str | None = None

    @property
    def effective_sender(self) -> str:
        return self.from_address or self.sender or "unknown"

    @property
    def effective_content(self) -> str:
        parts = []
        if self.subject:
            parts.append(self.subject)
        if self.body:
            parts.append(self.body)
        if parts:
            return "\n".join(parts)
        return self.content or ""

    @property
    def has_auth_failure(self) -> bool:
        if not self.auth:
            return False
        return self.auth.spf == "fail" or self.auth.dkim == "fail"


class AnalyzeRequest(BaseModel):
    """Trigger behavioral analysis for a sender."""
    sender_id: str
    message_history: list[dict] | None = None


class InterceptRequest(BaseModel):
    """Outbound content to check before sending."""
    recipient: str
    content: str
    sender_risk_context: dict | None = None


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check for Cloud Run readiness/liveness probes."""
    return {
        "status": "healthy",
        "service": "elder-scam-shield",
        "agent": root_agent.name,
    }


@app.get("/api/status")
async def system_status():
    """System status for integration monitoring.

    Returns pipeline version, corpus size, model, and capabilities.
    A production system checks this before routing traffic.
    """
    return {
        "service": "elder-scam-shield",
        "version": "1.0.0",
        "pipeline": "v2_8step",
        "model": "gemini-3.1-flash-lite",
        "corpus_entries": 22979,
        "signal_families": 4,
        "signal_count": 20,
        "agents": ["inbound-classifier", "behavioral-analyzer", "outbound-interceptor", "family-alerter"],
        "api": {
            "classify": {"method": "POST", "path": "/api/classify", "accepts": "email or message"},
            "pipeline": {"method": "POST", "path": "/api/pipeline", "accepts": "email or message"},
            "intercept": {"method": "POST", "path": "/api/intercept", "accepts": "outbound content"},
        },
        "integration": {
            "compatible_with": "Faxi inboundEmailPipeline.ts",
            "replaces": "spamCheckService.checkEmail()",
            "input_format": {"from_address": "string", "subject": "string", "body": "string", "auth": {"spf": "pass|fail", "dkim": "pass|fail", "dmarc": "pass|fail"}},
        },
    }


# ---------------------------------------------------------------------------
# Demo page
# ---------------------------------------------------------------------------

@app.get("/shield", response_class=HTMLResponse)
@app.get("/demo", response_class=HTMLResponse)
async def shield():
    """Main landing page — the walkthrough with real eval data."""
    path = Path(__file__).parent / "web" / "demo-walkthrough.html"
    if not path.exists():
        return HTMLResponse(content="<h1>Demo not built yet.</h1>", status_code=200)
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@app.get("/analyzer", response_class=HTMLResponse)
async def analyzer():
    """Conversation Analyzer — knowledge graph provenance demo."""
    path = Path(__file__).parent / "web" / "analyzer.html"
    if not path.exists():
        return HTMLResponse(content="<h1>Analyzer not built yet.</h1>", status_code=200)
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@app.get("/technical", response_class=HTMLResponse)
async def technical():
    """Technical deep dive — architecture, research, benchmarks."""
    path = Path(__file__).parent / "web" / "technical.html"
    if not path.exists():
        return HTMLResponse(content="<h1>Technical page not built yet.</h1>", status_code=200)
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@app.get("/simulator", response_class=HTMLResponse)
async def simulator():
    """Interactive scam simulator — choose-your-adventure style."""
    path = Path(__file__).parent / "web" / "index.html"
    if not path.exists():
        return HTMLResponse(content="<h1>Simulator not built yet.</h1>", status_code=200)
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the Family Safety Dashboard.

    Interactive dashboard showing quarantine inbox, risk timeline,
    contact network, and protection summary — the human-in-the-loop
    proof for family guardians.
    """
    path = Path(__file__).parent / "web" / "dashboard.html"
    if not path.exists():
        return HTMLResponse(
            content="<h1>Elder Shield</h1><p>Dashboard not built yet.</p>",
            status_code=200,
        )
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/classify")
async def classify_message(req: ClassifyRequest):
    """Classify an inbound message via the Inbound Classifier agent.

    Fast path for the interactive simulator — runs only the classifier
    (1 LLM call). Pre-processing (Steps 1-4) runs as Python before the
    LLM call, and results are injected into the prompt as context.
    For the full pipeline including behavioral analysis, use /api/pipeline.
    """
    try:
        sender = req.effective_sender
        content = req.effective_content

        # Flag SPF/DKIM failures as PM-13 before pipeline
        auth_signal = ""
        if req.has_auth_failure:
            auth_signal = "\nPM-13 detected: email authentication failure (SPF/DKIM)."

        # Steps 1-4: pre-LLM pipeline (~50ms, no API calls)
        pipeline_ctx = run_pre_classification_pipeline(
            content, sender, "demo_user"
        )

        # Get or create session — retrieve existing graph state
        session = await _get_or_create_session("demo_user", {
            "message_text": content,
            "sender_id": sender,
            "user_id": "demo_user",
            "pipeline_context": pipeline_ctx,
        })

        # Include existing graph context in prompt (from prior turns)
        existing_graph = session.state.get("knowledge_graph", {})
        existing_signals = existing_graph.get("graph_signals", {})
        graph_context = ""
        if existing_signals.get("echo_grounded_identity"):
            graph_context = "\nWARNING: Sender's identity claim is echo-grounded — built from facts the elder revealed first."
        if existing_signals.get("echo_ratio", 0) > 0.5:
            graph_context += f"\nEcho ratio: {existing_signals['echo_ratio']} — sender is mostly repeating elder's own information."

        prompt = (
            f"新着メッセージを分析してください。送信者: {sender}, "
            f"ユーザーID: demo_user\n\n「{content}」\n\n"
            f"Pre-computed pipeline context:\n{json.dumps(pipeline_ctx, ensure_ascii=False, default=str)}"
            f"{auth_signal}{graph_context}"
        )
        msg = genai_types.Content(
            role="user", parts=[genai_types.Part(text=prompt)]
        )

        result = {"classification": "no_response"}
        async for event in _classifier_runner.run_async(
            user_id="demo_user", session_id=session.id, new_message=msg
        ):
            if not (hasattr(event, "content") and event.content and event.content.parts):
                continue
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    text = part.text.strip()
                    if text.startswith("```"):
                        text = re.sub(r'^```\w*\s*', '', text)
                        text = re.sub(r'\s*```$', '', text)
                    start = text.find("{")
                    if start >= 0:
                        depth = 0
                        end = start
                        for i in range(start, len(text)):
                            if text[i] == "{": depth += 1
                            elif text[i] == "}": depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                        try:
                            parsed = json.loads(text[start:end])
                            if parsed.get("classification"):
                                result = parsed
                        except json.JSONDecodeError:
                            pass
                fc = getattr(part, "function_call", None)
                if fc and hasattr(fc, "args") and fc.args:
                    args = fc.args
                    if args.get("classification"):
                        result.update({
                            k: args[k] for k in
                            ("classification", "confidence",
                             "detected_signals", "extracted_facts",
                             "reasoning")
                            if k in args
                        })

        # Read structured output from session state (via output_key)
        updated = await _session_service.get_session(
            app_name="elder_scam_shield",
            user_id="demo_user",
            session_id=session.id,
        )
        if updated and updated.state.get("classification"):
            state_result = updated.state["classification"]
            if isinstance(state_result, dict) and state_result.get("classification"):
                result = state_result

        if "reasoning" not in result:
            result["reasoning"] = ""

        # Update conversation knowledge graph with LLM-extracted facts
        llm_facts = result.get("extracted_facts", {})
        if llm_facts:
            turn_index = len(session.state.get("fact_ledger", {}).get("turns", []))
            graph_update = process_conversation_turn(
                content, "inbound", turn_index,
                session_state=session.state,
                extracted_facts=llm_facts,
            )
            session.state["fact_ledger"] = graph_update["fact_ledger"]
            session.state["epistemic_state"] = graph_update["epistemic_state"]
            session.state["knowledge_graph"] = graph_update["knowledge_graph"]

        return {"result": result, "sender": sender, "live": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/classify-naive")
async def classify_naive(req: ClassifyRequest):
    """Baseline classification — no tools, no corpus, no pipeline context.

    Same model (flash-lite), minimal prompt. Represents what you'd get
    out of the box before any ADK tuning. Used by the simulator for the
    Pre-ADK Tuning column.
    """
    try:
        session = await _session_service.create_session(
            app_name="elder_scam_shield_naive", user_id="demo_user"
        )
        msg = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=f"Classify this message:\n\n{req.effective_content}")],
        )
        result = {"classification": "safe", "confidence": 0.5, "detected_signals": [], "reasoning": ""}
        async for event in _naive_runner.run_async(
            user_id="demo_user", session_id=session.id, new_message=msg
        ):
            if not (hasattr(event, "content") and event.content and event.content.parts):
                continue
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    text = part.text.strip()
                    if text.startswith("```"):
                        text = re.sub(r'^```\w*\s*', '', text)
                        text = re.sub(r'\s*```$', '', text)
                    start = text.find("{")
                    if start >= 0:
                        depth = 0
                        end = start
                        for i in range(start, len(text)):
                            if text[i] == "{": depth += 1
                            elif text[i] == "}": depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                        try:
                            parsed = json.loads(text[start:end])
                            if parsed.get("classification"):
                                result = parsed
                        except json.JSONDecodeError:
                            pass

        # Read from session state (output_key)
        updated = await _session_service.get_session(
            app_name="elder_scam_shield_naive",
            user_id="demo_user",
            session_id=session.id,
        )
        if updated and updated.state.get("naive_classification"):
            state_result = updated.state["naive_classification"]
            if isinstance(state_result, dict) and state_result.get("classification"):
                result = state_result

        if "reasoning" not in result:
            result["reasoning"] = ""
        return {"result": result, "sender": req.effective_sender, "live": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline")
async def run_full_pipeline(req: ClassifyRequest):
    """Run the full Workflow pipeline: pre-processing → classification
    → behavioral analysis → conditional routing to Family Alerter.

    This is the complete multi-agent pipeline that judges can evaluate.
    Results are written to session state via output_key on each agent.
    """
    try:
        sender = req.effective_sender
        content = req.effective_content
        session = await _get_or_create_session("demo_user", {
            "message_text": content,
            "sender_id": sender,
            "user_id": "demo_user",
        })
        prompt = (
            f"新着メッセージを分析してください。送信者: {sender}, "
            f"ユーザーID: demo_user\n\n「{content}」"
        )
        msg = genai_types.Content(
            role="user", parts=[genai_types.Part(text=prompt)]
        )
        async for event in _pipeline_runner.run_async(
            user_id="demo_user", session_id=session.id, new_message=msg
        ):
            pass

        updated = await _session_service.get_session(
            app_name="elder_scam_shield",
            user_id="demo_user",
            session_id=session.id,
        )
        state = updated.state if updated else {}
        return {
            "classification": state.get("classification", {}),
            "risk_assessment": state.get("risk_assessment", {}),
            "alert": state.get("alert"),
            "tool_traces": state.get("tool_traces", []),
            "sender": sender,
            "pipeline": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze_sender(req: AnalyzeRequest):
    """Trigger behavioral analysis via the full pipeline.

    Runs the Workflow to update the sender's longitudinal profile
    and return the current risk assessment from session state.
    """
    try:
        session = await _get_or_create_session("demo_user", {
            "sender_id": req.sender_id,
            "user_id": "demo_user",
        })
        prompt = (
            f"Analyze sender profile.\n"
            f"Sender ID: {req.sender_id}\n"
            f"Message history: {json.dumps(req.message_history or [], ensure_ascii=False)}"
        )
        msg = genai_types.Content(
            role="user", parts=[genai_types.Part(text=prompt)]
        )
        async for event in _pipeline_runner.run_async(
            user_id="demo_user", session_id=session.id, new_message=msg
        ):
            pass
        updated = await _session_service.get_session(
            app_name="elder_scam_shield",
            user_id="demo_user",
            session_id=session.id,
        )
        result = updated.state.get("risk_assessment", {}) if updated else {}
        return {"result": result, "sender_id": req.sender_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/intercept")
async def intercept_outbound(req: InterceptRequest):
    """Check outbound content before it leaves the protected user.

    Uses the Outbound Interceptor agent (separate from the inbound
    Workflow) to scan for sensitive data and make hold/release decisions.
    """
    try:
        session = await _get_or_create_session("demo_user", {
            "sender_id": req.recipient,
            "user_id": "demo_user",
        })

        # Update epistemic state (structural — no LLM needed) before interceptor
        turn_index = len(session.state.get("fact_ledger", {}).get("turns", []))
        graph_update = process_conversation_turn(
            req.content, "outbound", turn_index,
            session_state=session.state,
            extracted_facts=None,  # facts come after LLM
        )
        session.state["epistemic_state"] = graph_update["epistemic_state"]

        # Build epistemic context for the interceptor
        graph_signals = graph_update.get("graph_signals", {})
        epistemic_context = (
            f"Elder trust stage: {graph_signals.get('trust_stage', 'unknown')}. "
            f"Friction: {graph_signals.get('friction_score', '?')} ({graph_signals.get('friction_trajectory', '?')}). "
            f"Echo ratio: {graph_signals.get('echo_ratio', 0)}."
        )

        prompt = (
            f"Check outbound message.\n"
            f"Recipient: {req.recipient}\n"
            f"Content: {req.content}\n"
            f"Risk context: {json.dumps(req.sender_risk_context or {}, ensure_ascii=False)}\n\n"
            f"Conversation graph: {epistemic_context}"
        )
        msg = genai_types.Content(
            role="user", parts=[genai_types.Part(text=prompt)]
        )
        async for event in _intercept_runner.run_async(
            user_id="demo_user", session_id=session.id, new_message=msg
        ):
            pass
        updated = await _session_service.get_session(
            app_name="elder_scam_shield",
            user_id="demo_user",
            session_id=session.id,
        )
        result = updated.state.get("intercept_decision", {}) if updated else {}
        result["graph_signals"] = graph_signals
        return {"result": result, "recipient": req.recipient}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConversationTurnRequest(BaseModel):
    """Single conversation turn for knowledge graph analysis."""
    content: str
    direction: str  # "inbound" or "outbound"
    turn_index: int = 0
    session_id: str = "analyzer"


# In-memory graph state per analyzer session
_analyzer_states: dict[str, dict] = {}


@app.post("/api/conversation/turn")
async def conversation_turn(req: ConversationTurnRequest):
    """Process a single conversation turn through the knowledge graph.

    Calls the classifier LLM to extract facts (multilingual, context-aware),
    then feeds them into the provenance-tracking knowledge graph.
    """
    state = _analyzer_states.get(req.session_id, {})

    # Call lightweight fact extractor (no classification, no tools, ~0.5s)
    extracted_facts = {}
    try:
        session = await _session_service.create_session(
            app_name="elder_scam_shield_extractor", user_id="analyzer"
        )

        # Build prompt with existing facts for semantic matching
        existing_ledger = state.get("fact_ledger", {}).get("facts", {})
        existing_context = ""
        if existing_ledger:
            fact_list = [f"{fid}: {f['value']} (by {f['first_stated_by']})"
                        for fid, f in existing_ledger.items()]
            existing_context = "\n\nEXISTING FACTS (match against these):\n" + "\n".join(fact_list)

        msg = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=f"NEW MESSAGE:\n{req.content}{existing_context}")],
        )
        async for event in _extractor_runner.run_async(
            user_id="analyzer", session_id=session.id, new_message=msg
        ):
            pass
        updated = await _session_service.get_session(
            app_name="elder_scam_shield_extractor", user_id="analyzer", session_id=session.id,
        )
        if updated and updated.state.get("extracted_facts"):
            ef = updated.state["extracted_facts"]
            if isinstance(ef, dict):
                extracted_facts = ef
    except Exception:
        pass  # If LLM fails, graph still updates epistemic state structurally

    # Update knowledge graph with LLM-extracted facts
    result = process_conversation_turn(
        req.content, req.direction, req.turn_index, state,
        extracted_facts=extracted_facts if extracted_facts else None,
    )

    _analyzer_states[req.session_id] = result
    return {
        "fact_ledger": result["fact_ledger"],
        "epistemic_state": result["epistemic_state"],
        "knowledge_graph": result["knowledge_graph"],
        "graph_signals": result["graph_signals"],
        "extracted_facts": extracted_facts,
    }


@app.post("/api/conversation/reset")
async def conversation_reset(session_id: str = "analyzer"):
    """Reset the conversation graph state for a new analysis."""
    _analyzer_states.pop(session_id, None)
    return {"status": "reset"}


@app.get("/api/dashboard/data")
async def dashboard_data():
    """Return dashboard data from seed file (or Firestore in production)."""
    path = Path(__file__).parent / "data" / "dashboard_seed.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dashboard seed data not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/demo/scenario")
async def get_demo_scenario():
    """Return the pre-built 7-day demo scenario data.

    This is the scripted walkthrough that demonstrates how
    Elder Shield detects a multi-day social engineering attack
    against an elderly Japanese user.
    """
    if not SCENARIO_PATH.exists():
        raise HTTPException(status_code=404, detail="Demo scenario file not found")
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return data


# ---------------------------------------------------------------------------
# Entry point (local dev / Cloud Run)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
