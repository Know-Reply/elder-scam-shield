# Elder Scam Shield — Domain Model

Foundational domain model for the 4-agent ADK scam protection system.
All downstream agent code, test scenarios, and demo flows derive from this document.

---

## 1. Scam Pattern Taxonomy

Nine NPA tokushu sagi (特殊詐欺) patterns. Each pattern maps to detection strategies
and agent responsibilities defined in Sections 2 and 3.

### 1.1 Impersonation Fraud (オレオレ詐欺)

- **Slug:** `ore-ore-sagi`
- **Attack vector:** Single-shot (though may span 2-3 calls/messages)
- **How it works:** Scammer calls/messages claiming to be a family member (son, grandson) in urgent trouble — car accident, arrest, workplace mistake. Demands immediate cash transfer. Often uses crying or panicked voice/tone in text.
- **Detection signals:** Claimed identity vs. known contacts mismatch, extreme urgency language (今すぐ, 急いで), secrecy demands (誰にも言わないで), unusual payment method, first contact from unknown sender claiming existing relationship.
- **Typical duration:** Minutes to hours. Single interaction or same-day follow-up.
- **Stats (2024):** Subset of overall tokushu sagi. Historically the largest category; now overtaken by police impersonation. Victims 65+ comprise ~65% of all tokushu sagi cases.

### 1.2 Fake Grandchild (孫を装った詐欺)

- **Slug:** `fake-grandchild`
- **Attack vector:** Single-shot to short trust-building (1-3 days)
- **How it works:** Variant of ore-ore targeting grandparents specifically. Emotional appeal — "おばあちゃん、健二だよ" — followed by crisis narrative. May involve a second caller posing as lawyer/police.
- **Detection signals:** Grandchild name mismatch against contacts, emotional manipulation language, crisis escalation within first interaction, request for cash pickup or bank transfer, involvement of claimed "authority" figure.
- **Typical duration:** Hours to 3 days.
- **Stats:** Subtype of ore-ore. Primary demo scenario (7-day timeline in demo flow uses this as base pattern extended to trust-building duration).

### 1.3 Fictitious Billing (架空請求)

- **Slug:** `fictitious-billing`
- **Attack vector:** Single-shot
- **How it works:** Fake invoices for services never used — unpaid subscription fees, membership renewals, content access charges. Often references legal action if unpaid.
- **Detection signals:** Unknown billing entity, no prior transaction history, legal threat language (法的措置, 裁判), payment deadline pressure, unusual payment methods (convenience store payment, gift cards), generic addressee.
- **Typical duration:** Single message. Follow-ups if victim engages.
- **Stats (2024):** 5,716 cases (~10% increase YoY). Largest category by case count.

### 1.4 Refund Scams (還付金詐欺)

- **Slug:** `refund-sagi`
- **Attack vector:** Single-shot
- **How it works:** Claims victim is owed a tax refund, insurance reimbursement, or medical fee return. Directs victim to ATM or requests bank details to "process the refund." The refund framing lowers guard because victim expects to receive, not send.
- **Detection signals:** Unsolicited refund notification, request to visit ATM, bank detail solicitation framed as "verification," claimed government/insurance source from non-official sender, time-limited refund window.
- **Typical duration:** Single interaction. Urgency tied to artificial deadline.
- **Stats (2024):** 4,070 cases (slight decrease YoY).

### 1.5 Lottery/Prize Fraud (当選通知詐欺)

- **Slug:** `lottery-prize`
- **Attack vector:** Single-shot
- **How it works:** "You won" notification requiring fee payment to claim prize. Processing fees, tax prepayment, shipping charges. Victim never entered any lottery.
- **Detection signals:** Prize notification with no prior entry, upfront fee requirement, unknown sender, too-good-to-be-true amounts, urgency to claim before expiry, request for personal details to "verify identity."
- **Typical duration:** Single message with follow-up pressure.
- **Stats:** Lower volume than billing/refund. Often delivered via fax or postal mail to elderly.

