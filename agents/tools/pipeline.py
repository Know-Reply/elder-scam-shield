"""Multi-step hardened pipeline — moves intelligence OUT of the model.

8-step pipeline that runs pre-processing BEFORE the LLM classifier,
so by the time Gemini sees the message, it already has metadata signals,
extracted entities, corpus matches, and graph validation as context.

The model confirms or overrides pre-computed signals — it doesn't reason
from scratch. This is what enables running on smaller/cheaper models.

Steps:
  1. Linguistic Analysis    (new — lightweight NLP, no LLM)
  2. Entity Extraction      (rule-based pre-extraction)
  3. Corpus Search          (TF-IDF, upgraded from Jaccard)
  4. Social Graph Validation
  5. Per-Message Classification (LLM — consumes steps 1-4 as context)
  6. Sender Profile Update
  7. Behavioral Velocity Scoring
  8. Decision Synthesis + Action Routing
"""

import re


# ── Step 1: Linguistic Analysis ─────────────────────────────────────────

# Emotional manipulation keyword sets (research-documented patterns)
_URGENCY_WORDS = {
    "en": {"urgent", "immediately", "right now", "today", "asap", "hurry",
           "deadline", "expires", "last chance", "act now", "don't delay",
           "time sensitive", "within 24"},
    "ja": {"今すぐ", "急いで", "至急", "本日中", "すぐに", "直ちに", "緊急",
           "期限", "大至急"},
}
_GUILT_WORDS = {
    "en": {"disappointed", "let down", "counting on you", "only you",
           "no one else", "please help", "i beg", "desperate", "ashamed",
           "embarrassed", "sorry to ask", "hate to ask"},
    "ja": {"お願い", "頼む", "情けない", "申し訳", "すみません", "助けて",
           "頼り", "迷惑", "心配"},
}
_FLATTERY_WORDS = {
    "en": {"wonderful", "amazing", "special", "beautiful", "kind",
           "generous", "dear", "beloved", "sweetheart", "darling",
           "my love", "incredible", "extraordinary"},
    "ja": {"素敵", "素晴らしい", "優しい", "特別", "大切", "愛して",
           "すごい", "立派"},
}
_SECRECY_WORDS = {
    "en": {"don't tell", "keep secret", "between us", "confidential",
           "private matter", "don't share", "just between"},
    "ja": {"誰にも言わないで", "内緒", "秘密", "他の人には", "言わないで"},
}


def _detect_language(text: str) -> str:
    """Detect if text is primarily Japanese or English."""
    cjk = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text))
    ascii_alpha = len(re.findall(r'[a-zA-Z]', text))
    return "ja" if cjk > ascii_alpha else "en"


def _count_keyword_matches(text: str, keyword_set: dict, language: str) -> int:
    """Count keyword matches in text."""
    text_lower = text.lower()
    count = 0
    for word in keyword_set.get(language, set()) | keyword_set.get("en", set()):
        if word in text_lower:
            count += 1
    return count


