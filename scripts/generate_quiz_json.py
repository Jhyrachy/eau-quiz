#!/usr/bin/env python3
"""
generate_quiz_json.py

MiniMax-M2.7 MCQ generator with self-evaluation feedback loop.
Each generated question is validated: an LLM "student" tries to answer it
using ONLY the guideline text. If the student can't answer correctly,
the question is regenerated with feedback (max 5 loops).

Run LOCALLY only — never in CI.
"""

import re, json, sys, os, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# ─── Config ────────────────────────────────────────────────────────────────
API_URL = "https://api.minimax.io/anthropic/v1/messages"
MODEL = "MiniMax-M2.7"
MAX_TOKENS_GEN = 2048
MAX_TOKENS_EVAL = 1024
TEMPERATURE_GEN = 0.5
TEMPERATURE_EVAL = 0.2
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")
MAX_LOOPS = 3
# Minimum score (out of 10) for each dimension to accept a question
MIN_SCORE = 7
# ─────────────────────────────────────────────────────────────────────────

HEADERS = {
    "Authorization": f"Bearer {MINIMAX_KEY}",
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01",
    "x-b3-header": MODEL,
}

SYSTEM_GEN = """You are a medical exam question writer for European Association of Urology guidelines.
Answer in English only. Always output valid JSON only — no markdown, no explanation outside JSON.
Never include trailing commas or malformed JSON.

CRITICAL RULE — ONLY use facts explicitly stated in the provided text:
- The correct answer MUST be directly stated in the text.
- Each wrong option must be plausible BUT must NOT be stated or implied as correct in the text.
- Do NOT invent clinical options (e.g. MRI, biopsy, PSA) that are not mentioned in the text.
- If the text says "X is indicated", do NOT offer "repeat PSA" or "watchful waiting" as options
  unless those are EXPLICITLY mentioned as alternatives in the text.
- Wrong options must be wrong for reasons independent of the specific text — i.e. they should
  be plausible distractors that a student might confuse with the right answer, not random nonsense."""

SYSTEM_EVAL = """You are a medical student taking a multiple-choice quiz.
You must answer based ONLY on the information provided in the "Guideline Text" section below.
Do NOT use any external knowledge — if the answer is not in the text, say you cannot determine it.
Read the question carefully, then choose the single best answer."""


def call_minimax(system: str, user_prompt: str, max_tokens: int,
                 temperature: float = 0.7) -> str:
    """Generic MiniMax-M2.7 call. Returns response text or empty string on failure."""
    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user_prompt}]
    }
    req = Request(API_URL, data=json.dumps(payload).encode(), headers=HEADERS, method="POST")
    try:
        with urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
    except HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode()[:200]}")
        return ""
    except Exception as e:
        print(f"    ✗ {e}")
        return ""

    data = json.loads(raw)
    content = data.get("content", [])
    # Skip thinking blocks — return first text block only
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")
    return ""


def extract_json(text: str) -> dict | None:
    """Try to parse JSON from LLM response."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


# ─── Step 1: Generate MCQ ────────────────────────────────────────────────────

PROMPT_GEN = """Generate multiple choice questions (single best answer) based on the guideline section below.

Requirements:
- Each question tests a specific factual knowledge point explicitly stated in the text.
- Generate 1-3 questions per section depending on content density.
- 4 answer options (A-D), one correct answer.
- The CORRECT option must be directly stated in the text.
- WRONG options must be plausible but NOT stated/implied as correct in the text.
  Common mistake to avoid: adding options like "MRI", "biopsy", "PSA test" that are not in the text.
- Include the exact source URL.
- Include a 1-2 sentence explanation citing the section number and referencing the text.
- Difficulty: easy (direct recall) / medium (application) / hard (synthesis/exception).
- Include the exact fact from the text this question is based on.

Output JSON only — no markdown, no commentary:
{{"questions": [{{"id": "...", "question": "...", "options": [{{"id":"A","text":"..."}},{{"id":"B","text":"..."}},{{"id":"C","text":"..."}},{{"id":"D","text":"..."}}], "correct": "A", "explanation": "...", "section": "...", "section_title": "...", "source_url": "...", "difficulty": "easy", "fact": "..."}}]}}

---

GUIDELINE SECTION: {section_title}
URL: {source_url}
TEXT:
{section_text}
"""


def generate_questions(section_text: str, section_title: str,
                       section_anchor: str, guideline: str,
                       source_base_url: str) -> list:
    """Call LLM to generate MCQs for a section."""
    source_url = f"{source_base_url}{section_anchor}"
    prompt = PROMPT_GEN.format(
        section_title=section_title,
        source_url=source_url,
        section_text=section_text[:4000]
    )
    text = call_minimax(SYSTEM_GEN, prompt, MAX_TOKENS_GEN, TEMPERATURE_GEN)
    if not text:
        return []
    parsed = extract_json(text)
    if not parsed:
        print(f"    ✗ No valid JSON generated")
        return []
    questions = parsed.get("questions", [])
    print(f"    → {len(questions)} question(s) generated")
    return questions


# ─── Step 2: Self-Evaluation Loop ───────────────────────────────────────────

PROMPT_EVAL = """You are a medical student taking a quiz about a guideline.
Answer based ONLY on the "Guideline Text" provided. Do NOT use external knowledge.

