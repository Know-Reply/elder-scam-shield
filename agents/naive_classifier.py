"""Faxi Production Classifier — the real baseline for Pre-ADK comparison.

This replicates Faxi's actual spamCheckService.ts prompt and behavior:
same model (gemini-2.5-flash-lite), same minimal prompt, same 3 categories,
no tools, no corpus, no signals, no behavioral analysis.

The simulator uses this to show what Faxi's production classifier sees
vs what Elder Shield's ADK-tuned pipeline sees.
"""

from google.adk import Agent
from .schemas import ClassificationResult

# Mirrors Faxi's spamCheckService.buildPrompt() — same wording, same rules
FAXI_PROMPT = """You are a spam and safety classifier for an email-to-fax service used by elderly Japanese users.

Classify the following message into one of these categories:
- "spam": unsolicited marketing, bulk advertising, adult content, malware links
- "scam": targeted fraud, impersonation, credential theft, emotional manipulation, phishing
- "safe": personal correspondence, business communication, newsletters the user may have signed up for, transactional emails (receipts, confirmations)

RULES:
- When in doubt, lean toward "safe" — false positives (blocking legitimate email) are worse than false negatives (letting borderline email through)

Output strict JSON with classification (use "suspicious" for borderline scam signals), confidence 0.0-1.0, detected_signals (empty list), extracted_facts, and reasoning."""

naive_classifier = Agent(
    model="gemini-2.5-flash-lite",
    name="naive_classifier",
    description="Faxi production classifier — same model, minimal prompt, no tools or domain knowledge.",
    instruction=FAXI_PROMPT,
    output_schema=ClassificationResult,
    output_key="naive_classification",
)
