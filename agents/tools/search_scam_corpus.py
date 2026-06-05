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
# Local fallback (development — searches JSONL corpus directly)
# ---------------------------------------------------------------------------

_LOCAL_CORPUS: Optional[list[dict]] = None


def _load_local_corpus() -> list[dict]:
    """Load the processed JSONL corpus into memory."""
    global _LOCAL_CORPUS
    if _LOCAL_CORPUS is not None:
        return _LOCAL_CORPUS

    corpus_path = Path(__file__).parent.parent.parent / "data" / "processed" / "scam_corpus.jsonl"
    jp_path = Path(__file__).parent.parent.parent / "data" / "processed" / "jp_scenarios.jsonl"
    edge_path = Path(__file__).parent.parent.parent / "data" / "processed" / "edge_cases.jsonl"

    _LOCAL_CORPUS = []
    for p in [corpus_path, jp_path, edge_path]:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        _LOCAL_CORPUS.append(json.loads(line))

    return _LOCAL_CORPUS


def _tokenize(text: str) -> set[str]:
    """Simple whitespace + CJK character tokenization."""
    # Split on whitespace and punctuation, keep CJK characters individually
    tokens = set(re.findall(r'[\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+', text.lower()))
    return tokens


def _jaccard_similarity(a: set, b: set) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _search_local(query: str, top_k: int = 5, label_filter: str = None) -> list[dict]:
    """Search local JSONL corpus using token-level Jaccard similarity."""
    corpus = _load_local_corpus()
    if not corpus:
        return []

    query_tokens = _tokenize(query)
    scored = []
    for entry in corpus:
        if label_filter and entry.get("label") != label_filter:
            continue
        entry_tokens = _tokenize(entry.get("text", ""))
        score = _jaccard_similarity(query_tokens, entry_tokens)
        if score > 0.05:  # minimum relevance threshold
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, entry in scored[:top_k]:
        results.append({
            "id": entry.get("id", "unknown"),
            "snippet": entry.get("text", "")[:200],
            "label": entry.get("label", "unknown"),
            "scam_type": entry.get("scam_type"),
            "source": entry.get("source", "unknown"),
            "relevance_score": round(score, 3),
            "language": entry.get("language", "en"),
        })

    return results


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