### 1.6 Fake Bank Notices (銀行なりすまし)

- **Slug:** `fake-bank`
- **Attack vector:** Single-shot
- **How it works:** Impersonates bank requesting account verification, security update, or card reissuance. Requests login credentials, card numbers, PINs. May reference real bank names.
- **Detection signals:** Sender domain mismatch with claimed bank, credential/PIN solicitation, "security update" framing, link to non-bank domain, SPF/DKIM failure (already caught by Faxi's existing gate), urgency around account suspension.
- **Typical duration:** Single message.
- **Stats:** Significant overlap with phishing. Often caught by existing email security (SPF/DKIM/DMARC).

### 1.7 Government Impersonation (役所なりすまし)

- **Slug:** `gov-impersonation`
- **Attack vector:** Single-shot
- **How it works:** Fake notices from city hall (市役所), tax office (税務署), pension bureau (年金事務所). Claims unpaid taxes, pension issues, My Number card problems. Initial contact by NPA study: 46.4% of fraud impersonates government officials.
- **Detection signals:** Government entity claim from non-official sender, My Number / pension number solicitation, payment demand for "administrative fees," threat of legal consequences, official-sounding but non-standard communication channel.
- **Typical duration:** Single interaction.
- **Stats:** 46.4% of initial fraud contact impersonates government officials (PMC9358277).

### 1.8 Romance/Friendship Fraud (ロマンス詐欺)

- **Slug:** `romance-sagi`
- **Attack vector:** Trust-building (days to months)
- **How it works:** Builds fake emotional relationship over extended period. Phases: Hook (initial contact, persona establishment) → Line (trust deepening, daily contact, future plans) → Sinker (crisis requiring money). Uses personalized flattery, mirroring, trauma-bonding, compliance conditioning, future dream construction.
- **Detection signals:**
  - **Early (Day 1-3):** New unknown sender initiating personal relationship, rapid intimacy escalation, flattery density above baseline.
  - **Mid (Day 3-5):** Daily contact pattern establishment, personal disclosure solicitation, location/identity contradictions accumulating.
  - **Late (Day 5+):** Crisis narrative introduction, first financial mention, urgency escalation, isolation language ("don't tell anyone, this is between us").
  - **Cross-phase:** Stated fact contradictions over time, frequency escalation pattern, emotional manipulation progression.
- **Typical duration:** 7-30 days for email/message-based. Can extend months.
- **Stats (2024):** Part of social media fraud category: 10,237 cases, ¥127.2B losses, average ¥13.6M per case. Nearly tripled YoY. Highest per-case loss of any category.

### 1.9 Fake Police (警察なりすまし)

- **Slug:** `fake-police`
- **Attack vector:** Single-shot (with possible same-day follow-up)
- **How it works:** Impersonates police claiming victim's account is linked to criminal activity, or that their card has been used fraudulently. Instructs victim to transfer funds to "safe account" or surrender cash/cards to a collector.
- **Detection signals:** Police/law enforcement claim from non-official channel, "safe account" transfer request, card surrender instruction, case number that cannot be verified, threat of arrest, demand for secrecy from family.
- **Typical duration:** Hours. Often involves coordinated phone + in-person collection.
- **Stats (2024):** 4,261 cases (>400% increase YoY). Fastest-growing category. Part of the ¥98.5B figure cited for 2025.

---

## 2. Detection Signal Inventory

Every signal the system can detect, organized by detection modality.

### 2.1 Per-Message Signals

Detectable from a single inbound message without historical context.

| # | Signal | Description | Detecting Agent | False-Positive Risk |
|---|--------|-------------|-----------------|---------------------|
| PM-1 | `urgency_language` | Extreme time pressure keywords: 今すぐ, 急いで, 本日中に, 至急 | Inbound Classifier | Medium — legitimate urgent messages exist |
| PM-2 | `secrecy_demand` | Requests to not tell family/others: 誰にも言わないで, 内緒で | Inbound Classifier | Low — rare in legitimate messages |
| PM-3 | `financial_solicitation` | Explicit money request, bank transfer instruction, amount mention | Inbound Classifier | Medium — legitimate invoices trigger |
| PM-4 | `authority_claim` | Claims to be police, government, bank from non-verified sender | Inbound Classifier | Low — domain/sender verification anchors this |
| PM-5 | `unusual_payment_method` | Gift card, cryptocurrency, convenience store payment, 振込 to unknown account | Inbound Classifier | Low |
| PM-6 | `legal_threat` | Lawsuit, arrest, legal action language: 法的措置, 訴訟, 逮捕 | Inbound Classifier | Low — legitimate legal communications are rare for elderly users |
| PM-7 | `credential_solicitation` | Requests for passwords, PINs, My Number, bank account numbers | Inbound Classifier | Low |
| PM-8 | `prize_notification` | Unsolicited winning/prize claim with fee requirement | Inbound Classifier | Low |
| PM-9 | `refund_lure` | Unsolicited refund offer requiring bank details or ATM visit | Inbound Classifier | Low |
| PM-10 | `emotional_crisis` | Accident, hospitalization, arrest narrative with financial resolution: 事故, 入院, 逮捕された | Inbound Classifier | Medium — real emergencies use similar language |
| PM-11 | `identity_claim` | Sender claims specific relationship (grandson, son, official) | Inbound Classifier | N/A — not a risk signal alone, feeds Behavioral Analyzer |
| PM-12 | `flattery_density` | Abnormally high compliment/praise ratio in message | Inbound Classifier | Medium — some legitimate senders are effusive |
| PM-13 | `spf_dkim_fail` | Email authentication failure | Inbound Classifier (pre-pipeline) | Low — strong technical signal |

### 2.2 Longitudinal Signals

Require sender profile built across multiple messages over time.

| # | Signal | Description | Detecting Agent | False-Positive Risk |
|---|--------|-------------|-----------------|---------------------|
| LG-1 | `stated_fact_contradiction` | Sender's claimed facts contradict previous claims (location, job, relationship) | Behavioral Analyzer | Low — contradictions are strong signal |
| LG-2 | `contact_identity_mismatch` | Claimed name/relationship does not match user's known contacts | Behavioral Analyzer | Low — anchored to verified contact list |
| LG-3 | `frequency_escalation` | Message frequency accelerating over days (0→1→1→2→3) | Behavioral Analyzer | Medium — legitimate new relationships also escalate |
| LG-4 | `emotional_progression` | Measurable shift from casual → intimate → urgent/desperate over message sequence | Behavioral Analyzer | Medium — requires calibration |
| LG-5 | `financial_mention_timing` | First money mention appears after trust-building period (day 5+ of contact) | Behavioral Analyzer | Low — strong romance scam indicator |
| LG-6 | `isolation_language_trend` | Increasing requests to keep communication private across messages | Behavioral Analyzer | Low |
| LG-7 | `persona_inconsistency` | Writing style, formality level, or language proficiency shifts between messages | Behavioral Analyzer | Medium — people adapt register |
| LG-8 | `crisis_after_trust` | Emergency/crisis narrative appearing only after established rapport | Behavioral Analyzer | Low — strong trust-building scam indicator |
| LG-9 | `rapid_intimacy` | Relationship depth (disclosed personal details, future plans) advancing faster than baseline for contact type | Behavioral Analyzer | Medium |
| LG-10 | `compliance_conditioning` | Pattern of small requests escalating to larger ones across messages | Behavioral Analyzer | Medium |

### 2.3 Cross-Modal Signals

Require correlating conversation data with spending/action data.

| # | Signal | Description | Detecting Agent | False-Positive Risk |
|---|--------|-------------|-----------------|---------------------|
| CM-1 | `conversation_spending_correlation` | Financial request in conversation followed by outbound transfer action within short window | Behavioral Analyzer + Outbound Interceptor | Low — direct causal link |
| CM-2 | `amount_matches_request` | Transfer amount matches amount mentioned in recent inbound message from flagged sender | Outbound Interceptor | Low |
| CM-3 | `payment_to_new_recipient` | Outbound payment to recipient never transacted with before, correlated with recent scam-flagged conversation | Outbound Interceptor | Medium — legitimate first-time payments exist |
| CM-4 | `urgency_amount_compound` | High urgency score in conversation + large transfer amount + high sender risk score | Outbound Interceptor | Low — compound signal reduces FP |

### 2.4 Outbound Signals

Detected in user's own outgoing messages/actions.

| # | Signal | Description | Detecting Agent | False-Positive Risk |
|---|--------|-------------|-----------------|---------------------|
| OB-1 | `pii_in_response` | User sending personal identifiable information (name, address, My Number) in reply | Outbound Interceptor | Medium — user may legitimately share with known contacts |
| OB-2 | `bank_details_in_response` | User sending bank account number, card number, or PIN in reply | Outbound Interceptor | Low — almost never legitimate via email/fax |
| OB-3 | `transfer_instruction` | User composing wire transfer or payment instruction | Outbound Interceptor | Medium — context-dependent (sender risk score gates this) |
| OB-4 | `response_to_flagged_sender` | User replying to sender with elevated risk score | Outbound Interceptor | N/A — triggers enhanced scrutiny, not block alone |
| OB-5 | `compliance_language` | User's reply shows acquiescence patterns: わかりました, すぐに送ります, 言わないでおきます | Outbound Interceptor | Medium — normal agreement language, gated by sender risk |

---

## 3. Agent Responsibility Matrix

### 3.1 Inbound Classifier

| Dimension | Detail |
|-----------|--------|
| **ADK primitives** | SENSE |
| **Signals detected** | PM-1 through PM-13 (all per-message signals) |
| **Memory Bank reads** | User's contact list (for PM-11 initial check), sender blocklist |
| **Memory Bank writes** | Raw extracted facts per message (name, relationship, location, institution, amount, urgency), classification label (spam/scam/safe), confidence score |
| **A2A publishes** | `message.classified` event with: sender_id, classification, confidence, extracted_facts[], detected_signals[] |
| **A2A subscribes** | None (entry point) |
| **Gemini model** | `gemini-2.0-flash` — low latency for per-message gate. Japanese language + scam pattern recognition. |
| **Primary detector for** | `fictitious-billing`, `lottery-prize`, `fake-bank`, `refund-sagi` (single-shot patterns with strong per-message signals) |
| **Secondary role for** | All patterns — first-pass extraction for every inbound message |

### 3.2 Behavioral Analyzer

| Dimension | Detail |
|-----------|--------|
| **ADK primitives** | INTERPRET + JUDGE |
| **Signals detected** | LG-1 through LG-10 (all longitudinal signals), CM-1 (conversation-spending correlation) |
| **Memory Bank reads** | Sender profile (full history), user contact list, previous risk assessments |
| **Memory Bank writes** | Updated sender profile: stated_facts accumulation, contradiction_count, contact_frequency array, risk_score, risk_factors[] |
| **A2A publishes** | `sender.risk_updated` event with: sender_id, risk_score, risk_factors[], contradiction_details[], recommendation (monitor/flag/block) |
| **A2A subscribes** | `message.classified` from Inbound Classifier |
| **Gemini model** | `gemini-2.5-pro` — complex reasoning over multi-message profiles, contradiction detection, temporal pattern analysis. Higher latency acceptable (not on hot path). |
| **Primary detector for** | `romance-sagi`, `fake-grandchild`, `ore-ore-sagi` (trust-building and identity-based patterns requiring longitudinal analysis) |
| **Secondary role for** | `gov-impersonation`, `fake-police` (identity claim verification against contacts) |

### 3.3 Outbound Interceptor

| Dimension | Detail |
|-----------|--------|
| **ADK primitives** | JUDGE |
| **Signals detected** | OB-1 through OB-5 (all outbound signals), CM-2 through CM-4 (cross-modal signals) |
| **Memory Bank reads** | Sender risk score for reply recipient, recent inbound message context, user's known payees |
| **Memory Bank writes** | Hold record: held_action, reason, evidence_summary, timestamp, resolution (released/blocked) |
| **A2A publishes** | `outbound.held` event with: action_type, recipient_sender_id, risk_evidence[], held_content_hash (not content itself — "never show content" principle) |
| **A2A subscribes** | `sender.risk_updated` from Behavioral Analyzer, outbound action stream from Faxi pipeline |
| **Gemini model** | `gemini-2.0-flash` — low latency for real-time interception gate. PII/financial detail pattern matching. |
| **Primary detector for** | All patterns at the outbound stage — last line of defense before victim sends money/data |
| **Unique capability** | Operates between conversation and transaction — the gap that banks and email providers cannot cover |

### 3.4 Family Alerter

| Dimension | Detail |
|-----------|--------|
| **ADK primitives** | CREATE |
| **Signals detected** | None directly — consumes risk assessments and hold events |
| **Memory Bank reads** | Family contact preferences, notification history (dedup/rate-limit), user profile (name, preferred language) |
| **Memory Bank writes** | Notification record: alert_id, timestamp, recipient, delivery_status, response_action |
| **A2A publishes** | `alert.delivered` event with: alert_id, family_member_id, delivery_channel, response_deadline |
| **A2A subscribes** | `sender.risk_updated` (when risk_score exceeds threshold), `outbound.held` from Outbound Interceptor |
| **Gemini model** | `gemini-2.0-flash` — template-based generation of warm, non-technical Japanese notifications. Low latency for time-sensitive alerts. |
| **Primary detector for** | None — this agent creates, it does not detect |
| **Unique capability** | Human-in-the-loop bridge. Translates technical evidence into actionable family notifications. Bilingual (Japanese primary, English secondary). |

### Agent-to-Pattern Coverage Matrix

| Pattern | Primary Detector | Secondary | Outbound Gate |
|---------|-----------------|-----------|---------------|
| `ore-ore-sagi` | Behavioral Analyzer | Inbound Classifier | Outbound Interceptor |
| `fake-grandchild` | Behavioral Analyzer | Inbound Classifier | Outbound Interceptor |
| `fictitious-billing` | Inbound Classifier | — | Outbound Interceptor |
| `refund-sagi` | Inbound Classifier | — | Outbound Interceptor |
| `lottery-prize` | Inbound Classifier | — | Outbound Interceptor |
| `fake-bank` | Inbound Classifier | — | Outbound Interceptor |
| `gov-impersonation` | Inbound Classifier | Behavioral Analyzer | Outbound Interceptor |
| `romance-sagi` | Behavioral Analyzer | Inbound Classifier | Outbound Interceptor |
| `fake-police` | Inbound Classifier | Behavioral Analyzer | Outbound Interceptor |

---

## 4. Data Source Inventory

### 4.1 Romance Scam Dialogue Dataset

- **Source:** https://arxiv.org/html/2512.16280v1
- **What it provides:** 250 synthetic seven-day conversations modeling Hook (initial contact, filtration) and Line (trust-building, persona maintenance) phases. 30-50 dialogue turns per day. Includes manipulation tactics: personalized flattery, compliance conditioning, trauma-bonding, authority performance, future dream construction. Human-expert validated (3 romance-baiting specialists reviewed 40% of dialogues).
- **How to use in build:**
  - **Testing:** Primary test corpus for Behavioral Analyzer's longitudinal detection. Each conversation is a 7-day scenario mapping directly to the demo flow.
  - **Training prompts:** Extract manipulation tactic examples for few-shot prompt engineering in Inbound Classifier and Behavioral Analyzer.
  - **Demo scenarios:** The 7-day romance scam timeline in the demo directly mirrors this dataset's structure.
- **Limitations:** Synthetic (GPT-4 generated, not real victim transcripts). English-only — requires translation/adaptation for Japanese patterns. Models romance scam only, not other tokushu sagi types. CC license terms may apply.

### 4.2 Scam Call Conversation Dataset

- **Source:** https://www.kaggle.com/datasets/teeconnie/scam-and-non-scam-call-conversation-dataset
- **What it provides:** 800 conversations (400 scam, 400 non-scam). Anonymized with placeholders for PII. Mix of real reports and synthetic augmentation. Non-scam includes banking, travel, healthcare conversations — some intentionally scam-adjacent for harder negative cases.
- **How to use in build:**
  - **Testing:** False-positive calibration — run non-scam conversations through Inbound Classifier to verify safe classification. Scam conversations for true-positive validation.
  - **Training prompts:** Extract scam conversation patterns for few-shot examples. The anonymized format (placeholders) maps cleanly to fact extraction testing.
  - **Demo scenarios:** Source for Scene 1 (obvious scam) demo variants.
- **Limitations:** English-only. Call transcripts, not email/fax format — requires adaptation. CC BY-NC-ND 4.0 license restricts derivative works. No Japan-specific patterns. No longitudinal multi-day sequences.

### 4.3 Fraudulent Email Corpus

- **Source:** https://www.kaggle.com/datasets/rtatman/fraudulent-email-corpus
- **What it provides:** 2,500+ Nigerian-style (419) fraud emails from 1998-2007. Full email headers (From, Reply-To, Subject, Date, MIME metadata). Single-file format requiring parsing.
- **How to use in build:**
  - **Testing:** Bulk true-positive testing for Inbound Classifier on obvious single-shot scams. Header analysis testing.
  - **Training prompts:** Examples of financial solicitation language patterns, authority claims, prize/inheritance lures.
- **Limitations:** Dated (1998-2007) — language patterns have evolved significantly. English-only, Western-style scams. No Japanese patterns. No multi-turn conversations. No sender profile metadata. Useful only for baseline single-shot classification testing.

### 4.4 NPA Tokushu Sagi Statistics

- **Source:** https://www.nippon.com/en/japan-data/h02424/ (reporting on NPA data)
- **What it provides:** 2024 statistics: ¥71.8B tokushu sagi losses (58.6% increase YoY), 21,043 cases (10.5% increase). Breakdown by type (police impersonation 4,261 cases with >400% increase, fictitious billing 5,716, refund 4,070). Victim demographics (65+ = 65.4% of cases). Social media fraud separately: 10,237 cases, ¥127.2B losses. Combined: ~¥199B for 2024.
- **How to use in build:**
  - **Demo scenarios:** Lead with ¥324B (2025 projected/reported figure from CONTEXT.md) for business case. Pattern distribution informs which scam types to prioritize in demo.
  - **Training prompts:** Ground pattern descriptions in real statistical weight. Fake police surge (>400% increase) justifies `fake-police` as high-priority pattern.
- **Limitations:** Reported statistics, not raw data. No individual case records. 2024 data confirmed; the ¥324B / 42,900 case figure referenced in CONTEXT.md appears to be 2025 NPA data from a separate source. Year-over-year trend confirms acceleration.
- **Note on ¥324B figure:** CONTEXT.md cites ¥324B total losses and 42,900 cases for 2025. The nippon.com source confirms 2024 combined losses of ~¥199B (¥71.8B tokushu sagi + ¥127.2B social media fraud). The ¥324B figure is consistent with the acceleration trend (4.5x YoY cited in CONTEXT.md) and likely comes from a 2025 NPA interim report.

### 4.5 Elder Financial Exploitation Dataset (Data.gov)

- **Source:** https://catalog.data.gov/dataset/exploring-elder-financial-exploitation-victimization-identifying-unique-risk-profiles-2009-0e58c
- **What it provides:** 8,800 confirmed elder financial exploitation cases with behavioral patterns and risk profiles.
- **How to use in build:**
  - **Training prompts:** Risk profile characteristics to inform Behavioral Analyzer's risk scoring model — what behavioral patterns correlate with exploitation.
  - **Demo scenarios:** Ground the "why this matters" narrative with confirmed case patterns.
- **Limitations:** US data, not Japan-specific. Dataset access may be restricted (404 on direct link as of research date). Risk profiles may not transfer directly to Japanese cultural context. Supplementary source only.

### 4.6 Scam Vulnerability Study (PMC9358277)

- **Source:** https://pmc.ncbi.nlm.nih.gov/articles/PMC9358277/
- **What it provides:** Psychosocial characteristics of elderly Japanese scam victims. Key findings:
  - Female victims: 87.5% of scam group vs 61.6% of non-victims
  - Living alone: 47% of victims
  - Overconfidence bias: victims scored higher on "I am confident I will not be scammed" (2.20 vs 1.37)
  - Phone responsiveness: victims answer calls immediately (2.16 vs 1.35)
  - Poor stranger boundaries: victims listen to unknown visitors despite intending not to
  - Infrequent outings: 46% daily vs 74% for non-victims (isolation indicator)
  - 75% of initial fraud contact via telephone
  - 46.4% of fraudsters impersonate government officials
  - Risk predictors: female gender (OR=3.52), overconfidence (OR=3.24), infrequent outings (OR=2.78), poor boundaries (OR=2.58)
- **How to use in build:**
  - **Training prompts:** Vulnerability factors inform Behavioral Analyzer's contextual risk adjustment — a user living alone with high phone responsiveness faces elevated baseline risk.
  - **Demo scenarios:** Ground the "why elderly are vulnerable" narrative. The overconfidence paradox (victims believe they are immune) is a compelling demo talking point.
  - **Agent design:** The "never show content" principle is directly supported by this research — warning-based systems fail because overconfident users dismiss warnings.
- **Limitations:** Small sample size (not specified in abstract). Correlational, not causal. Findings describe vulnerability profiles, not detection signals per se — useful for context but not directly implementable as detection rules.

---

## Appendix: Signal-to-Pattern Mapping

Which signals are most diagnostic for each scam pattern. Agents use this to weight signals
when computing risk scores.

| Pattern | Strongest Signals | Supporting Signals |
|---------|------------------|--------------------|
| `ore-ore-sagi` | LG-2 (contact mismatch), PM-10 (emotional crisis), PM-1 (urgency) | PM-2 (secrecy), PM-3 (financial), OB-3 (transfer) |
| `fake-grandchild` | LG-2 (contact mismatch), PM-10 (emotional crisis), PM-11 (identity claim) | LG-1 (fact contradiction), PM-1 (urgency), PM-2 (secrecy) |
| `fictitious-billing` | PM-6 (legal threat), PM-3 (financial), PM-5 (unusual payment) | PM-1 (urgency) |
| `refund-sagi` | PM-9 (refund lure), PM-7 (credential solicitation), PM-4 (authority claim) | PM-1 (urgency) |
| `lottery-prize` | PM-8 (prize notification), PM-3 (financial), PM-5 (unusual payment) | PM-1 (urgency) |
| `fake-bank` | PM-4 (authority claim), PM-7 (credential solicitation), PM-13 (SPF/DKIM fail) | PM-1 (urgency) |
| `gov-impersonation` | PM-4 (authority claim), PM-7 (credential solicitation), PM-6 (legal threat) | LG-2 (contact mismatch), PM-1 (urgency) |
| `romance-sagi` | LG-1 (fact contradiction), LG-5 (financial timing), LG-4 (emotional progression) | LG-3 (frequency escalation), LG-8 (crisis after trust), LG-9 (rapid intimacy), LG-10 (compliance conditioning), PM-12 (flattery density) |
| `fake-police` | PM-4 (authority claim), PM-2 (secrecy), PM-5 (unusual payment — "safe account") | PM-1 (urgency), PM-6 (legal threat), LG-2 (contact mismatch) |