def linguistic_analysis(text: str, sender_style_baseline: dict = None) -> dict:
    """Step 1: Lightweight linguistic analysis — no LLM needed.

    Computes:
    - Writing style fingerprint (length, complexity, punctuation)
    - Emotional manipulation density (urgency + guilt + flattery + secrecy)
    - Style deviation from sender's baseline (if available)

    Returns a pre-computed signal bundle that feeds into the Classifier.
    """
    language = _detect_language(text)
    words = text.split()
    word_count = len(words)
    char_count = len(text)

    # Writing style fingerprint
    avg_word_length = sum(len(w) for w in words) / max(word_count, 1)
    unique_words = len(set(w.lower() for w in words))
    vocabulary_richness = unique_words / max(word_count, 1)
    exclamation_count = text.count("!") + text.count("！")
    question_count = text.count("?") + text.count("？")
    ellipsis_count = text.count("...") + text.count("…")

    style = {
        "word_count": word_count,
        "char_count": char_count,
        "avg_word_length": round(avg_word_length, 2),
        "vocabulary_richness": round(vocabulary_richness, 3),
        "exclamation_density": round(exclamation_count / max(word_count, 1), 3),
        "question_density": round(question_count / max(word_count, 1), 3),
        "ellipsis_count": ellipsis_count,
    }

    # Emotional manipulation density
    urgency = _count_keyword_matches(text, _URGENCY_WORDS, language)
    guilt = _count_keyword_matches(text, _GUILT_WORDS, language)
    flattery = _count_keyword_matches(text, _FLATTERY_WORDS, language)
    secrecy = _count_keyword_matches(text, _SECRECY_WORDS, language)

    manipulation_score = (urgency * 0.3 + guilt * 0.25 + flattery * 0.2 + secrecy * 0.25)
    manipulation_density = round(manipulation_score / max(word_count / 10, 1), 3)

    manipulation = {
        "urgency_count": urgency,
        "guilt_count": guilt,
        "flattery_count": flattery,
        "secrecy_count": secrecy,
        "manipulation_density": min(manipulation_density, 1.0),
        "manipulation_signals": [],
    }
    if urgency > 0: manipulation["manipulation_signals"].append(f"urgency({urgency})")
    if guilt > 0: manipulation["manipulation_signals"].append(f"guilt({guilt})")
    if flattery > 0: manipulation["manipulation_signals"].append(f"flattery({flattery})")
    if secrecy > 0: manipulation["manipulation_signals"].append(f"secrecy({secrecy})")

    # Style deviation from baseline (if sender has history)
    style_deviation = 0.0
    if sender_style_baseline:
        baseline_len = sender_style_baseline.get("avg_word_count", word_count)
        baseline_vocab = sender_style_baseline.get("avg_vocabulary_richness", vocabulary_richness)
        len_dev = abs(word_count - baseline_len) / max(baseline_len, 1)
        vocab_dev = abs(vocabulary_richness - baseline_vocab) / max(baseline_vocab, 0.01)
        style_deviation = round(min((len_dev + vocab_dev) / 2, 1.0), 3)

    return {
        "language": language,
        "style": style,
        "manipulation": manipulation,
        "style_deviation": style_deviation,
        "style_deviation_flag": style_deviation > 0.5,
    }


# ── Step 2: Entity Extraction (rule-based) ──────────────────────────────

_AMOUNT_PATTERN = re.compile(
    r'(?:¥|￥|\\)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:万)?(?:円|yen|usd|\$|dollars?)?'
    r'|(\d+)\s*万\s*円'
    r'|\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    re.I
)

_JP_RELATIONSHIP_WORDS = {
    "孫": "grandchild", "息子": "son", "娘": "daughter",
    "甥": "nephew", "姪": "niece", "おばあちゃん": "grandmother",
    "おじいちゃん": "grandfather", "お母さん": "mother", "お父さん": "father",
    "姉": "older sister", "兄": "older brother", "妹": "younger sister",
    "弟": "younger brother", "奥さん": "wife", "主人": "husband",
}

_EN_RELATIONSHIP_WORDS = {
    "grandson": "grandson", "granddaughter": "granddaughter",
    "grandchild": "grandchild", "son": "son", "daughter": "daughter",
    "nephew": "nephew", "niece": "niece", "grandmother": "grandmother",
    "grandfather": "grandfather", "grandma": "grandmother",
    "grandpa": "grandfather", "mother": "mother", "father": "father",
    "mom": "mother", "dad": "father", "wife": "wife", "husband": "husband",
}

_JP_LOCATION_PATTERN = re.compile(
    r'(東京|大阪|横浜|名古屋|京都|神戸|福岡|札幌|仙台|広島|さいたま|千葉|'
    r'渋谷|新宿|池袋|目黒|品川|上野|浅草|秋葉原|銀座)'
)

