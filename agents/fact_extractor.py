"""Fact Extractor — LLM-based extraction + semantic matching.

One call, two jobs:
1. Extract facts from the new message
2. Match against existing facts (semantic, not string-based)

The LLM handles both — it understands "being alone" references
"lives alone", or "Mizuho" references "Mizuho Bank".
"""

from google.adk import Agent
from .schemas import ExtractedFacts

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

## TASK 3: ELDER STATE ANALYSIS (outbound messages only)

If the message is from the ELDER (outbound), assess their psychological state.
If the message is from the SENDER (inbound), leave elder_state at defaults.

Detect five signals — each is "none", "mild", or "strong":

**compliance** — Is the elder agreeing to do what the sender asks?
- none: no agreement, neutral response
- mild: tentative agreement, "maybe", "I'll think about it"
- strong: clear agreement, "understood", "I'll do it", "of course", asking "what should I do?"

**resistance** — Is the elder challenging or pushing back?
- none: no challenge
- mild: hesitation, "are you sure?", asking for clarification
- strong: direct challenge, "prove it", "who are you really?", "I need to verify"

**disclosure** — Is the elder revealing personal information?
- none: generic response, no personal details
- mild: mentions a name or general area
- strong: bank details, routines, living situation, health, financial details

**emotional_engagement** — Is the elder emotionally invested in the sender?
- none: neutral, factual response
- mild: polite concern, "that's nice"
- strong: deep concern FOR the sender, "are you okay?", "I'm worried about you"

**instruction_seeking** (boolean) — Is the elder asking the sender what to do?
This is a key compliance signal: the elder is yielding decision-making control.
"What should I do?" / "How much?" / "Where do I send it?" = true

Also detect which VS (Victim State) signal codes are present in detected_signals:
- VS-1 compliance_acceptance — agreeing to requests, accepting instructions
- VS-2 secrecy_adoption — agreeing to keep the conversation secret from family
- VS-3 financial_commitment — stating intent to send money, go to bank, buy cards.
      NOT triggered by "spend time" or non-financial uses of "spend".
- VS-4 emotional_capitulation — reassuring the sender, expressing concern FOR them
- VS-5 urgency_mirroring — adopting the sender's sense of urgency or deadlines
- VS-6 question_cessation — not asking questions anymore (compared to earlier)
- VS-7 deference_shift — becoming more formal or submissive

Examples:
- "Kenji? Oh my! How have you been?" → compliance:none, resistance:none, disclosure:none, emotional:mild, instruction:false, detected_signals:[]
- "Oh no! Are you okay? What should I do?" → compliance:strong, resistance:none, disclosure:none, emotional:strong, instruction:true, detected_signals:["VS-1","VS-4"]
- "I'm fine. I go to Mizuho Bank on Mondays." → compliance:none, resistance:none, disclosure:strong, emotional:none, instruction:false, detected_signals:[]
- "Understood. I'll go to the bank now. I won't tell anyone." → compliance:strong, resistance:none, disclosure:none, emotional:none, instruction:false, detected_signals:["VS-1","VS-2","VS-3"]
- "Who are you? I don't recognize this number." → compliance:none, resistance:strong, disclosure:none, emotional:none, instruction:false, detected_signals:[]
"""

fact_extractor = Agent(
    model="gemini-2.5-flash-lite",
    name="fact_extractor",
    description="Fact extraction + semantic matching for conversation knowledge graph.",
    instruction=EXTRACTOR_PROMPT,
    output_schema=ExtractedFacts,
    output_key="extracted_facts",
)