Question to validate:
{question}

Options:
{options_list}

Guideline Text:
{section_text}

First, state which option you would choose and WHY (引用文本中的具体句子).
Then give scores (1-10) for:
1. grounded: The correct answer IS stated in the text above (1=no, 10=absolutely clear).
2. well_formed: The question is clear, unambiguous, and answerable from the text (1=confusing, 10=crystal clear).
3. plausible: The wrong options are plausible distractors a real student might choose (1=nonsense, 10=excellent distractors).

Output JSON only:
{{"chosen": "A", "reasoning": "...", "grounded": 8, "well_formed": 9, "plausible": 7}}
"""


def evaluate_question(question: dict, section_text: str) -> dict | None:
    """LLM evaluates one question using only the guideline text. Returns score dict."""
    options_list = "\n".join(
        f"  {o['id']}. {o['text']}" for o in question.get("options", [])
    )
    prompt = PROMPT_EVAL.format(
        question=question["question"],
        options_list=options_list,
        section_text=section_text[:3000]
    )
    text = call_minimax(SYSTEM_EVAL, prompt, MAX_TOKENS_EVAL, TEMPERATURE_EVAL)
    if not text:
        return None
    parsed = extract_json(text)
    return parsed


def score_pass(scores: list[dict]) -> tuple[bool, str]:
    """
    Returns (pass, reason). pass=True if ALL questions meet MIN_SCORE on all dims.
    Returns failing reason for the first question that doesn't pass.
    """
    for i, s in enumerate(scores):
        for dim in ("grounded", "well_formed", "plausible"):
            v = s.get(dim, 0)
            if v < MIN_SCORE:
                reason = (f"Q{i+1} FAILED: {dim}={v}/{MIN_SCORE} — "
                          f"LLM chose '{s.get('chosen')}': {s.get('reasoning', '')[:100]}")
                return False, reason
    return True, "all passed"


# ─── Step 3: Main Loop ───────────────────────────────────────────────────────

def validate_question(question: dict, section_text: str,
                      section_title: str) -> tuple[bool, dict, list[dict]]:
    """
    Run the self-evaluation loop for one question.
    Returns (passed, final_question_dict, all_attempts_scores).
    """
    for loop in range(1, MAX_LOOPS + 1):
        print(f"    Loop {loop}/{MAX_LOOPS}...")
        score = evaluate_question(question, section_text)
        if score is None:
            print(f"      ✗ evaluation failed, retrying")
            time.sleep(2)
            continue

        g = score.get("grounded", 0)
        wf = score.get("well_formed", 0)
        pl = score.get("plausible", 0)
        chosen = score.get("chosen", "?")
        print(f"      grounded={g}  well_formed={wf}  plausible={pl}  → chosen={chosen}")

        all_dims_ok = all(v >= MIN_SCORE for v in [g, wf, pl])
        if all_dims_ok:
            return True, question, [score]

        # Regenerate with feedback
        print(f"      ⚠ low score — regenerating with feedback...")
        time.sleep(1)

        # Build enhanced prompt with previous attempt
        feedback_prompt = PROMPT_REGEN_FEEDBACK.format(
            section_title=section_title,
            source_url=question.get("source_url", ""),
            section_text=section_text[:4000],
            failed_question=question["question"],
            failed_options="\n".join(
                f"  {o['id']}. {o['text']}" for o in question.get("options", [])
            ),
            correct_answer=question["correct"],
            failed_fact=question.get("fact", ""),
            feedback=(
                f"grounded={g} (must be ≥{MIN_SCORE}/10 — "
                f"correct answer must be MORE explicitly stated in text); "
                f"well_formed={wf} (must be ≥{MIN_SCORE}/10); "
                f"plausible={pl} (must be ≥{MIN_SCORE}/10 — "
                f"wrong options must be plausible but NOT stated as correct in text)"
            )
        )
        new_text = call_minimax(SYSTEM_GEN, feedback_prompt, MAX_TOKENS_GEN, TEMPERATURE_GEN)
        if not new_text:
            print(f"      ✗ regeneration failed")
            return False, question, [score]

        new_parsed = extract_json(new_text)
        if new_parsed and new_parsed.get("questions"):
            question = new_parsed["questions"][0]
            # Re-score the new version in the next loop
        else:
            print(f"      ✗ no valid JSON from regeneration")

    # Exhausted loops
    return False, question, []


PROMPT_REGEN_FEEDBACK = """You are a medical exam question writer for European Association of Urology guidelines.
Answer in English only. Always output valid JSON only — no markdown, no explanation outside JSON.

