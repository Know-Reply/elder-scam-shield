"""Elder Scam Shield — FastAPI application entry point.

Serves the web demo, exposes the agent pipeline as REST endpoints,
and provides the 7-day demo scenario data for judges to walk through.

Designed for Cloud Run deployment with ADK Python 2.0.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.root_agent import root_agent

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Elder Scam Shield",
    description="Multi-agent scam protection for elderly Japanese users",
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

class ClassifyRequest(BaseModel):
    """Inbound message to classify."""
    sender: str
    content: str
    metadata: dict | None = None


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


# ---------------------------------------------------------------------------
# Demo page
# ---------------------------------------------------------------------------

@app.get("/demo", response_class=HTMLResponse)
async def demo():
    """Serve the interactive web demo.

    Returns the demo HTML page that visualizes the 7-day scenario,
    letting judges walk through each day and see the agent pipeline
    in action.
    """
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Elder Scam Shield</h1><p>Demo UI not built yet. "
            "Use <code>/api/demo/scenario</code> for raw scenario data.</p>",
            status_code=200,
        )
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/classify")
async def classify_message(req: ClassifyRequest):
    """Run an inbound message through the Inbound Classifier agent.

    Returns classification (safe / suspicious / scam), detected signals,
    and extracted facts from the message content.
    """
    try:
        # Build the prompt for the root agent to route to inbound_classifier
        prompt = (
            f"Classify this inbound message.\n"
            f"Sender: {req.sender}\n"
            f"Content: {req.content}"
        )
        # ADK 2.0: invoke the agent and collect the response
        response = await root_agent.ainvoke(prompt)
        return {"result": response, "sender": req.sender}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze_sender(req: AnalyzeRequest):
    """Trigger behavioral analysis for a sender.

    Runs the Behavioral Analyzer agent to update the sender's
    longitudinal profile and return the current risk assessment.
    """
    try:
        prompt = (
            f"Analyze sender profile.\n"
            f"Sender ID: {req.sender_id}\n"
            f"Message history: {json.dumps(req.message_history or [], ensure_ascii=False)}"
        )
        response = await root_agent.ainvoke(prompt)
        return {"result": response, "sender_id": req.sender_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/intercept")
async def intercept_outbound(req: InterceptRequest):
    """Check outbound content before it leaves the protected user.

    The Outbound Interceptor scans for sensitive data (bank accounts,
    passwords, large money amounts) and holds the message if the
    recipient has elevated risk.
    """
    try:
        prompt = (
            f"Check outbound message.\n"
            f"Recipient: {req.recipient}\n"
            f"Content: {req.content}\n"
            f"Risk context: {json.dumps(req.sender_risk_context or {}, ensure_ascii=False)}"
        )
        response = await root_agent.ainvoke(prompt)
        return {"result": response, "recipient": req.recipient}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/demo/scenario")
async def get_demo_scenario():
    """Return the pre-built 7-day demo scenario data.

    This is the scripted walkthrough that demonstrates how
    Elder Scam Shield detects a multi-day social engineering attack
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
