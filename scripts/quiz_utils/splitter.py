"""
splitter.py
───────────
Splits section text into chunks for bullet extraction.

For M2.7: context window ≈ 200K tokens ≈ 800K chars.
We use 50% of context as working limit (~400K chars) to leave room
for system prompt, output buffer, and quality focus.

Rules:
  • < 400K chars → 1 chunk (entire section)
  • ≥ 400K chars → split into N chunks at natural sentence boundary
  • No overlap needed (bullets are extracted independently per chunk)

Usage:
  from utils.splitter import split_section
  chunks = split_section(section_text, max_chars=400_000)
"""

import re
from typing import List


def split_section(text: str, max_chars: int = 400_000) -> List[str]:
    """
    Split section text into chunks that fit in half the context window.

    Args:
        text: full section text
        max_chars: working limit (default 400K ≈ half of 800K context)

    Returns:
        list of text chunks, each < max_chars
    """
    if len(text) <= max_chars:
        return [text]

    # Split at sentence boundary (.)
    # Find all sentence ends
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    
    chunks = []
    current_chunk = []
    current_len = 0

    for sentence in sentences:
        # Rough char count (sentence + space)
        sent_len = len(sentence) + 1
        if current_len + sent_len > max_chars and current_chunk:
            chunks.append(' '.join(current_chunk))
            # Start new chunk — no overlap needed
            current_chunk = [sentence]
            current_len = sent_len
        else:
            current_chunk.append(sentence)
            current_len += sent_len

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks


def split_into_n(text: str, n: int) -> List[str]:
    """
    Split text into exactly N chunks (sentence-aligned).
    Used when we know we want N buckets (e.g., 2 for large sections).

    Args:
        text: full section text
        n: number of chunks (minimum 2)

    Returns:
        list of N text chunks
    """
    if n < 2:
        return [text]

    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    total = len(sentences)
    chunk_size = total / n

    chunks = []
    for i in range(n):
        start = int(i * chunk_size)
        end = int((i + 1) * chunk_size) if i < n - 1 else total
        chunk = ' '.join(sentences[start:end]).strip()
        if chunk:
            chunks.append(chunk)

    return chunks