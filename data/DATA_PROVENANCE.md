# Data Provenance — Elder Scam Shield

Transparency about what's real, what's synthetic, and how each was produced.

---

## Corpus: 19,189 entries

### Real data (19,015 entries — 99.1%)

| Source | Entries | Language | Type | License | Method |
|---|---|---|---|---|---|
| [zefang-liu/phishing-email-dataset](https://huggingface.co/datasets/zefang-liu/phishing-email-dataset) | 17,514 | EN | Real phishing + safe emails | LGPL-3.0 | Downloaded from HuggingFace, deduplicated |
| [cybersectony/PhishingEmailDetectionv2.0](https://huggingface.co/datasets/cybersectony/PhishingEmailDetectionv2.0) | 1,254 | EN | Real phishing + legitimate emails (URL rows excluded) | Unspecified | Downloaded from HuggingFace, filtered to email-only rows |
| [フィッシング対策協議会 事例DB](https://www.antiphishing.jp/news/database/) | 203 | JA | Real Japanese phishing messages (subject lines + message bodies) | Public educational | Scraped from case pages, tagged by impersonated brand |
| [警察庁 SOS47 特殊詐欺の手口](https://www.npa.go.jp/bureau/safetylife/sos47/case/) | 44 | JA | Real NPA-published scam dialogues and scripts | Public educational | Extracted from 8 NPA pattern pages (ore-ore, deposits, cashcard, billing, refund, romance, investment, special) |

**Re-tagging (2,008 of the above):** The original datasets use binary labels
(phishing/safe). We sub-classified the 7,344 "phishing" entries into NPA-aligned
pattern categories using **deterministic regex keyword matching** — no LLM inference.
Priority-ordered patterns match specific keywords (e.g., "prince" + "inheritance" →
`advance-fee-419`; "bank" + "verify" → `fake-bank`). 5,336 entries that matched no
specific pattern were tagged `generic-scam`. The regex rules are in
`data/retag_corpus.py` and are fully reproducible.

### Synthetic data (174 entries — 0.9%)

| Source | Entries | Type | Method |
|---|---|---|---|
| `data/generate_jp_scenarios_v2.py` | 162 | Japanese NPA scam scenarios | Hand-crafted in Python by AI assistant |
| `data/generate_edge_cases.py` | 12 | Edge cases (bilingual, ambiguous) | Hand-crafted in Python by AI assistant |

**Why synthetic in addition to real data:** The NPA publishes scam dialogue scripts
and the antiphishing.jp database has real phishing messages, but these cover a
limited number of variations. We augmented the 247 real Japanese entries with
synthetic scenarios to ensure coverage across all difficulty levels (obvious,
moderate, sophisticated) and all 9 NPA patterns. We created synthetic scenarios grounded in the NPA taxonomy
to cover all 9 tokushu sagi patterns at three difficulty levels (obvious, moderate,
sophisticated) plus tricky legitimate counterparts.

**How generated:** Each message is a hardcoded string literal in a Python script,
authored by an AI assistant (Claude) with knowledge of Japanese scam patterns.
They are NOT generated at runtime by an LLM — they are static test fixtures.
The Japanese was written to be linguistically authentic (proper keigo for
institutional scams, casual form for family impersonation, age-appropriate
expressions for elderly targets).

**Limitations of synthetic data:**
- May not capture the full linguistic diversity of real scams
- Sophistication levels are the author's judgment, not empirically calibrated
- No real victim interaction patterns (response dynamics)
- Japanese phrasing reviewed for authenticity but not by native speaker victims

---

## Evaluation sets

| File | Cases | Language | Source |
|---|---|---|---|
| `evals/scam_detection.evalset.json` | 5 | Japanese | Hand-crafted (AI assistant) |
| `evals/scam_detection_full.evalset.json` | 55 | Japanese | Hand-crafted (AI assistant) |
| `evals/scam_detection_english.evalset.json` | 20 | English | Hand-crafted (AI assistant) |

All evaluation cases are **synthetic test fixtures** — hand-crafted input/output
pairs designed to test specific classification behaviors. They are not derived
from real user interactions.

---

## Signal weights

The signal weights in the Behavioral Analyzer are **derived from corpus analysis**
(`data/derive_baselines.py`). Methodology: precision-normalized P(scam|signal)
computed across all 19,104 corpus entries using keyword-based signal detection.

This means the weights are evidence-based (grounded in real phishing email data)
but the signal detection itself is heuristic (regex, not human-labeled). The
weights should be interpreted as "how discriminative is this keyword pattern in
our corpus" rather than "how often does this signal appear in real Japanese scams."

---

## What we would add with more time

1. **Real Japanese scam transcripts** — partner with NPA or consumer protection
   agencies to obtain anonymized victim reports
2. **Romance scam dialogues** — the arxiv dataset (2512.16280) promises public
   release but isn't available yet; when released, it would replace our synthetic
   romance scenarios
3. **Kaggle datasets** — the scam call conversation dataset and fraudulent email
   corpus require Kaggle authentication; adding these would increase English
   conversation coverage
4. **Human evaluation** — have native Japanese speakers and scam prevention
   experts review the synthetic scenarios for authenticity
5. **Real Faxi data** — in production, the system would be trained on actual
   messages processed by Faxi's pipeline (with user consent)
