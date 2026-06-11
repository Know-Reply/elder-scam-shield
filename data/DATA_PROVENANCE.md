# Data Provenance -- Elder Scam Shield

Transparency about what's real, what's synthetic, and how each was produced.

---

## Corpus: 22,979 entries (22,837 after deduplication)

### Real data (22,568 entries -- 98.2%)

| Source | Entries | Language | Type | License | Method |
|---|---|---|---|---|---|
| [zefang-liu/phishing-email-dataset](https://huggingface.co/datasets/zefang-liu/phishing-email-dataset) | 17,514 | EN | Real phishing + safe emails | LGPL-3.0 | Downloaded from HuggingFace, deduplicated |
| [cybersectony/PhishingEmailDetectionv2.0](https://huggingface.co/datasets/cybersectony/PhishingEmailDetectionv2.0) | 1,254 | EN | Real phishing + legitimate emails (URL rows excluded) | Unspecified | Downloaded from HuggingFace, filtered to email-only rows |
| [antiphishing.jp](https://www.antiphishing.jp/news/database/) | 203 | JA | Real Japanese phishing messages (subject lines + message bodies) | Public educational | Scraped from case pages, tagged by impersonated brand |
| [NPA SOS47 dialogues](https://www.npa.go.jp/bureau/safetylife/sos47/case/) | 44 | JA | Real NPA-published scam dialogues and scripts | Public educational | Extracted from 8 NPA pattern pages (ore-ore, deposits, cashcard, billing, refund, romance, investment, special) |
| [BothBosu/scam-dialogue](https://huggingface.co/datasets/BothBosu/scam-dialogue) | 1,600 | EN | Multi-turn phone call transcripts (scam + safe) | Apache 2.0 | Downloaded from HuggingFace. Synthetic (Llama 3 70B). 4 scam types + 4 safe types. |
| [BothBosu/multi-agent-scam-conversation](https://huggingface.co/datasets/BothBosu/multi-agent-scam-conversation) | 1,600 | EN | Multi-turn conversations with 8 personality types | Apache 2.0 | Downloaded from HuggingFace. Synthetic (AutoGen). Same types + personality dimension. |

**Re-tagging (2,008 of the above):** The original datasets use binary labels
(phishing/safe). We sub-classified the 7,344 "phishing" entries into NPA-aligned
pattern categories using **deterministic regex keyword matching** -- no LLM inference.
Priority-ordered patterns match specific keywords (e.g., "prince" + "inheritance" ->
`advance-fee-419`; "bank" + "verify" -> `fake-bank`). 5,336 entries that matched no
specific pattern were tagged `generic-scam`. The regex rules are in
`data/retag_corpus.py` and are fully reproducible.

### Synthetic data (174 entries -- 0.8%)

| Source | Entries | Type | Method |
|---|---|---|---|
| `data/generate_jp_scenarios_v2.py` | 162 | Japanese NPA scam scenarios | Hand-crafted in Python by AI assistant |
| `data/generate_edge_cases.py` | 12 | Edge cases (bilingual, ambiguous) | Hand-crafted in Python by AI assistant |

**Why synthetic in addition to real data:** The NPA publishes scam dialogue scripts
and the antiphishing.jp database has real phishing messages, but these cover a
limited number of variations. We augmented the 247 real Japanese entries with
synthetic scenarios to ensure coverage across all difficulty levels (obvious,
moderate, sophisticated) and all 9 NPA patterns.

**How generated:** Each message is a hardcoded string literal in a Python script,
authored by an AI assistant (Claude) with knowledge of Japanese scam patterns.
They are NOT generated at runtime by an LLM -- they are static test fixtures.
The Japanese was written to be linguistically authentic (proper keigo for
institutional scams, casual form for family impersonation, age-appropriate
expressions for elderly targets).

**Limitations of synthetic data:**
- May not capture the full linguistic diversity of real scams
- Sophistication levels are the author's judgment, not empirically calibrated
- No real victim interaction patterns (response dynamics)
- Japanese phrasing reviewed for authenticity but not by native speaker victims

---

## Data pipeline components

### Corpus Search (`agents/tools/search_scam_corpus.py`)

Grounding tool that connects to Vertex AI Search (production) or falls back to
local JSONL-based search using Jaccard similarity (development). Every
classification becomes evidence-backed: "this pattern matches N confirmed cases"
instead of "my prompt says so." Searches across 6 corpus files.

### Social Graph Builder (`agents/tools/graph_builder.py`)

Infers contact networks from communication patterns. Closes the loop between
fact extraction and graph validation:

1. Classifier extracts facts from every message (name, relationship, location)
2. Graph builder accumulates those facts into sender profiles
3. Profiles that meet confidence thresholds become graph nodes
4. Cross-references between contacts create verified edges
5. The graph strengthens with every message

8 confidence levels: VERIFIED, OBSERVED, ESTABLISHED, RECOGNIZED, CORROBORATED,
INFERRED, CLAIMED, UNCONNECTED. Auto-promotion to contact occurs at ESTABLISHED
or higher. Cross-references are tracked bidirectionally -- when sender A mentions
person B, and sender C also mentions person B, person B gains RECOGNIZED status.

### Graph Validation (`agents/tools/social_graph.py`)

Pre-screening step for the Behavioral Analyzer. Checks whether a sender has
ANY connection to the user's known contact graph. Graph distance determines
trust modifiers:

| Distance | Modifier | Meaning |
|---|---|---|
| 0 (direct, 12+ months) | -0.2 | Known contact, long history |
| 0 (direct, <12 months) | -0.1 | Known contact, short history |
| 1 (friend-of-friend) | 0.0 | Neutral |
| -1 (no connection, no claim) | +0.1 | Unknown sender |
| -1 (no connection, claims relationship) | +0.3 | Imposter signal |

---

## Adversarial test scenarios (`scenarios/adversarial_edge_cases.json`)

12 adversarial scenarios across 4 categories, developed through a structured
adversarial design review:

| Category | Count | Runnable | Honest-Fails |
|---|---|---|---|
| A: Legitimate-looking scammy | 3 | 3 | 0 |
| B: Sophisticated evasions | 4 | 2 | 2 |
| C: System trust collapse | 3 | 1 | 2 |
| D: Discipline collision | 2 | 1 | 1 |

The 3 documented honest-fails (cross-platform persona, LLM-cloned voice,
self-fulfilling fear loop) are architectural boundaries, not bugs. Each
includes a hostile_question_defense explaining what the system can and
cannot do about it.

---

## Evaluation sets

| File | Cases | Language | Source |
|---|---|---|---|
| `evals/scam_detection.evalset.json` | 5 | Japanese | Hand-crafted (AI assistant) |
| `evals/scam_detection_full.evalset.json` | 55 | Japanese | Hand-crafted (AI assistant) |
| `evals/scam_detection_english.evalset.json` | 20 | English | Hand-crafted (AI assistant) |

All evaluation cases are **synthetic test fixtures** -- hand-crafted input/output
pairs designed to test specific classification behaviors. They are not derived
from real user interactions.

The 80-case eval suite runs live Gemini inference (not cached). Results are
stored in `evals/results/` with timestamps.

---

## Signal weights

The signal weights in the Behavioral Analyzer are **derived from corpus analysis**
(`data/derive_baselines.py`). Methodology: precision-normalized P(scam|signal)
computed across all corpus entries using keyword-based signal detection.

This means the weights are evidence-based (grounded in real phishing email data)
but the signal detection itself is heuristic (regex, not human-labeled). The
weights should be interpreted as "how discriminative is this keyword pattern in
our corpus" rather than "how often does this signal appear in real Japanese scams."

BV (behavioral velocity) and EA (elder abuse) signals are structurally defined --
they require multi-message context that single-entry corpora cannot capture.
Their weights are set by architectural reasoning, not corpus statistics.

---

## Corpus validation

Full validation report in [CORPUS_VALIDATION_REPORT.md](CORPUS_VALIDATION_REPORT.md).

Summary:
- **22,837 unique entries** (142 exact duplicates removed from 22,979)
- **Label distribution:** 57.2% safe, 42.8% scam
- **Tag accuracy:** 80-100% across sources (spot-checked 50 per source)
- **Undertrained signals:** 1 (PM-13, 8 examples)
- **Undercovered NPA patterns:** 5 (ore-ore-sagi, fake-grandchild, phishing, cash-card, investment-fraud -- all <50 examples)
- **Channel distribution:** 84% email, 14% phone, 1% SMS, <1% unknown

---

## What we would add with more time

1. **Real Japanese scam transcripts** -- partner with NPA or consumer protection
   agencies to obtain anonymized victim reports
2. **Romance scam dialogues** -- the arxiv dataset (2512.16280) promises public
   release; when released, it would replace our synthetic romance scenarios
3. **Multi-channel data** -- LINE, SMS, and fax message corpora to train
   cross-channel pattern detection
4. **Human evaluation** -- have native Japanese speakers and scam prevention
   experts review the synthetic scenarios for authenticity
5. **Real Faxi data** -- in production, the system would be trained on actual
   messages processed by Faxi's pipeline (with user consent)
6. **Longitudinal conversation corpora** -- multi-turn, multi-day conversation
   datasets to directly validate BV and EA signal weights

---

## Adversarial design review

The adversarial edge cases and family alerter UX went through a structured
adversarial design review (2026-06-06) covering alert design, dignity
preservation, and adversarial scenario coverage.
