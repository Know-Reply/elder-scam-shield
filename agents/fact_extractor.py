"""Fact Extractor — LLM-based extraction + semantic matching.

One call, two jobs:
1. Extract facts from the new message
2. Match against existing facts (semantic, not string-based)

The LLM handles both — it understands "being alone" references
"lives alone", or "Mizuho" references "Mizuho Bank".
"""

from google.adk import Agent
from agents.schemas import ExtractedFacts

EXTRACTOR_PROMPT = """You perform TWO tasks on each message. Both are required.

## TASK 1: EXTRACT FACTS from the NEW MESSAGE

Identity:
- claimed_name: a SPECIFIC person's proper name. NOT titles like "Grandma",
  "Mom", "おばあちゃん". Only: "Kenji", "Takeshi", "田中".
- referenced_names: ALL OTHER proper names mentioned. Every distinct name
  must appear in claimed_name or referenced_names.
- claimed_relationship: relationship type (grandson, daughter, friend)
- claimed_location: specific places (city, country). NOT "here" or "there".
- claimed_institution: SPECIFIC organizations ("Mizuho Bank", "Tokyo Police").
  NOT generic words like "bank", "hospital".

Financial:
- financial_mention: SPECIFIC amounts only. Leave null if no amount stated.
  "How much?" is a question, not a fact.

Life facts (details a scammer could exploit):
- Employment, health, living situation, routines, relationships, vulnerabilities
- Extract BOTH explicit AND implied: "it's quiet since grandfather passed"
  → ["grandfather passed away", "lives alone"]
- Do NOT extract trivial observations

## TASK 2: MATCH AGAINST EXISTING FACTS

If EXISTING FACTS are listed below, check if the NEW MESSAGE references
any of them — even if worded differently. Return their fact IDs in
matched_existing.

Examples of what counts as a match:
- Message says "Mizuho" → matches "institution:mizuho bank" (same bank)
- Message says "being alone" → matches "life_fact:lives alone" (same concept)
- Message says "Takeshi" → matches "name:takeshi" (same person)
- Message says "your bank account" referring to Mizuho → matches "institution:mizuho bank"

When in doubt, include the match.

## EXAMPLE

EXISTING FACTS:
- name:takeshi (by elder)
- institution:mizuho bank (by elder)
- life_fact:lives alone (by elder)

NEW MESSAGE: "I worry about you being alone. Can you help from your Mizuho account?"

Correct output:
- claimed_name: null
- life_facts: ["worried about recipient being alone", "needs financial help"]
- matched_existing: ["life_fact:lives alone", "institution:mizuho bank"]

Note: "being alone" matched "lives alone" (same concept). "Mizuho account"
matched "Mizuho Bank" (same institution). The matches are semantic, not exact.

## TIME REFERENCES
Convert relative times to absolute dates using today's date (provided below).
"Tomorrow" → specific date. "Last week" → specific week.
"""

fact_extractor = Agent(
    model="gemini-3.1-flash-lite",
    name="fact_extractor",
    description="Fact extraction + semantic matching for conversation knowledge graph.",
    instruction=EXTRACTOR_PROMPT,
    output_schema=ExtractedFacts,
    output_key="extracted_facts",
)
