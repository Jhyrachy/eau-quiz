"""
dedup.py
────────
Deduplicates MCQs across chunks/sections using Jaccard similarity.
Removes near-duplicates (similarity > 0.6) keeping the highest-scored.

Usage:
  from utils.dedup import deduplicate
  unique = deduplicate(questions, threshold=0.6)
"""

from typing import List, Dict, Any
import re


def jaccard_similarity(text1: str, text2: str) -> float:
    """
    Compute Jaccard similarity between two texts.
    Tokenize on whitespace and punctuation, lowercase.

    Returns:
        float between 0 (completely different) and 1 (identical)
    """
    # Extract meaningful tokens (words 3+ chars)
    tokens1 = set(re.findall(r"\b[a-z]{3,}\b", text1.lower()))
    tokens2 = set(re.findall(r"\b[a-z]{3,}\b", text2.lower()))

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


def extract_stem(question: Dict[str, Any]) -> str:
    """
    Extract the question stem (everything before the first option letter).
    Strips numbering, "correct answer" notes, etc.
    """
    stem = question.get('question', '')
    # Remove leading number/letter like "1.", "A.", "Q1:"
    stem = re.sub(r'^[\d]+[\.\)]\s*', '', stem)
    stem = re.sub(r'^["\(\[]?[A-Z][\.\)\]\s]+', '', stem)
    return stem.strip()


def deduplicate(questions: List[Dict[str, Any]], threshold: float = 0.6) -> List[Dict[str, Any]]:
    """
    Remove near-duplicate questions using Jaccard similarity on stems.
    When two questions exceed threshold similarity, keep the one with
    higher factual_score (if present) or the first occurrence.

    Args:
        questions: list of question dicts (may have '_factual_score' from reranker)
        threshold: similarity threshold (default 0.6 = 60% overlap)

    Returns:
        list of deduplicated questions, preserving original order
    """
    if not questions:
        return []

    # Sort by factual_score descending so we keep better questions
    sorted_qs = sorted(questions, key=lambda q: q.get('_factual_score', 0), reverse=True)

    keep = []
    for q in sorted_qs:
        stem = extract_stem(q)
        is_duplicate = False
        for kept_q in keep:
            kept_stem = extract_stem(kept_q)
            sim = jaccard_similarity(stem, kept_stem)
            if sim > threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            keep.append(q)

    # Restore original ordering by position in input list
    seen_ids = set()
    result = []
    for q in questions:
        q_id = q.get('id') or q.get('question', '')[:50]
        if q_id not in seen_ids:
            # Check if this question survived
            for kept in keep:
                kept_id = kept.get('id') or kept.get('question', '')[:50]
                if kept_id == q_id or jaccard_similarity(
                    extract_stem(q), extract_stem(kept)
                ) > threshold:
                    result.append(q)
                    seen_ids.add(q_id)
                    break

    return result