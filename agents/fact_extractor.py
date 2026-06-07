"""Fact Extractor — lightweight entity extraction for the conversation graph.

Extracts names, locations, institutions, amounts, and relationships from
a single message. No classification, no corpus search, no tools. Just
structured fact extraction for the knowledge graph provenance tracker.

Uses the same model (flash-lite) but with a minimal prompt — ~0.5s vs ~1s
for the full classifier.
"""

from pydantic import BaseModel, Field

from google.adk import Agent
from agents.schemas import ExtractedFacts


fact_extractor = Agent(
    model="gemini-3.1-flash-lite",
    name="fact_extractor",
    description="Lightweight fact extraction — names, locations, institutions, amounts.",
    instruction="""Extract factual entities from this message. Return structured JSON.

Extract:
- claimed_name: any person's name mentioned (given name, family name, nickname)
- claimed_relationship: any relationship claim (grandson, daughter, friend, colleague)
- claimed_location: any place mentioned (city, neighborhood, country)
- claimed_institution: any organization (bank, hospital, police, company, school)
- financial_mention: any money amount with urgency level
- other_facts: notable details (lives alone, broke phone, started new job, etc.)

Extract ALL facts, even from casual messages. A message saying "I'm in Osaka"
should extract claimed_location: "Osaka". Be thorough.""",
    output_schema=ExtractedFacts,
    output_key="extracted_facts",
)
