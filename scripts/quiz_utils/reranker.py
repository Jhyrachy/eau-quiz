"""
reranker.py
───────────
Ranks verified MCQs by multiple quality dimensions:
  • factual_score: fraction of question facts confirmed in source
  • context_score: presence of clinical context in stem (age, gender, scenario)
  • explanation_score: presence of reasoning explanation in answer
  • redundancy: how much overlap exists with other questions (set during dedup)

Each dimension is scored 0-1, then combined with weights:
  final_score = 0.4 * factual + 0.25 * context + 0.2 * (1 - redundancy) + 0.15 * explanation

Usage:
  from utils.reranker import rerank
  ranked = rerank(verified_questions)
"""

from typing import List, Dict, Any
import re


def score_factual(question: Dict[str, Any]) -> float:
    """
    Score based on how many key facts from the question are verified in source.
    """
    matched = question.get('_matched_facts', [])
    extracted = question.get('_extracted_facts', [])

    if not extracted:
        # No numeric facts — score based on option text quality
        # Check if options contain specific values (doses, percentages)
        option_texts = ' '.join(o.get('text', '') for o in question.get('options', []))
        has_specifics = bool(re.search(r'\b\d+(?:\.\d+)?\s*(?:mg|%|gy|ng|ml)\b', option_texts))
        return 0.7 if has_specifics else 0.4

    return min(len(matched) / len(extracted), 1.0)


def score_context(question: Dict[str, Any]) -> float:
    """
    Score based on clinical context in the stem:
    - Patient age (e.g., "68-year-old")
    - Gender (man/woman)
    - Clinical scenario (recurrence, metastatic, etc.)
    - Specific parameters (PSA level, Gleason score, etc.)
    """
    stem = question.get('question', '')

    has_age = bool(re.search(r'\b\d+(?:-|\s)year(?:-|\s)old\b', stem, re.IGNORECASE))
    has_gender = bool(re.search(r'\b(man|woman|male|female|patient)\b', stem, re.IGNORECASE))
    has_clinical = bool(re.search(
        r'\b(psa|gleason|metastatic|recurrence|castration|prostatectomy|tumor|cancer|stage|grade)\b',
        stem, re.IGNORECASE
    ))
    has_parameters = bool(re.search(r'\b\d+(?:\.\d+)?\s*(?:ng|mg|ml|gy|cm|mm)\b', stem))

    score = 0.0
    if has_age: score += 0.25
    if has_gender: score += 0.25
    if has_clinical: score += 0.3
    if has_parameters: score += 0.2

    return min(score, 1.0)


def score_explanation(question: Dict[str, Any]) -> float:
    """
    Score based on explanation quality:
    - Has explanation field
    - Explanation references specific data (numbers, study names, p-values)
    - Explanation is not just restating the correct answer
    """
    explanation = question.get('explanation', '')

    if not explanation or len(explanation) < 20:
        return 0.0

    # Check for specific clinical data in explanation
    has_numbers = bool(re.search(r'\b\d+(?:\.\d+)?\s*(?:%|mg|gy|ng|ml|year|yr)\b', explanation))
    has_study = bool(re.search(r'\b[A-Z]{4,}\b', explanation))  # Study acronyms
    has_pvalue = bool(re.search(r'\bp\s*[=<>]\s*\d+(?:\.\d+)?\b', explanation, re.IGNORECASE))

    score = 0.4 if len(explanation) > 50 else 0.2
    if has_numbers: score += 0.25
    if has_study: score += 0.2
    if has_pvalue: score += 0.15

    return min(score, 1.0)


def rerank(questions: List[Dict[str, Any]], redundancy_penalty: float = 0.0) -> List[Dict[str, Any]]:
    """
    Rank questions by weighted combination of quality dimensions.

    Args:
        questions: list of question dicts (should be verified first)
        redundancy_penalty: 0-1 penalty applied for each duplicate found (from dedup pass)

    Returns:
        list of questions sorted by final_score descending,
        with _factual_score, _context_score, _explanation_score, _final_score fields added
    """
    scored = []
    for q in questions:
        f = score_factual(q)
        c = score_context(q)
        e = score_explanation(q)
        r = redundancy_penalty  # 0 = no penalty, 1 = maximum penalty

        # Weighted combination
        final = 0.4 * f + 0.25 * c + 0.2 * (1 - r) + 0.15 * e

        q_copy = dict(q)
        q_copy['_factual_score'] = round(f, 3)
        q_copy['_context_score'] = round(c, 3)
        q_copy['_explanation_score'] = round(e, 3)
        q_copy['_final_score'] = round(final, 3)
        scored.append(q_copy)

    # Sort by final score descending
    scored.sort(key=lambda q: q['_final_score'], reverse=True)
    return scored


def rank_and_limit(questions: List[Dict[str, Any]], top_n: int = None) -> List[Dict[str, Any]]:
    """
    Rank questions and optionally limit to top N.
    If top_n is None, returns all questions sorted by score.
    """
    ranked = rerank(questions)
    if top_n:
        return ranked[:top_n]
    return ranked