_INSTITUTION_PATTERN = re.compile(
    r'(警察|警視庁|市役所|税務署|年金|役所|銀行|病院|クリニック|'
    r'裁判所|弁護士|証券|保険|郵便局|NTT|au|ソフトバンク|'
    r'police|hospital|bank|IRS|FBI|government|court)',
    re.I
)


def entity_extraction(text: str) -> dict:
    """Step 2: Rule-based entity extraction — no LLM needed.

    Extracts structured facts from message text using patterns.
    Runs BEFORE the LLM classifier so every downstream agent
    has pre-extracted entities available.
    """
    language = _detect_language(text)

    # Names (look for Japanese name patterns or quoted names)
    names = []
    # Japanese: look for relationship + name combos
    for jp_word, en_word in _JP_RELATIONSHIP_WORDS.items():
        if jp_word in text:
            names.append({"word": jp_word, "relationship": en_word})

    for en_word, rel in _EN_RELATIONSHIP_WORDS.items():
        if re.search(r'\b' + en_word + r'\b', text, re.I):
            names.append({"word": en_word, "relationship": rel})

    # Financial amounts
    amounts = []
    for m in _AMOUNT_PATTERN.finditer(text):
        raw = m.group()
        amounts.append(raw.strip())

    # Locations
    locations = _JP_LOCATION_PATTERN.findall(text)

    # Institutions
    institutions = _INSTITUTION_PATTERN.findall(text)

    # Deadlines / urgency markers
    has_deadline = bool(re.search(
        r'今日中|本日中|within 24|by today|by tomorrow|明日まで|期限',
        text, re.I
    ))

    # Third-party references (people mentioned but not the sender)
    third_parties = []
    # Japanese: "Xさんが/に/の" pattern
    jp_refs = re.findall(r'([ぁ-ん]{2,}|[ァ-ヶ]{2,}|[一-龥]{1,4})(?:さん|くん|ちゃん)', text)
    third_parties.extend(jp_refs)

    return {
        "relationships_claimed": names,
        "financial_amounts": amounts,
        "locations": locations,
        "institutions": institutions,
        "has_deadline": has_deadline,
        "third_party_references": third_parties,
        "entity_count": len(names) + len(amounts) + len(locations) + len(institutions),
    }


# ── Step 8: Decision Synthesis ──────────────────────────────────────────

