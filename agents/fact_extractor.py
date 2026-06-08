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

## TIME REFERENCES
Convert ALL relative time references to absolute dates based on today's
date (provided below). "Tomorrow" → "2026-06-09", "next week" → "week of
2026-06-15", "this morning" → "2026-06-08 morning", "last week" → "week of
2026-06-01". Store the resolved date in the fact, not the relative word.
This prevents confusion when facts are reviewed months later.

## MATCHING AGAINST EXISTING FACTS

If EXISTING FACTS are provided below, check if any fact in the NEW MESSAGE
refers to the same entity or concept as an existing fact — even if worded
differently, abbreviated, or in a different language.

Return the EXACT fact IDs (e.g. "name:kenji", "institution:mizuho bank")
from the existing list in the matched_existing field.

IMPORTANT: Match aggressively. These are all matches:
- "Mizuho" matches "institution:mizuho bank" (abbreviation of same bank)
- "Mizuho Bank" matches "institution:mizuho bank" (exact)
- "Kenji" matches "name:kenji" or "name:健二" (same person)
- "Takeshi" matches "name:takeshi" or "name:たけし" (same person)
- "the bank" referring to previously mentioned Mizuho matches "institution:mizuho bank"
- "lives alone" matches a previous "lives alone since spouse passed" (same concept)

When in doubt, include the match. False negatives (missing a match) are
worse than false positives (matching incorrectly) for provenance tracking.

DEDUPLICATION RULE: If the NEW MESSAGE mentions a fact that already
exists in EXISTING FACTS, add its fact ID to matched_existing.
You should STILL extract all named entities (claimed_name, claimed_location,
claimed_institution) from the message — even if they match existing facts.
The matched_existing field is ADDITIONAL information, not a replacement
for extraction. Always extract. Always match. Both.
"""

fact_extractor = Agent(
    model="gemini-3.1-flash-lite",
    name="fact_extractor",
    description="Fact extraction + semantic matching for conversation knowledge graph.",
    instruction=EXTRACTOR_PROMPT,
    output_schema=ExtractedFacts,
    output_key="extracted_facts",
)
