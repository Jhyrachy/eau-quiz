#!/usr/bin/env python3
"""
Concurrent section MCQ generator.
Processes multiple sections in parallel using ThreadPoolExecutor.
Each section is a separate API call; self-eval loops are sequential within each section.

Usage:
    python scripts/generate_concurrent.py prostate-cancer diagnostic-evaluation 4
"""
import json, sys, os, time, re, concurrent.futures
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from threading import Lock

# ─── Config ────────────────────────────────────────────────────────────────
API_URL = "https://api.minimax.io/anthropic/v1/messages"
MODEL = "MiniMax-M2.7"
MAX_TOKENS_GEN = 2048
MAX_TOKENS_EVAL = 1024
TEMPERATURE_GEN = 0.5
TEMPERATURE_EVAL = 0.2
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")
MAX_LOOPS = 3
MIN_SCORE = 7
MAX_WORKERS = 4  # concurrent API calls
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
- Wrong options must be wrong for reasons independent of the specific text."""

SYSTEM_EVAL = """You are a medical student taking a multiple-choice quiz.
You must answer based ONLY on the information provided in the "Guideline Text" section below.
Do NOT use any external knowledge — if the answer is not in the text, say you cannot determine it."""

PROMPT_GEN = """Generate multiple choice questions (single best answer) based on the guideline section below.

Requirements:
- Each question tests a specific factual knowledge point explicitly stated in the text.
- Generate 1-3 questions per section depending on content density.
- 4 answer options (A-D), one correct answer.
- The CORRECT option must be directly stated in the text.
- WRONG options must be plausible but NOT stated/implied as correct in the text.
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
{section_text}"""

PROMPT_EVAL = """You are a medical student taking a quiz about a guideline.
Answer based ONLY on the "Guideline Text" provided. Do NOT use external knowledge.

Question to validate:
{question}

Options:
{options_list}

Guideline Text:
{section_text}

First, state which option you would choose and WHY.
Then give scores (1-10) for:
1. grounded: The correct answer IS stated in the text above (1=no, 10=absolutely clear).
2. well_formed: The question is clear, unambiguous, and answerable from the text (1=confusing, 10=crystal clear).
3. plausible: The wrong options are plausible distractors a real student might choose (1=nonsense, 10=excellent distractors).

Output JSON only:
{{"chosen": "A", "reasoning": "...", "grounded": 8, "well_formed": 9, "plausible": 7}}"""


def call_minimax(system: str, user_prompt: str, max_tokens: int, temperature: float = 0.7) -> str:
    payload = {
        "model": MODEL, "max_tokens": max_tokens, "temperature": temperature,
        "system": system, "messages": [{"role": "user", "content": user_prompt}]
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
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")
    return ""


def extract_json(text: str):
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


def process_section(section: dict, guideline: str, source_base: str) -> list:
    """Generate + validate questions for ONE section. Returns list of accepted questions."""
    section_text = section.get("text", "").strip()
    if len(section_text) < 80:
        return []

    section_title = section.get("title", "")
    section_anchor = section.get("nav_anchor", section.get("anchor", ""))
    source_url = f"{source_base}{section_anchor}"

    print(f"  [{time.strftime('%H:%M:%S')}] Section: {section_title[:50]}")

    prompt = PROMPT_GEN.format(
        section_title=section_title,
        source_url=source_url,
        section_text=section_text[:4000]
    )
    text = call_minimax(SYSTEM_GEN, prompt, MAX_TOKENS_GEN, TEMPERATURE_GEN)
    if not text:
        print(f"    ✗ no response")
        return []

    parsed = extract_json(text)
    if not parsed or not parsed.get("questions"):
        print(f"    ✗ no valid JSON")
        return []

    accepted = []
    for q in parsed["questions"]:
        q["source_url"] = source_url
        q["section_title"] = section_title

        for loop in range(1, MAX_LOOPS + 1):
            options_list = "\n".join(f"  {o['id']}. {o['text']}" for o in q.get("options", []))
            eval_prompt = PROMPT_EVAL.format(
                question=q["question"],
                options_list=options_list,
                section_text=section_text[:3000]
            )
            score_text = call_minimax(SYSTEM_EVAL, eval_prompt, MAX_TOKENS_EVAL, TEMPERATURE_EVAL)
            score = extract_json(score_text) if score_text else None

            if score:
                g = score.get("grounded", 0)
                wf = score.get("well_formed", 0)
                pl = score.get("plausible", 0)
                chosen = score.get("chosen", "?")
                print(f"    Q{len(accepted)+1}: loop={loop} g={g} wf={wf} pl={pl} → {chosen}")
                if all(v >= MIN_SCORE for v in [g, wf, pl]):
                    accepted.append(q)
                    break
                if loop < MAX_LOOPS:
                    time.sleep(0.5)
            else:
                print(f"    Q{len(accepted)+1}: loop={loop} eval failed")
                break

        if len([a for a in accepted if a.get("_qid") == id(q)]) == 0 and len(accepted) < len(parsed["questions"]):
            # Not yet counted — question either accepted or exhausted loops
            pass

    print(f"    → {len(accepted)}/{len(parsed['questions'])} accepted")
    return accepted


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_concurrent.py <guideline_slug> <chapter_slug> [max_workers]")
        sys.exit(1)

    if not MINIMAX_KEY:
        print("ERROR: MINIMAX_API_KEY not set")
        sys.exit(1)

    guideline_slug = sys.argv[1]
    chapter_slug = sys.argv[2]
    max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else MAX_WORKERS

    chapter_file = Path(f"data/chapters/{guideline_slug}/{chapter_slug}.json")
    if not chapter_file.exists():
        print(f"✗ Chapter file not found: {chapter_file}")
        sys.exit(1)

    with open(chapter_file, encoding="utf-8") as f:
        chapter = json.load(f)

    source_base = chapter.get("url", "")
    sections = [s for s in chapter.get("sections", []) if len(s.get("text", "").strip()) >= 80]
    print(f"Chapter: {chapter_slug} — {len(sections)} sections to process (max_workers={max_workers})")

    all_questions = []
    counter_lock = Lock()
    next_id = [1]  # mutable container for closure

    def assign_ids(qs):
        with counter_lock:
            for q in qs:
                q["id"] = f"{guideline_slug}-{chapter_slug}-{next_id[0]:03d}"
                next_id[0] += 1
                q["chapter"] = chapter_slug
                q["guideline"] = guideline_slug

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_section = {
            executor.submit(process_section, s, guideline_slug, source_base): s
            for s in sections
        }
        for future in concurrent.futures.as_completed(future_to_section):
            questions = future.result()
            assign_ids(questions)
            all_questions.extend(questions)

    result = {
        "guideline": guideline_slug,
        "chapter": chapter_slug,
        "url": source_base,
        "question_count": len(all_questions),
        "questions": all_questions
    }

    out_path = Path(f"data/questions/{guideline_slug}_{chapter_slug}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Done: {result['question_count']} questions → {out_path}")


if __name__ == "__main__":
    main()
