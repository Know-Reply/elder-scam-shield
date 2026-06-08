"""Pre-classification pipeline — context the LLM can't compute itself.

Three pre-processing steps run BEFORE the LLM, providing evidence
from infrastructure (corpus, graph, structural analysis). The LLM
then classifies and extracts entities — that's its job, not regex.

Pre-LLM steps (pure Python, ~50ms, no API calls):
  1. Linguistic Analysis       — manipulation density, style fingerprint
  2. Corpus Search             — TF-IDF over 22,979 entries
  3. Social Graph Validation   — contact verification, imposter detection
  3.5 Contra-Indicator Check   — evidence FOR legitimacy, not just against

LLM step (Gemini flash-lite, ~0.9s):
  4. Classification + Entity Extraction — output_schema enforced

Post-classification (separate agents in Workflow):
  - Behavioral Analyzer — longitudinal profiling (async)
  - Family Alerter — conditional on risk > 0.6
  - Conversation Knowledge Graph — provenance tracking
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


# ── Full pipeline runner ────────────────────────────────────────────────

def _contra_indicator_check(text: str, linguistic: dict) -> dict:
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
    The LLM extracts entities and classifies. Pre-processing provides
    context the LLM can't compute itself (corpus matches, graph state).
    """
    from agents.tools.search_scam_corpus import search_scam_corpus
    from agents.tools.social_graph import validate_social_graph

    # Step 1: Linguistic Analysis (structural, no LLM)
    linguistic = linguistic_analysis(message_text, sender_style_baseline)

    # Step 2: Corpus Search (TF-IDF)
    corpus_result = search_scam_corpus(message_text, top_k=5)

    # Step 3: Social Graph Validation
    graph = validate_social_graph(user_id, sender_id)

    # Step 3.5: Contra-indicator analysis
    contra = _contra_indicator_check(message_text, linguistic)

    return {
        "linguistic": linguistic,
        "corpus_matches": corpus_result.get("matches", []),
        "corpus_stats": corpus_result.get("corpus_stats", {}),
        "graph_validation": graph,
        "contra_indicators": contra,
        "pipeline_version": "v2_7step",
    }