def decision_synthesis(
    linguistic: dict,
    entities: dict,
    corpus_matches: list,
    graph_validation: dict,
    classification: dict,
    behavioral_risk: float,
    behavioral_signals: list,
) -> dict:
    """Step 8: Combine ALL signal layers into compound risk score with evidence chain.

    Takes outputs from all previous steps and produces:
    - Final compound risk score
    - Complete evidence chain citing every contributing signal
    - Action routing (PASS / FLAG / HOLD / BLOCK)
    """

    evidence_chain = []

    # Linguistic signals
    manip = linguistic.get("manipulation", {})
    if manip.get("manipulation_density", 0) > 0.3:
        evidence_chain.append({
            "source": "linguistic_analysis",
            "signal": "high_manipulation_density",
            "value": manip["manipulation_density"],
            "detail": f"Manipulation signals: {', '.join(manip.get('manipulation_signals', []))}",
        })
    if linguistic.get("style_deviation_flag"):
        evidence_chain.append({
            "source": "linguistic_analysis",
            "signal": "style_deviation",
            "value": linguistic["style_deviation"],
            "detail": "Writing style deviates significantly from sender baseline",
        })

    # Entity signals
    if entities.get("financial_amounts"):
        evidence_chain.append({
            "source": "entity_extraction",
            "signal": "financial_amounts_detected",
            "value": entities["financial_amounts"],
            "detail": f"Financial amounts found: {', '.join(entities['financial_amounts'])}",
        })
    if entities.get("has_deadline"):
        evidence_chain.append({
            "source": "entity_extraction",
            "signal": "deadline_pressure",
            "value": True,
            "detail": "Message contains deadline/urgency markers",
        })

    # Corpus evidence
    scam_matches = [m for m in corpus_matches if m.get("label") == "scam"]
    if scam_matches:
        evidence_chain.append({
            "source": "corpus_search",
            "signal": "corpus_scam_matches",
            "value": len(scam_matches),
            "detail": f"{len(scam_matches)} similar scam messages found in {corpus_matches[0].get('source', 'corpus')}",
        })

    # Graph signals
    graph_mod = graph_validation.get("graph_risk_modifier", 0)
    if graph_mod > 0:
        evidence_chain.append({
            "source": "graph_validation",
            "signal": "graph_risk_boost",
            "value": graph_mod,
            "detail": f"Graph distance: {graph_validation.get('graph_distance', '?')}. "
                      f"{'Imposter signal — claims relationship but no graph connection' if graph_mod >= 0.3 else 'Unknown sender'}",
        })
    elif graph_mod < 0:
        evidence_chain.append({
            "source": "graph_validation",
            "signal": "graph_trust",
            "value": graph_mod,
            "detail": f"Known contact (distance {graph_validation.get('graph_distance', 0)}), trust modifier {graph_mod}",
        })

    # Classification result
    cls = classification.get("classification", "safe")
    if cls in ("scam", "suspicious"):
        evidence_chain.append({
            "source": "classifier",
            "signal": f"classified_{cls}",
            "value": classification.get("confidence", 0),
            "detail": f"Per-message classification: {cls} ({classification.get('confidence', 0):.0%} confidence). "
                      f"Signals: {', '.join(classification.get('detected_signals', []))}",
        })

    # Behavioral signals
    if behavioral_risk > 0.25:
        evidence_chain.append({
            "source": "behavioral_analyzer",
            "signal": "behavioral_risk_elevated",
            "value": behavioral_risk,
            "detail": f"Behavioral risk: {behavioral_risk:.2f}. Signals: {', '.join(str(s) for s in behavioral_signals[:5])}",
        })

    # ── Compound risk score ─────────────────────────────────────────
    # Weighted combination of all signal layers
    compound_score = 0.0

    # Linguistic (10%)
    compound_score += min(manip.get("manipulation_density", 0), 1.0) * 0.10

    # Corpus evidence (15%)
    if scam_matches:
        corpus_signal = min(len(scam_matches) / 3, 1.0) * max(m.get("relevance_score", 0) for m in scam_matches)
        compound_score += corpus_signal * 0.15

    # Graph (15%)
    compound_score += max(graph_mod, 0) * 0.5  # imposter signal contributes heavily
    compound_score -= max(-graph_mod, 0) * 0.15  # trust reduces

    # Classification (30%)
    cls_score = {"safe": 0, "spam": 0.1, "suspicious": 0.5, "scam": 0.9}.get(cls, 0)
    compound_score += cls_score * classification.get("confidence", 0.5) * 0.30

    # Behavioral (30%)
    compound_score += behavioral_risk * 0.30

    compound_score = round(max(min(compound_score, 1.0), 0.0), 3)

    # Action routing
    if compound_score >= 0.7:
        action = "BLOCK"
    elif compound_score >= 0.4:
        action = "FLAG"
    elif compound_score >= 0.2:
        action = "MONITOR"
    else:
        action = "PASS"

    return {
        "compound_risk_score": compound_score,
        "action": action,
        "evidence_chain": evidence_chain,
        "evidence_count": len(evidence_chain),
        "pipeline_steps_completed": 8,
        "signal_sources": list(set(e["source"] for e in evidence_chain)),
    }


# ── Victim State Analysis (outbound replies only) ─────────────────────

