# Corpus Validation Report

Generated from 22979 entries across 6 source files.

---

## 1. Deduplication

- Total entries: 22979
- Unique texts: 22837
- Exact duplicates found: 142
- Duplicates by source: {'antiphishing_corpus.jsonl': 140, 'conversation_corpus.jsonl': 2}
- Sample duplicates (first 5):
  - `antiphish_0054_s0` from `antiphishing_corpus.jsonl` duplicates entry #19036
  - `antiphish_0076_s0` from `antiphishing_corpus.jsonl` duplicates entry #19049
  - `antiphish_0139_s0` from `antiphishing_corpus.jsonl` duplicates entry #19036
  - `antiphish_0273_s0` from `antiphishing_corpus.jsonl` duplicates entry #19075
  - `antiphish_0299_s0` from `antiphishing_corpus.jsonl` duplicates entry #19075

**Deduplicated corpus: 22837 entries**

## 2. Tag Quality Audit

Spot-check of 50 random entries per source for NPA pattern tag accuracy.

| `BothBosu/multi-agent-scam-conversation` | 50 sampled | 48 correct | 2 questionable | **96% accuracy** |
| `BothBosu/scam-dialogue` | 50 sampled | 42 correct | 8 questionable | **84% accuracy** |
| `antiphishing.jp` | 50 sampled | 49 correct | 1 questionable | **98% accuracy** |
| `cybersectony/PhishingEmailDetectionv2.0` | 50 sampled | 47 correct | 3 questionable | **94% accuracy** |
| `npa.go.jp/sos47` | 44 sampled | 35 correct | 9 questionable | **80% accuracy** |
| `synthetic_edge` | 12 sampled | 12 correct | 0 questionable | **100% accuracy** |
| `synthetic_npa_v2` | 50 sampled | 41 correct | 9 questionable | **82% accuracy** |
| `zefang-liu/phishing-email-dataset` | 50 sampled | 48 correct | 2 questionable | **96% accuracy** |

## 3. Channel Distribution

| Channel | Count | % |
|---|---|---|
| email | 19,185 | 84.0% |
| phone | 3,242 | 14.2% |
| sms | 236 | 1.0% |
| unknown | 174 | 0.8% |

## 4. Signal Coverage Matrix

Entries containing each signal (keyword-based detection).

| Signal | Count | Status |
|---|---|---|
| CM-1 | 3,042 | OK |
| CM-2 | 356 | OK |
| CM-3 | 1,279 | OK |
| CM-4 | 39 | OK |
| LG-1 | 1,333 | OK |
| LG-10 | 3,402 | OK |
| LG-2 | 2,122 | OK |
| LG-3 | 991 | OK |
| LG-4 | 1,459 | OK |
| LG-5 | 650 | OK |
| LG-6 | 1,696 | OK |
| LG-7 | 135 | OK |
| LG-8 | 710 | OK |
| LG-9 | 3,596 | OK |
| OB-1 | 4,190 | OK |
| OB-2 | 4,705 | OK |
| OB-3 | 3,564 | OK |
| OB-4 | 4,716 | OK |
| OB-5 | 5,073 | OK |
| PM-1 | 2,343 | OK |
| PM-10 | 463 | OK |
| PM-11 | 413 | OK |
| PM-12 | 3,709 | OK |
| PM-13 | 8 | **UNDERTRAINED (8)** |
| PM-2 | 582 | OK |
| PM-3 | 4,804 | OK |
| PM-4 | 3,390 | OK |
| PM-5 | 606 | OK |
| PM-6 | 1,516 | OK |
| PM-7 | 1,802 | OK |
| PM-8 | 1,323 | OK |
| PM-9 | 885 | OK |

**Undertrained signals (<10 examples): 1** — PM-13

## 5. NPA Pattern Coverage

| Pattern | Count | Status |
|---|---|---|
| generic-scam | 5,336 | OK |
| credential-phishing | 917 | OK |
| gov-impersonation | 805 | OK |
| lottery-prize | 557 | OK |
| refund-scam | 524 | OK |
| advance-fee-419 | 432 | OK |
| fake-police | 364 | OK |
| fake-bank | 291 | OK |
| fictitious-billing | 260 | OK |
| romance-scam | 193 | OK |
| impersonation | 84 | OK |
| ore-ore-sagi | 22 | **UNDERCOVERED (22)** |
| fake-grandchild | 19 | **UNDERCOVERED (19)** |
| phishing | 2 | **UNDERCOVERED (2)** |
| cash-card | 1 | **UNDERCOVERED (1)** |
| investment-fraud | 1 | **UNDERCOVERED (1)** |

**Undercovered patterns (<50 examples): 5** — ore-ore-sagi, fake-grandchild, phishing, cash-card, investment-fraud

## 6. Signal Weight Recalibration

| Signal | Old Weight | New Weight | Delta |
|---|---|---|---|
| PM-1 | 0.0865 | 0.0844 | -0.0021 |
| PM-10 | 0.0614 | 0.0603 | -0.0011 |
| PM-11 | 0.0676 | 0.0853 | +0.0177 |
| PM-12 | 0.0726 | 0.0712 | -0.0014 |
| PM-13 | 0.0000 | 0.0000 | +0.0000 |
| PM-2 | 0.0811 | 0.0797 | -0.0014 |
| PM-3 | 0.0802 | 0.0788 | -0.0014 |
| PM-4 | 0.0765 | 0.0751 | -0.0014 |
| PM-5 | 0.1123 | 0.1103 | -0.0020 |
| PM-6 | 0.0604 | 0.0592 | -0.0012 |
| PM-7 | 0.1052 | 0.1032 | -0.0020 |
| PM-8 | 0.0865 | 0.0849 | -0.0016 |
| PM-9 | 0.1096 | 0.1076 | -0.0020 |

## 7. Legitimate Message Baseline

| Label | Count | % |
|---|---|---|
| safe | 13,056 | 57.2% |
| scam | 9,781 | 42.8% |

**✓ Legitimate baseline adequate: 57.2% (13,056 entries)**

---

## Summary

- **Corpus size:** 22,837 (after dedup from 22,979)
- **Duplicates removed:** 142
- **Undertrained signals:** 1 (PM-13)
- **Undercovered patterns:** 5 (ore-ore-sagi, fake-grandchild, phishing, cash-card, investment-fraud)
- **Legitimate baseline:** 57.2%
- **Channels:** {'email': 19185, 'sms': 236, 'unknown': 174, 'phone': 3242}