"""
verifier.py
───────────
Verifies a generated MCQ against the original section text.
Uses fuzzy matching for key facts (numbers, percentages, study names, p-values).

Usage:
  from utils.verifier import verify_question
  is_valid = verify_question(question_dict, section_text)
"""

import re
from typing import List, Dict, Any, Tuple


def normalize(text: str) -> str:
    """
    Normalize text for fuzzy comparison.
    - lowercase
    - collapse whitespace
    - decode HTML entities
    - keep clinical symbols (≥, <, etc.) and numbers
    """
    text = text.lower()
    # Decode common HTML entities
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&ge;', '≥', text)
    text = re.sub(r'&le;', '≤', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_key_facts(text: str) -> List[str]:
    """
    Extract clinically significant facts from text:
    - Numbers with units (percentages, doses, ages, p-values)
    - Study names / trial names
    - Clinical thresholds and cutoffs
    - Grade levels and recommendations (strong/weak)
    """
    facts = []

    # Numbers with clinical units
    patterns = [
        r'\b\d+(?:\.\d+)?\s*(?:mg|ml|gy|gray|ng|ml|μg|cm|mm|mmol|l|g|mmhg|kda|%|year|yr)s?\b',
        r'\b\d+(?:\.\d+)?\s*(?:%|percent)\b',
        r'\b[pP]\s*[=<>]\s*\d+(?:\.\d+)?\b',
        r'\b(p\s*=\s*\d+(?:\.\d+)?)\b',
        r'\bHR\s*[=<>]\s*\d+(?:\.\d+)?\b',
        r'\bOR\s*[=<>]\s*\d+(?:\.\d+)?\b',
        r'\bRR\s*[=<>]\s*\d+(?:\.\d+)?\b',
        r'\bCI[:\s]+\d+(?:\.\d+)?[-–]\d+(?:\.\d+)?%?\b',
        r'\b(?:low|moderate|high|strong|weak)\s+recommendation\b',
        r'\b(?:strong|conditional|weak)\s+(?:recommendation|basis)\b',
        r'\bgrade\s+[A-C]\b',
        r'\b(?:level\s+of\s+evidence|loe)\s*[=:]\s*[IVX]+\b',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            fact = match.group().strip()
            if fact and len(fact) > 2:
                facts.append(fact.lower())

    # Study names (caps words like "RADICALS", "GETUG", "STAMPEDE")
    study_pattern = r'\b[A-Z]{4,}(?:\s+[A-Z]{2,})*\b'
    for match in re.finditer(study_pattern, text):
        study = match.group().strip()
        # Exclude common abbreviations that aren't study names
        if study not in ('PSA', 'MRI', 'CT', 'PET', 'US', 'PSA', 'Gy', 'RNA', 'DNA', 'WHO'):
            facts.append(normalize(study))

    # Clinical terms that indicate verifiable facts
    clinical_terms = [
        r'(?:overall\s+survival|os|event-free\s+survival|efs|pfs|dfs)',
        r'(?:hazard\s+ratio|hr|odds\s+ratio|or|relative\s+risk|rr)',
        r'(?:median|mean|average)\s+\d+',
        r'(?:range|interval)\s+\d+[-–]\d+',
        r'statistically\s+significant',
        r'p\s*[=<>]\s*\d+',
    ]
    for pattern in clinical_terms:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            facts.append(match.group().lower())

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for f in facts:
        if f not in seen:
            seen.add(f)
            unique.append(f)

    return unique


def verify_question(question: Dict[str, Any], section_text: str) -> Tuple[bool, List[str], List[str]]:
    """
    Verify a generated MCQ against the source section text.

    Returns:
        (is_verified, extracted_facts, matched_facts)
        - is_verified: True if at least one key fact from the question is found in source
        - extracted_facts: facts extracted from the question
        - matched_facts: facts that were found in the source text
    """
    extracted = extract_key_facts(question.get('question', ''))
    # Also check options for facts (wrong answers may contain verifiable data)
    for opt in question.get('options', []):
        extracted.extend(extract_key_facts(opt.get('text', '')))

    # Remove duplicates
    extracted = list(dict.fromkeys(extracted))

    if not extracted:
        # No extractable numeric facts — use keyword fallback
        # Check if key clinical terms from the question appear in source
        question_lower = normalize(question.get('question', ''))
        # Extract significant words (length > 4, not common words)
        stopwords = {'which', 'what', 'when', 'where', 'who', 'how', 'does', 'doesnt', 'cannot', 'should', 'may', 'might', 'following', 'patient', 'treatment', 'therapy', 'cancer', 'prostate'}
        words = [w for w in re.findall(r'\b[a-z]{5,}\b', question_lower) if w not in stopwords]
        matched = [w for w in words if normalize(w) in normalize(section_text)]
        return (len(matched) >= 1, [], matched)

    # Fuzzy match: for each extracted fact, check if it appears in source
    normalized_source = normalize(section_text)
    matched_facts = []
    for fact in extracted:
        if fact in normalized_source:
            matched_facts.append(fact)

    return (len(matched_facts) >= 1, extracted, matched_facts)


def verify_batch(questions: List[Dict[str, Any]], section_text: str) -> List[Dict[str, Any]]:
    """
    Verify all questions in a batch.
    Adds 'verified' boolean field to each question dict.

    Args:
        questions: list of question dicts
        section_text: full section text (for reference)

    Returns:
        list of questions with 'verified' field added
    """
    verified_questions = []
    for q in questions:
        is_verified, extracted, matched = verify_question(q, section_text)
        q_copy = dict(q)
        q_copy['verified'] = is_verified
        q_copy['_extracted_facts'] = extracted
        q_copy['_matched_facts'] = matched
        verified_questions.append(q_copy)
    return verified_questions