# VS signal patterns — detect the elder's psychological state change
_VS_COMPLIANCE = re.compile(
    r'わかりました|了解|承知|そうします|やります|'
    r'はい、|ええ、|分かった|'
    r"understood|i will|okay i|yes i",
    re.I
)
_VS_SECRECY_ACCEPT = re.compile(
    r'言いません|内緒にし|秘密にし|誰にも.*言わない|'
    r'黙って|話さない|'
    r"won't tell|keep.*secret|don't.*worry.*tell",
    re.I
)
_VS_FINANCIAL_COMMIT = re.compile(
    r'振り込み|振込み|銀行に行|送ります|払います|用意し|'
    r'引き出し|おろして|ATMに|カードを買|'
    r"transfer|send.*money|go to.*bank|withdraw|buy.*card",
    re.I
)
_VS_EMOTIONAL_CAPITULATION = re.compile(
    r'心配しないで|大丈夫|安心して|任せて|'
    r'元気になって|早く.*良く|頑張って|'
    r"don't worry|it's okay|take care|get well",
    re.I
)
_VS_URGENCY_MIRROR = re.compile(
    r'すぐに|今日中に|急いで|今から|明日朝一|'
    r"right away|immediately|first thing|asap",
    re.I
)

# Weights per VS signal (how dangerous each state change is)
_VS_WEIGHTS = {
    "VS-1": 0.15,  # compliance alone is just politeness
    "VS-2": 0.35,  # secrecy acceptance is a strong danger signal
    "VS-3": 0.40,  # financial commitment is the highest risk
    "VS-4": 0.10,  # emotional capitulation — caring, not dangerous alone
    "VS-5": 0.20,  # urgency mirroring — adopting scammer's tempo
}


def victim_state_analysis(text: str) -> dict:
    """Analyze an elder's outbound reply for signs of falling for a scam.

    Detects the psychological state change from skeptical/neutral to
    compliant/committed. These signals are meaningless in isolation
    (VS-1 = politeness) but compound with inbound risk to detect the
    moment a scam is working.

    Returns VS signals detected + a compliance score (0.0-1.0).
    """
    signals = []
    details = {
        "compliance_words": [],
        "secrecy_acceptance": False,
        "financial_commitment": [],
        "emotional_capitulation": [],
        "urgency_mirroring": False,
    }

    # VS-1: Compliance acceptance
    compliance_matches = _VS_COMPLIANCE.findall(text)
    if compliance_matches:
        signals.append("VS-1")
        details["compliance_words"] = compliance_matches[:3]

    # VS-2: Secrecy adoption
    if _VS_SECRECY_ACCEPT.search(text):
        signals.append("VS-2")
        details["secrecy_acceptance"] = True

    # VS-3: Financial commitment
    financial_matches = _VS_FINANCIAL_COMMIT.findall(text)
    if financial_matches:
        signals.append("VS-3")
        details["financial_commitment"] = financial_matches[:3]

    # VS-4: Emotional capitulation
    emotional_matches = _VS_EMOTIONAL_CAPITULATION.findall(text)
    if emotional_matches:
        signals.append("VS-4")
        details["emotional_capitulation"] = emotional_matches[:3]

    # VS-5: Urgency mirroring
    if _VS_URGENCY_MIRROR.search(text):
        signals.append("VS-5")
        details["urgency_mirroring"] = True

    # Compound compliance score
    score = sum(_VS_WEIGHTS.get(s, 0) for s in signals)
    score = round(min(score, 1.0), 3)

    return {
        "signals": signals,
        "compliance_score": score,
        "details": details,
        "victim_falling": score >= 0.4,
        "guidance": (
            "CRITICAL: Elder's reply shows signs of falling for the scam. "
            f"Detected: {', '.join(signals)}. Compliance score: {score}. "
            "HOLD this reply and alert family immediately."
        ) if score >= 0.4 else None,
    }


# ── Full pipeline runner ────────────────────────────────────────────────

