"""Naive Classifier — baseline for Pre-ADK Tuning comparison.

Same model (gemini-3.1-flash-lite), minimal prompt, no tools, no corpus,
no pipeline context. Represents what you'd get out of the box with a
single LLM call and a basic prompt. Used by the simulator to show the
gap between raw LLM classification and the tuned Elder Shield pipeline.
"""

from google.adk import Agent
from agents.schemas import ClassificationResult

NAIVE_PROMPT = """You are a message classifier. Classify the following message as one of:
safe, suspicious, scam, or spam.

Output strict JSON:
{
  "classification": "safe|suspicious|scam|spam",
  "confidence": 0.0-1.0,
  "detected_signals": [],
  "extracted_facts": {
    "claimed_name": null,
    "claimed_relationship": null,
    "claimed_location": null,
    "claimed_institution": null,
    "financial_mention": null,
    "other_facts": []
  },
  "reasoning": "brief explanation"
}"""

naive_classifier = Agent(
    model="gemini-3.1-flash-lite",
    name="naive_classifier",
    description="Baseline single-pass classifier with no tools or domain knowledge.",
    instruction=NAIVE_PROMPT,
    output_schema=ClassificationResult,
    output_key="naive_classification",
)
