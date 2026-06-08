"""Fact Extractor — LLM-based entity extraction + semantic matching.

Extracts provenance-relevant facts from a single message and matches
them against the existing fact ledger. No regex. Works in any language.

The LLM handles both extraction AND matching — it understands that
"Mizuho Bank" and "your Mizuho account" are the same institution,
or that "Kenji" and "健二" are the same person.
"""

from google.adk import Agent
from agents.schemas import ExtractedFacts

# Base instruction — the existing_facts context is appended per-call by app.py
EXTRACTOR_PROMPT = """You are a fact extractor for a conversation analysis system.

## TASK
Extract facts from the NEW MESSAGE below. Return structured JSON.

## WHAT TO EXTRACT

Identity facts:
- claimed_name: the speaker's own identity claim, or the primary person
  being discussed. One name only.
- referenced_names: ALL OTHER person names mentioned in the message.
  CRITICAL: every distinct person name that is NOT the claimed_name MUST
  go here. "Takeshi told me you were busy" → referenced_names: ["Takeshi"].
  "I talked to Takeshi and Yuko" → referenced_names: ["Takeshi", "Yuko"].
  Do NOT skip names. Every name matters for provenance tracking.
- claimed_relationship: relationship claim (grandson, daughter, friend, doctor)
- claimed_location: places (city, neighborhood, country, specific address)
- claimed_institution: organizations (bank name, hospital, police, company, school)

Financial facts:
- financial_mention: money amounts with urgency (low/medium/high)

Life facts (significant details a scammer could exploit):
- Employment: job, company, work schedule, career changes
- Health: medical conditions, hospital visits, clinic routines
- Living situation: lives alone, family moved away, spouse passed
- Daily routines: "I go to the bank on Mondays", "clinic on Tuesdays"
- Relationships: who they know, who visits, who they trust
- Vulnerabilities: loneliness, financial concerns, health worries

Do NOT extract trivial observations ("the weather is nice", "I had lunch").
Extract only facts that reveal identity, routine, relationships, or vulnerability.

## TIME REFERENCES
Convert ALL relative time references to absolute dates based on today's
date (provided below). "Tomorrow" → "2026-06-09", "next week" → "week of
2026-06-15", "this morning" → "2026-06-08 morning", "last week" → "week of
2026-06-01". Store the resolved date in the fact, not the relative word.
This prevents confusion when facts are reviewed months later.

## FOCUS
Extract facts from the NEW MESSAGE only. Do not infer or repeat facts
from previous messages. Just extract what THIS message says.
Leave matched_existing empty — matching is handled by the system.
"""

fact_extractor = Agent(
    model="gemini-3.1-flash-lite",
    name="fact_extractor",
    description="Fact extraction + semantic matching for conversation knowledge graph.",
    instruction=EXTRACTOR_PROMPT,
    output_schema=ExtractedFacts,
    output_key="extracted_facts",
)
