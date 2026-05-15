"""
generate_section.py
───────────────────
Generates MCQs from a single guideline section.

Pipeline:
  1. Load section JSON (anchor, title, breadcrumb, text, nav_anchor)
  2. Extract bullet points from section text (1 LLM call)
  3. Generate 1 MCQ per bullet (1 LLM call per bullet)
  4. Verify all questions against full section text
  5. Rerank + deduplicate
  6. Save to data/questions/{guideline}/{section_anchor}.json

Usage:
  python scripts/generate_section.py prostate-cancer treatment#6.4.6

Args:
  sys.argv[1]: guideline slug (e.g., 'prostate-cancer')
  sys.argv[2]: section anchor (e.g., 'treatment#6.4.6')
"""

import json
import sys
import os
import time
import urllib.request
import re
from pathlib import Path

# Ensure scripts/utils is on the path (before any stdlib utils conflicts)
sys.path.insert(0, str(Path(__file__).parent))
from quiz_utils.verifier import verify_batch, extract_key_facts
from quiz_utils.reranker import rerank
from quiz_utils.dedup import deduplicate

# ── Config ────────────────────────────────────────────────────────────────────

API_KEY = "sk-cp-xloQyJmy5KtMNIysmVocs7aicnyRuLnEC69KqquSclUCtyHR9wXNwkA8CffSxDXzQ7XLvi04SLm4luUe2bXkE3T-YXUxErcoe63U04Yh7fpVMRVwzK5ABWY"
API_URL = "https://api.minimax.io/anthropic/v1/messages"
MAX_CHARS_WORKING = 400_000  # ~50% of 800K context, safe limit

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "X-B3-Client-ID": "hermes-agent",
    "anthropic-version": "2023-06-01",
}

# ── API Helpers ───────────────────────────────────────────────────────────────

def call_llm(system: str, user: str, max_tokens: int = 4096, temperature: float = 0.7) -> str:
    """Single LLM API call with retry."""
    body = {
        "model": "MiniMax-M2.7-32K",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            text = parse_llm_response(raw)
            return text
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"    ⚠️  Attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed after 5 attempts")


def parse_json_response(text: str):
    """Extract JSON array/object from LLM response text (handles markdown code blocks and thinking blocks)."""
    text = re.sub(r"^```json\s*", "", text.strip()).replace("```", "").strip()
    start = next((i for i, c in enumerate(text) if c in "[{"), None)
    if start is None:
        return None
    if text[start] == "[":
        depth, end = 0, start
        for i, c in enumerate(text[start:], start):
            depth += 1 if c == "[" else -1 if c == "]" else 0
            if c == "]" and depth == 0:
                end = i + 1
                break
        try:
            return json.loads(text[start:end])
        except:
            pass
    else:
        for end in range(len(text), start, -1):
            try:
                return json.loads(text[start:end])
            except:
                pass
    return None


def parse_llm_response(raw: dict):
    """
    Parse MiniMax response dict — handles both standard content blocks
    and the thinking+text block format.
    Returns the text content as string.
    """
    # Check for content blocks
    content = raw.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text":
                    return block.get("text", "")
                elif btype == "thinking":
                    # Skip thinking blocks, continue to next block
                    continue
    # Fallback: return as string
    return str(raw.get("content", ""))


# ── Core Pipeline ─────────────────────────────────────────────────────────────

SYSTEM_EXTRACT = """You are a medical guideline analyst.
Your task: extract a bullet list of clinically significant facts from the guideline text.
Each bullet = ONE testable fact (e.g., a numeric threshold, a study conclusion, a recommendation).

Output format — a JSON array of strings:
["fact 1", "fact 2", ...]

Rules:
- Each bullet = exactly ONE fact, specific and testable
- Include numbers with units: "PSA ≥ 10 ng/mL indicates high risk"
- Include study names: "GETUG-AFU 16 trial showed no OS benefit"
- Include recommendations: "Strong recommendation for ADT in castration-resistant disease"
- Include survival data: "Median OS 3.2 years in metastatic castration-resistant"
- Include cutoffs: "PSA doubling time < 3 months associated with worse prognosis"
- Skip vague statements, repeated concepts, and redundant facts
- Maximum 30 bullets per section — quality over quantity
- Language: English only"""


def extract_bullets(section_text: str, breadcrumb: str) -> list:
    """Extract key facts as bullet list from section text."""
    user = f"""GUIDELINE SECTION: {breadcrumb}

TEXT:
{section_text[:MAX_CHARS_WORKING]}

Extract all clinically significant, testable facts as a JSON array of strings.
Max 30 bullets. Focus on facts that could become MCQ answers or stems."""
    resp = call_llm(SYSTEM_EXTRACT, user, max_tokens=2048)
    parsed = parse_json_response(resp)
    if isinstance(parsed, list):
        return [b for b in parsed if isinstance(b, str) and len(b) > 10]
    return []


SYSTEM_MCQ = """You are a medical exam question writer for urology guidelines.
Generate ONE USMLE-style MCQ from the given fact.

Output format — a JSON object (NOT an array):
{
  "id": "guideline-section-index",
  "question": "A [age]-year-old [male/female] with [clinical context]...",
  "options": [
    {"id": "A", "text": "..."},
    {"id": "B", "text": "..."},
    {"id": "C", "text": "..."},
    {"id": "D", "text": "..."}
  ],
  "correct": 0,
  "explanation": "...",
  "section": "section title",
  "chapter": "chapter title",
  "guideline": "guideline name",
  "source_text": "the original fact"
}

Rules:
- Stem includes patient age, gender, clinical context
- Wrong answers are plausible but NOT in the source text
- Only use information from the provided fact
- Correct answer has id "A", "B", "C", or "D" — stored as integer 0-3
- Explanation references specific data from fact (numbers, study names)
- source_text = the fact this question was generated from
- Output MUST be valid JSON object (no markdown, no extra text)"""


