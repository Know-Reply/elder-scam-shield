# Elder Shield — 2-Minute Video Script

Target: 300 words spoken at natural pace. Screen recordings of live demo.

---

## 0:00–0:15 | THE PROBLEM
**Show:** Stats on /shield page, then a message that looks innocent

"Elder fraud costs Japan over 320 billion yen a year and $77 Billion globally. The problem isn't catching scam messages — any classifier can do that. Real scams unfold over extended periods. So does our detection. Because each message in the setup phase is only looks safe, but it's designed to manipulate. A per-message classifier misses it entirely."

## 0:15–0:30 | THE INSIGHT
**Show:** Architecture diagram (/architecture page)

"Elder Shield separates detection from scoring. The LLM detects signals — it never classifies. A deterministic risk ledger accumulates evidence across messages. The LLM understands language. The math makes decisions. All six agents run on Gemini Flash Lite — the cheapest model — because the intelligence is in the infrastructure, not the model."

## 0:30–0:50 | DEMO: LONGITUDINAL DETECTION
**Show:** Scenario 3 (Longitudinal Detection) playing through with stagger

"Watch a 6-message ore-ore impersonation. Messages one through three are safe — identity claim, casual chat. The system notes them but doesn't alarm. Message four: emotional crisis. The T1 primer bonus kicks in — those earlier safe messages now amplify the score. Message five: financial ask. Suspicious. Message six: secrecy plus money demand. Blocked. The system remembered the setup."

## 0:50–1:10 | DEMO: ELDER'S GUARD
**Show:** Scenario 4 (Epistemic Drift) — focus on trust stage progression and VS signals

"Most systems watch the scammer. Elder Shield also watches the elder. Victim state signals — compliance, disclosure, instruction seeking — track whether the scam is working. Watch the Elder's Guard drop from Neutral to Compromised as the elder reveals personal information and starts offering to help. When the elder reaches Compromised, the family is alerted."

## 1:10–1:25 | ADK OPTIMIZATION TOOLS
**Show:** Scroll through /technical page showing eval results, or show the comparison bars

"We used all four ADK optimization tools. Agent Evaluation with 55 eval cases plus 52 longitudinal scenarios. Agent Simulation stress-tested multi-day scam sequences. Agent Observability traces found that legitimate family messages were matching scam corpus patterns — which drove our contra-indicator pipeline. Agent Optimizer confirmed the prompt was near-optimal — proving the value is in the architecture, not prompt engineering."

## 1:25–1:45 | RESULTS: BEFORE AND AFTER
**Show:** Comparison bars from any scenario — Elder Shield vs Pre-ADK Tuning

"The results. The naive baseline — same model, no optimization — calls scam on 75% of first messages and falsely blocks 5 out of 12 legitimate family requests. Elder Shield: zero false positives. 63.6% accuracy versus 34.7%. And the metric that matters most: WHEN, not IF. A system that flags on day 7 documents a crime. A system that flags on day 3 prevents one."

## 1:45–2:00 | CLOSE
**Show:** /shield overview page with Faxi branding

"Elder Shield is built by Faxi — an AI-powered communication bridge for elderly Japanese users. It's designed as a drop-in replacement for our production spam classifier. Same API contract, same model, dramatically better protection. Because the people who need protection most are the ones who can't evaluate warnings themselves."

"We operate a messaging platform for seniors in Japan. Real scams unfold over days. So does our detection."

* Elder abuse?
---

## Production Notes

- Record screen at 1920x1080
- Use scenario 3 (Longitudinal) as the hero demo — it has the best escalation arc
- Show scenario 4 (Epistemic Drift) briefly for the Elder's Guard section
- Keep mouse movements slow and deliberate
- Narration should be calm and measured, not rushed
- Total spoken words: ~290 (fits 2 min at natural pace)