def _contra_indicator_check(text: str, entities: dict, linguistic: dict) -> dict:
    """Step 4.5: Check for signs that a scam-shaped message may be legitimate.

    Scams and real family requests can look structurally identical.
    This step surfaces the distinguishing features so the LLM has
    pre-computed evidence for both sides, not just corpus matches.
    """
    # Secrecy demands — strong scam indicator when present
    secrecy_patterns = re.compile(
        r'誰にも言わないで|内緒|言わないで|秘密|他の人には|'
        r'お父さんには.*言わないで|お母さんには.*言わないで|'
        r"don't tell|keep.*secret|between us",
        re.I
    )
    has_secrecy = bool(secrecy_patterns.search(text))

    # Third-party account — scams demand transfer to someone else's account
    third_party_account = bool(re.search(
        r'この口座|相手の口座|以下の口座|振込先|'
        r"this account|their account|transfer to",
        text, re.I
    ))

    # External deadline pressure — someone ELSE demanding payment
    external_pressure = bool(re.search(
        r'相手が.*払え|相手が.*要求|警察.*呼ぶ|訴える|法的|'
        r'今すぐ.*払|期限.*まで|'
        r"they.*demand|police.*call|sue|legal",
        text, re.I
    ))

    # Mundane need — proportional, everyday request
    mundane_patterns = re.compile(
        r'タクシー|バス|電車|ランチ|昼ごはん|教科書|文房具|'
        r'携帯.*壊れ|自転車|財布.*落|忘れ|'
        r"taxi|bus|lunch|textbook|phone.*broke|wallet|forgot",
        re.I
    )
    has_mundane_context = bool(mundane_patterns.search(text))

    # Manipulation density from linguistic analysis
    manipulation = linguistic.get("manipulation", {})
    low_manipulation = manipulation.get("manipulation_density", 0) == 0

    # Count contra-indicators present
    contra_count = sum([
        not has_secrecy,        # no secrecy demand
        not third_party_account, # no third-party account
        not external_pressure,   # no external deadline
        has_mundane_context,     # mundane everyday need
        low_manipulation,        # no manipulation language
    ])

    may_be_legitimate = contra_count >= 3 and not has_secrecy and not third_party_account

    return {
        "has_secrecy_demand": has_secrecy,
        "has_third_party_account": third_party_account,
        "has_external_pressure": external_pressure,
        "has_mundane_context": has_mundane_context,
        "low_manipulation": low_manipulation,
        "contra_indicator_count": contra_count,
        "may_be_legitimate": may_be_legitimate,
        "guidance": (
            "IMPORTANT: This message has strong contra-indicators suggesting it may be "
            "a legitimate family request, not a scam. No secrecy demand, no third-party "
            "account, mundane context. Classify as SUSPICIOUS (not scam) and recommend "
            "verification by calling the sender's known number."
        ) if may_be_legitimate else None,
    }


def run_pre_classification_pipeline(
    message_text: str,
    sender_id: str,
    user_id: str,
    sender_style_baseline: dict = None,
) -> dict:
    """Run steps 1-4 of the pipeline BEFORE the LLM classifier.

    Returns a context bundle that the Classifier consumes.
    The Classifier's job becomes: "given this pre-computed evidence,
    what's your classification?"

    This is what makes smaller models viable — the heavy lifting
    is done before the LLM sees the message.
    """
    from agents.tools.search_scam_corpus import search_scam_corpus
    from agents.tools.social_graph import validate_social_graph

    # Step 1: Linguistic Analysis
    linguistic = linguistic_analysis(message_text, sender_style_baseline)

    # Step 2: Entity Extraction
    entities = entity_extraction(message_text)

    # Step 3: Corpus Search (TF-IDF)
    corpus_result = search_scam_corpus(message_text, top_k=5)

    # Step 4: Social Graph Validation
    graph = validate_social_graph(user_id, sender_id)

    # Step 4.5: Contra-indicator analysis
    contra = _contra_indicator_check(message_text, entities, linguistic)

    return {
        "linguistic": linguistic,
        "entities": entities,
        "corpus_matches": corpus_result.get("matches", []),
        "corpus_stats": corpus_result.get("corpus_stats", {}),
        "graph_validation": graph,
        "contra_indicators": contra,
        "pipeline_version": "v2_8step",
    }