def generate_mcq_from_bullet(bullet: str, section_text: str, breadcrumb: str,
                              q_index: int, guideline_slug: str, section_slug: str) -> dict:
    """Generate 1 MCQ from 1 bullet fact."""
    user = f"""Generate ONE USMLE-style MCQ from this guideline fact.

FACT: {bullet}

SECTION: {breadcrumb}

SOURCE CONTEXT (for reference only — do not use facts outside this):
{section_text[:5000]}

Output JSON object only — no explanation, no markdown."""
    resp = call_llm(SYSTEM_MCQ, user, max_tokens=1024)
    parsed = parse_json_response(resp)
    if isinstance(parsed, dict):
        q = parsed
        q["id"] = f"{guideline_slug}-{section_slug}-{q_index:03d}"
        q["guideline"] = guideline_slug
        return q
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def generate_section(guideline_slug: str, section_anchor: str) -> dict:
    """
    Generate all MCQs for one section.
    Returns result dict with questions[], metadata.
    """
    # Load section JSON
    section_file = Path(f"/opt/data/eau-quiz/data/chapters/{guideline_slug}/{section_anchor.split('#')[0]}.json")
    if not section_file.exists():
        print(f"Section file not found: {section_file}")
        return {"questions": [], "metadata": {"error": "file not found"}}

    with open(section_file) as f:
        data = json.load(f)

    # Find the specific section
    # section_anchor format: "filename#anchor-fragment" (e.g. "treatment#6.4.6")
    # JSON anchor format: "#anchor-fragment" (e.g. "#6.4.6-hormonal-therapy-for-relapsing-patients")
    section_anchor_part = section_anchor.split("#")[-1]  # "6.4.6"
    processed_part = section_anchor_part.replace(".", "-")  # "6-4-6"

    section = None
    for sec in data.get("sections", []):
        json_anchor = sec.get("anchor", "").replace("#", "").replace(".", "-")  # "6-4-6-hormonal-therapy-for-relapsing-patients"
        if processed_part in json_anchor:  # "6-4-6" in "6-4-6-hormonal-therapy-for-relapsing-patients"
            section = sec
            break

    if not section:
        print(f"Section '{section_anchor}' not found in {section_file}")
        return {"questions": [], "metadata": {"error": "section not found"}}

    text = section.get("text", "")
    title = section.get("title", "")
    nav_anchor = section.get("nav_anchor", "")
    breadcrumb = f"{data.get('breadcrumb', guideline_slug)} — {title}"

    print(f"\n{'='*60}")
    print(f"Generating: {guideline_slug} / {section_anchor}")
    print(f"Text size: {len(text):,} chars")
    print(f"{'='*60}")

    # Step 1: Extract bullets
    print("Step 1/4: Extracting bullets...")
    bullets = extract_bullets(text, breadcrumb)
    print(f"  → {len(bullets)} bullets extracted")
    if not bullets:
        print("  ⚠️  No bullets extracted — skipping section")
        return {"questions": [], "metadata": {"bullets_extracted": 0}}

    # Step 2: Generate MCQ per bullet
    print(f"Step 2/4: Generating {len(bullets)} MCQs (1 per bullet)...")
    questions = []
    for i, bullet in enumerate(bullets):
        print(f"  [{i+1}/{len(bullets)}] Generating from: {bullet[:60]}...")
        q = generate_mcq_from_bullet(
            bullet=bullet,
            section_text=text,
            breadcrumb=breadcrumb,
            q_index=i,
            guideline_slug=guideline_slug,
            section_slug=section_anchor.replace("#", "-"),
        )
        if q:
            questions.append(q)
        time.sleep(1)  # Rate limit safety

    print(f"  → {len(questions)} questions generated")

    # Step 3: Verify
    print(f"Step 3/4: Verifying {len(questions)} questions against source...")
    verified = verify_batch(questions, text)
    verified_count = sum(1 for q in verified if q.get("verified", False))
    print(f"  → {verified_count}/{len(questions)} verified")
    verified_questions = [q for q in verified if q.get("verified", False)]

    if not verified_questions:
        print("  ⚠️  No questions passed verification")
        # Still save unverified with flag (user can review)
        verified_questions = verified

    # Step 4: Rerank + dedup
    print(f"Step 4/4: Reranking and deduplicating...")
    reranked = rerank(verified_questions)
    deduplicated = deduplicate(reranked)
    print(f"  → {len(deduplicated)} questions after dedup")

    result = {
        "questions": deduplicated,
        "metadata": {
            "guideline": guideline_slug,
            "section": section_anchor,
            "title": title,
            "nav_anchor": nav_anchor,
            "breadcrumb": breadcrumb,
            "bullets_extracted": len(bullets),
            "questions_generated": len(questions),
            "verified": verified_count,
            "final": len(deduplicated),
        },
    }

    # Save
    out_dir = Path(f"/opt/data/eau-quiz/data/questions/{guideline_slug}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{section_anchor.replace('#', '-')}.json"
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved {len(deduplicated)} questions → {out_file}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_section.py <guideline-slug> <section-anchor>")
        print("Example: python generate_section.py prostate-cancer treatment#6.4.6")
        sys.exit(1)

    guideline = sys.argv[1]
    section = sys.argv[2]
    result = generate_section(guideline, section)
    print(f"\nDone. {len(result.get('questions', []))} questions saved.")