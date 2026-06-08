"""Grounding tool — search scam corpus for similar known patterns.

Connects to Vertex AI Search (Agent Search) to find similar known scams
in the indexed corpus. Every classification becomes evidence-backed:
"this pattern matches N confirmed cases" instead of "my prompt says so."

For local development, falls back to a JSONL-based search using
text similarity. In production, uses Vertex AI Search Data Store.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Vertex AI Search (production)
# ---------------------------------------------------------------------------

def _search_vertex(query: str, top_k: int = 5) -> list[dict]:
    """Search the Vertex AI Search data store for similar scam patterns."""
    from google.cloud import discoveryengine_v1 as discoveryengine

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("VERTEX_AI_LOCATION", "asia-northeast1")
    data_store_id = os.environ.get("SCAM_CORPUS_DATA_STORE", "scam-corpus")

    client = discoveryengine.SearchServiceClient()
    serving_config = (
        f"projects/{project}/locations/{location}"
        f"/collections/default_collection/dataStores/{data_store_id}"
        f"/servingConfigs/default_serving_config"
    )

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=top_k,
        content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True,
                max_snippet_count=3,
            ),
            summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=3,
                include_citations=True,
            ),
        ),
    )

    response = client.search(request)
    results = []
    for result in response.results:
        doc = result.document
        data = {
            "id": doc.id,
            "title": doc.derived_struct_data.get("title", ""),
            "snippet": "",
            "label": doc.struct_data.get("label", "unknown"),
            "scam_type": doc.struct_data.get("scam_type", None),
            "relevance_score": result.relevance_score if hasattr(result, "relevance_score") else None,
        }
        # Extract snippets
        snippets = doc.derived_struct_data.get("snippets", [])
        if snippets:
            data["snippet"] = snippets[0].get("snippet", "")
        results.append(data)

    return results


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Local fallback (development — TF-IDF search over JSONL corpus)
# ---------------------------------------------------------------------------

_LOCAL_CORPUS: Optional[list[dict]] = None
_TFIDF_VECTORIZER = None
_TFIDF_MATRIX = None
_TFIDF_CHAR_VECTORIZER = None  # Character n-gram vectorizer for Japanese
_TFIDF_CHAR_MATRIX = None


def _load_local_corpus() -> list[dict]:
    """Load the processed JSONL corpus into memory and fit TF-IDF."""
    global _LOCAL_CORPUS, _TFIDF_VECTORIZER, _TFIDF_MATRIX, _TFIDF_CHAR_VECTORIZER, _TFIDF_CHAR_MATRIX
    if _LOCAL_CORPUS is not None:
        return _LOCAL_CORPUS

    data_dir = Path(__file__).parent.parent.parent / "data" / "processed"
    corpus_files = [
        data_dir / "scam_corpus.jsonl",
        data_dir / "jp_scenarios.jsonl",
        data_dir / "edge_cases.jsonl",
        data_dir / "gov_sources.jsonl",
        data_dir / "antiphishing_corpus.jsonl",
        data_dir / "conversation_corpus.jsonl",
    ]

    _LOCAL_CORPUS = []
    for p in corpus_files:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        _LOCAL_CORPUS.append(json.loads(line))

    # Fit TF-IDF on corpus texts — two vectorizers:
    #   1. Word-level for English (standard tokenization)
    #   2. Character n-gram for Japanese (no word boundaries in Japanese)
    if _LOCAL_CORPUS:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            texts = [entry.get("text", "") for entry in _LOCAL_CORPUS]

            # Word-level vectorizer (English + romaji)
            _TFIDF_VECTORIZER = TfidfVectorizer(
                max_features=50000,
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.95,
                sublinear_tf=True,
            )
            _TFIDF_MATRIX = _TFIDF_VECTORIZER.fit_transform(texts)

            # Character n-gram vectorizer (Japanese + cross-language)
            _TFIDF_CHAR_VECTORIZER = TfidfVectorizer(
                analyzer='char_wb',
                ngram_range=(2, 4),
                max_features=100000,
                min_df=1,
                max_df=0.98,
                sublinear_tf=True,
            )
            _TFIDF_CHAR_MATRIX = _TFIDF_CHAR_VECTORIZER.fit_transform(texts)
        except ImportError as e:
            print(f"[search_scam_corpus] sklearn not available: {e}")
            _TFIDF_VECTORIZER = None
            _TFIDF_MATRIX = None
            _TFIDF_CHAR_VECTORIZER = None
            _TFIDF_CHAR_MATRIX = None
        except Exception as e:
            print(f"[search_scam_corpus] TF-IDF build error: {e}")
            _TFIDF_CHAR_VECTORIZER = None
            _TFIDF_CHAR_MATRIX = None

    return _LOCAL_CORPUS


def _search_local(query: str, top_k: int = 5, label_filter: str = None) -> list[dict]:
    """Search local JSONL corpus using TF-IDF + cosine similarity."""
    corpus = _load_local_corpus()
    if not corpus:
        return []

    # TF-IDF search — use word vectorizer for English, char vectorizer for Japanese,
    # merge results for mixed-language queries
    if _TFIDF_VECTORIZER is not None and _TFIDF_MATRIX is not None:
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        # Detect if query has CJK characters
        has_cjk = bool(re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', query))

        # Word-level scores (always compute — works for English)
        word_scores = cosine_similarity(
            _TFIDF_VECTORIZER.transform([query]), _TFIDF_MATRIX
        ).flatten()

        # Character n-gram scores (better for Japanese)
        char_scores = np.zeros(len(corpus))
        if _TFIDF_CHAR_VECTORIZER is not None and _TFIDF_CHAR_MATRIX is not None:
            char_scores = cosine_similarity(
                _TFIDF_CHAR_VECTORIZER.transform([query]), _TFIDF_CHAR_MATRIX
            ).flatten()

        # Blend: char n-gram is more discriminating for both languages.
        # Word-level matches too many common words between casual and scam emails.
        if has_cjk:
            scores = 0.3 * word_scores + 0.7 * char_scores
        else:
            scores = 0.4 * word_scores + 0.6 * char_scores

        # Apply label filter
        if label_filter:
            for i, entry in enumerate(corpus):
                if entry.get("label") != label_filter:
                    scores[i] = 0.0

        # Get top-k
        top_indices = scores.argsort()[::-1][:top_k * 3]
        results = []
        for idx in top_indices:
            if scores[idx] < 0.01:
                break
            entry = corpus[idx]
            results.append({
                "id": entry.get("id", "unknown"),
                "snippet": entry.get("text", "")[:200],
                "label": entry.get("label", "unknown"),
                "scam_type": entry.get("scam_type"),
                "source": entry.get("source", "unknown"),
                "relevance_score": round(float(scores[idx]), 3),
                "language": entry.get("language", "en"),
            })
            if len(results) >= top_k:
                break
        return results

    # Fallback: simple keyword matching if sklearn not available
    query_lower = query.lower()
    query_words = set(re.findall(r'[\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+', query_lower))
    scored = []
    for entry in corpus:
        if label_filter and entry.get("label") != label_filter:
            continue
        text = entry.get("text", "").lower()
        text_words = set(re.findall(r'[\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+', text))
        overlap = len(query_words & text_words)
        if overlap > 0:
            score = overlap / max(len(query_words), 1)
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{
        "id": e.get("id", "unknown"),
        "snippet": e.get("text", "")[:200],
        "label": e.get("label", "unknown"),
        "scam_type": e.get("scam_type"),
        "source": e.get("source", "unknown"),
        "relevance_score": round(s, 3),
        "language": e.get("language", "en"),
    } for s, e in scored[:top_k]]


# ---------------------------------------------------------------------------
# Public API — the grounding tool agents call
# ---------------------------------------------------------------------------

def search_scam_corpus(
    message_text: str,
    top_k: int = 5,
    label_filter: str = None,
) -> dict:
    """Search the scam corpus for messages similar to the input.

    Used by Inbound Classifier and Behavioral Analyzer to ground
    classifications in evidence. Returns similar known scam/safe messages
    with relevance scores.

    Args:
        message_text: The inbound message text to search against.
        top_k: Number of similar results to return (default 5).
        label_filter: Optional filter — "scam" or "safe" only.

    Returns:
        Dict with matches list and corpus statistics.
    """
    use_vertex = os.environ.get("USE_VERTEX_SEARCH", "").lower() == "true"

    if use_vertex:
        try:
            matches = _search_vertex(message_text, top_k)
        except Exception as e:
            # Fall back to local on Vertex failure
            matches = _search_local(message_text, top_k, label_filter)
    else:
        matches = _search_local(message_text, top_k, label_filter)

    # Compute corpus-level stats for the response
    corpus = _load_local_corpus()
    scam_count = sum(1 for e in corpus if e.get("label") == "scam")
    safe_count = sum(1 for e in corpus if e.get("label") == "safe")

    return {
        "matches": matches,
        "match_count": len(matches),
        "corpus_stats": {
            "total_entries": len(corpus),
            "scam_entries": scam_count,
            "safe_entries": safe_count,
        },
        "grounding_source": "vertex_ai_search" if use_vertex else "local_jsonl",
    }


def get_corpus_pattern_stats(scam_type: str) -> dict:
    """Get statistical profile for a specific scam pattern from the corpus.

    Used by Behavioral Analyzer to cite evidence:
    "Location contradictions appeared in 89% of romance scam cases by Day 5."

    Args:
        scam_type: NPA pattern slug (e.g., "ore-ore-sagi", "romance-sagi").

    Returns:
        Dict with pattern statistics from the corpus.
    """
    corpus = _load_local_corpus()
    pattern_entries = [e for e in corpus if e.get("scam_type") == scam_type]

    if not pattern_entries:
        return {
            "scam_type": scam_type,
            "corpus_count": 0,
            "message": f"No entries for pattern '{scam_type}' in corpus.",
        }

    return {
        "scam_type": scam_type,
        "corpus_count": len(pattern_entries),
        "sources": list(set(e.get("source", "unknown") for e in pattern_entries)),
        "languages": list(set(e.get("language", "unknown") for e in pattern_entries)),
        "sample_ids": [e.get("id") for e in pattern_entries[:5]],
    }


# Pre-warm: load and vectorize the corpus at import time so the first
# API call doesn't pay the ~50s cold-start cost.
_load_local_corpus()
