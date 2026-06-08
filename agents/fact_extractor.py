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
- claimed_name: any person's name (given name, nickname, any language)
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

## MATCHING AGAINST EXISTING FACTS

If EXISTING FACTS are provided below, check if any extracted fact matches
an existing one semantically (same person, place, or institution — even if
worded differently). Return matched fact IDs in the matched_existing field.

Examples of matches:
- "Mizuho Bank" matches "みずほ銀行" matches "your Mizuho account"
- "Kenji" matches "健二" (same name, different script)
- "Takeshi" matches "たけし" (same name)
- "lives alone" matches "it's quiet since grandfather passed"
"""

fact_extractor = Agent(
    model="gemini-3.1-flash-lite",
    name="fact_extractor",
    description="Fact extraction + semantic matching for conversation knowledge graph.",
    instruction=EXTRACTOR_PROMPT,
    output_schema=ExtractedFacts,
    output_key="extracted_facts",
)
