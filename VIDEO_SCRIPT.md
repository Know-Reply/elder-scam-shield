# Elder Shield — 2-Minute Video Script

Target: 300 words spoken at natural pace. Screen recordings of live demo.

---

## Intro section
"Hi, I'm Rob, the creator of Faxi, an Internet bridge for seniors in Japan. Online scams targeting the elderly are a global problem costing over 70 billion dollars a year."

## Anatomy of an Ore-Ore Sagi
"And trouble is, scams don't look like spam. A scammer builds trust over time,and then asks for money. Each setup message looks safe in isolation and can pass filters. 

## What a Single Classifier Sees
"For this hackathon, we used ADK to turn our filter into "Elder Shield": six Gemini Flash Lite agents on Vertex AI that remember every message and compound evidence over time. Flagging and blocking scams earlier."

## What Elder Shield Sees
"Using ADK's Agent Evaluation and Observability tools, we identified 40 signals across 6 categories from urgency language to emotional manipulation. The LLM detects signals — it never classifies. A deterministic risk ledger makes every decision." 

## Who Knew What First?
"We track who revealed each fact first, like names, so a scammer can't use grandma's own words against her."

## Interception
"When risk crosses 50%, the family is alerted but privacy is maintained. The scammer is blocked automatically at higher levels. If the elder tries to send money, the message is held."

## 3 Days Earlier. Zero False Positives.
"Before ADK optimization, our classifier was blocking five legitimate family messages. Elder Shield blocks none and still catches every scam, with the same model — the difference is the social graph and the risk ledger around it."


## DEMO page
"Elder Shield runs invisibly inside the message pipeline, so this demo is a window into the engine. Messages go through the live API and you see every signal, score, and decision it returns."

## DEMO: LONGITUDINAL DETECTION
**Show:** Scenario 3 (Longitudinal Detection) playing through with stagger

"Watch a 6-message ore-ore impersonation. Messages one through three are safe — identity claim, casual chat. The system notes them but doesn't alarm. Message four: emotional crisis. The T1 primer bonus kicks in — those earlier safe messages now amplify the score. Message five: financial ask. Suspicious. Message six: secrecy plus money demand. Blocked. The system remembered the setup."

"Watch a six-message ore-ore impersonation. Messages one through three look safe — the system notes them quietly. Message four: emotional crisis — those earlier safe messages now amplify the score. Message five: financial ask. Message six: secrecy plus a money demand. Blocked. It remembered the setup."

## DEMO: ELDER'S GUARD
**Show:** Scenario 4 (Epistemic Drift) — focus on trust stage progression and VS signals

"Most systems watch the scammer. Elder Shield also watches the elder. Victim state signals — compliance, disclosure, instruction seeking — track whether the scam is working. Watch the Elder's Guard drop from Neutral to Compromised as the elder reveals personal information and starts offering to help. When the elder reaches Compromised, the family is alerted."

"Most systems watch the scammer. Elder Shield also watches the elder. Watch the Elder's Guard drop from Neutral to Compromised as she reveals information and starts complying — that's when the family is alerted."

- Feel free to try these or your own custom message pairs

## DEMO: Dashboard - what should we explain here quickly?
"The family dashboard shows a quarantine inbox and risk timeline for contacts."

## 1:45–2:00 | CLOSE
**Show:** /shield overview page with Faxi branding

"Elder Shield is designed as a drop-in replacement for our production spam classifier. Same API contract, same model, dramatically better protection. Elder fraud costs 324 billion yen a year in Japan alone. The people who need protection most are the ones who can't evaluate warnings themselves. That's who we built this for."

## OVERTIME
"Hi...you're still here? Let me show you around a bit more"

## 1:10–1:25 | ADK OPTIMIZATION TOOLS
**Show:** Scroll through /technical page showing eval results, or show the comparison bars

"We used all four ADK optimization tools. Agent Evaluation with 55 eval cases plus 52 longitudinal scenarios. Agent Simulation stress-tested multi-day scam sequences. Agent Observability traces found that legitimate family messages were matching scam corpus patterns — which drove our contra-indicator pipeline. Agent Optimizer confirmed the prompt was near-optimal — proving the value is in the architecture, not prompt engineering."

## 1:25–1:45 | RESULTS: BEFORE AND AFTER
**Show:** Comparison bars from any scenario — Elder Shield vs Pre-ADK Tuning

"The results. Thirty-four out of thirty-four scams caught — the naive baseline, same model, missed three multi-day groomers whose messages each look reasonable on their own. Zero false positives, earned the hard way: our own evaluation exposed family messages being flagged, we traced it to the scoring layer, and fixed it in thirty lines of auditable code. And the metric that matters most: WHEN, not IF. A system that flags on day 7 documents a crime. A system that flags on day 4 prevents one."






  Timing concern: You have a LOT of sections before the demo. The demo should hit before
   1:00. Consider combining "What a Single Classifier Sees" + "What Elder Shield Sees"
  into one 10-second section, not two.