Your previous question for this section was REJECTED by the evaluation system:
- Question: {failed_question}
- Options: {failed_options}
- Correct: {correct_answer}
- Fact tested: {failed_fact}
- Feedback: {feedback}

CRITICAL RULES — write a NEW improved question:
1. The CORRECT answer MUST be directly, EXPLICITLY stated in the guideline text below.
2. Wrong options must be plausible distractors a real student might confuse — but they must NOT be stated/implied as correct in the text.
3. Do NOT use options like "MRI", "biopsy", "PSA test", "watchful waiting" unless those are EXPLICITLY mentioned as alternatives in the text for this specific fact.
4. If the text says "X is indicated OR Y", do NOT offer "repeat PSA" or "reassure" as options.

Output JSON only:
{{"questions": [{{"id": "...", "question": "...", "options": [{{"id":"A","text":"..."}},{{"id":"B","text":"..."}},{{"id":"C","text":"..."}},{{"id":"D","text":"..."}}], "correct": "A", "explanation": "...", "section": "...", "section_title": "...", "source_url": "...", "difficulty": "easy", "fact": "..."}}]}}

---

GUIDELINE SECTION: {section_title}
URL: {source_url}
TEXT:
{section_text}
"""


# ─── Step 4: Process one section ─────────────────────────────────────────────

def process_section(section: dict, guideline: str, source_base_url: str) -> list:
    """Generate + validate questions for a section. Returns list of accepted questions."""
    section_text = section.get("text", "").strip()
    if len(section_text) < 80:  # skip stubs
        return []

    section_title = section.get("title", "")
    # Use nav_anchor (nearest h2/h3 ancestor) for source URL — h4 anchors don't scroll
    section_anchor = section.get("nav_anchor", section.get("anchor", ""))

    print(f"\n  Section: {section_title}")
    print(f"  Source: {source_base_url}{section_anchor}")
    questions = generate_questions(
        section_text, section_title, section_anchor, guideline, source_base_url
    )
    if not questions:
        return []

    accepted = []
    for q in questions:
        passed, final_q, _ = validate_question(q, section_text, section_title)
        if passed:
            print(f"    ✓ ACCEPTED")
            accepted.append(final_q)
        else:
            print(f"    ✗ REJECTED (exceeded {MAX_LOOPS} loops)")
    return accepted


# ─── Step 5: Chapter-level ───────────────────────────────────────────────────

def generate_for_chapter(guideline_slug: str, chapter_slug: str) -> dict:
    """Load scraped chapter, generate validated MCQs for all sections."""
    chapter_file = Path(f"data/chapters/{guideline_slug}/{chapter_slug}.json")
    if not chapter_file.exists():
        print(f"  ✗ Chapter file not found: {chapter_file}")
        return {"guideline": guideline_slug, "chapter": chapter_slug, "questions": []}

    with open(chapter_file, encoding="utf-8") as f:
        chapter = json.load(f)

    all_questions = []
    source_base = chapter.get("url", "")

    for section in chapter.get("sections", []):
        accepted = process_section(section, guideline_slug, source_base)
        for q in accepted:
            q["id"] = (f"{guideline_slug}-{chapter_slug}-"
                       f"{section.get('anchor', 's').lstrip('#')}-"
                       f"{len(all_questions)+1:03d}")
            q["chapter"] = chapter_slug
            q["guideline"] = guideline_slug
        all_questions.extend(accepted)

    return {
        "guideline": guideline_slug,
        "chapter": chapter_slug,
        "url": source_base,
        "question_count": len(all_questions),
        "questions": all_questions
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

def load_guidelines():
    with open("data/guidelines.json", encoding="utf-8") as f:
        return json.load(f)


def main():
    if not MINIMAX_KEY:
        print("ERROR: MINIMAX_API_KEY env var not set")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python generate_quiz_json.py <guideline_slug> <chapter_slug>")
        print("       python generate_quiz_json.py --all")
        sys.exit(1)

    if sys.argv[1] == "--all":
        guidelines = load_guidelines()
        total_q = 0
        for g in guidelines:
            slug = g["slug"]
            for ch in g["chapters"]:
                cs = ch["slug"]
                out_file = Path(f"data/questions/{slug}_{cs}.json")
                if out_file.exists():
                    print(f"SKIP {slug}/{cs} (exists)")
                    continue
                print(f"\n[{slug}] {cs}")
                result = generate_for_chapter(slug, cs)
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"  ✓ {out_file} — {result['question_count']} questions")
                total_q += result["question_count"]
        print(f"\nTotal: {total_q} questions")
    else:
        guideline_slug = sys.argv[1]
        chapter_slug = sys.argv[2]
        result = generate_for_chapter(guideline_slug, chapter_slug)
        out_file = Path(f"data/questions/{guideline_slug}_{chapter_slug}.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Saved → {out_file} ({result['question_count']} questions)")


if __name__ == "__main__":
    main()
