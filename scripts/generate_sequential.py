#!/opt/data/.venv/bin/python3.13
"""
Sequential MCQ generator — clean, resumable, no arbitrary delays.
"""
import json, time, sys, random, re, urllib.request, urllib.error
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY = "sk-cp-xloQyJmy5KtMNIysmVocs7aicnyRuLnEC69KqquSclUCtyHR9wXNwkA8CffSxDXzQ7XLvi04SLm4luUe2bXkE3T-YXUxErcoe63U04Yh7fpVMRVwzK5ABWY"
GUIDELINE = sys.argv[1] if len(sys.argv) > 1 else "prostate-cancer"
MAX_RETRIES = 5
BASE_DELAY = 15
MODEL = "MiniMax-M2.7"
API_URL = "https://api.minimax.io/anthropic/v1/messages"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
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

# ── API Call ────────────────────────────────────────────────────────────────
def call_minimax(system: str, user_prompt: str, max_tokens: int, temperature: float = 0.7) -> str:
    payload = {
        "model": MODEL, "max_tokens": max_tokens, "temperature": temperature,
        "system": system, "messages": [{"role": "user", "content": user_prompt}]
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode(), headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode()[:200]}")
        return ""
    except Exception as e:
        print(f"    Network error: {e}")
        return ""
    try:
        data = json.loads(raw)
        content = data.get("content", [])
        if content and isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    return block["text"].strip()
        return ""
    except Exception:
        return ""

def extract_json(text: str):
    """Extract JSON from response text."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try markdown code block
    m = re.search(r'\{[^{}]*"questions"[^\}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # Try first { ... last }
    idx = text.find("{")
    if idx != -1:
        last = text.rfind("}")
        if last > idx:
            try:
                return json.loads(text[idx:last+1])
            except json.JSONDecodeError:
                pass
    return None

# ── Question Generation ─────────────────────────────────────────────────────
def generate_for_section(section, guideline, chapter_slug, next_id):
    text = section["text"]
    anchor = section["anchor"]
    title = section["title"]
    tables = section.get("tables", [])
    tables_md = ""
    for i, tbl in enumerate(tables[:2]):
        rows = tbl[:6]
        tables_md += f"\n[Table {i+1}]\n" + "\n".join(
            "| " + " | ".join(str(c) for c in r) + " |" for r in rows) + "\n"

    user = f"""Guideline Text:
{text[:3000]}{tables_md}

Write exactly 2 multiple-choice questions on this content.
- 4 options (A-D), only one correct
- Correct answer MUST be directly stated in the text
- Wrong options must be plausible but NOT stated in the text
- Include brief explanation

Output JSON only, no markdown. Format:
{{"questions": [{{"id": "001", "question": "...", "options": [{{"id":"A","text":"..."}},{{"id":"B","text":"..."}},{{"id":"C","text":"..."}},{{"id":"D","text":"..."}}], "correct": 0, "explanation": "..."}}]}}"""

    for attempt in range(MAX_RETRIES):
        resp = call_minimax(SYSTEM_GEN, user, max_tokens=2048)

        if not resp:
            delay = BASE_DELAY * (2 ** attempt) + random.uniform(5, 15)
            print(f"\n    [retry {attempt+1}/{MAX_RETRIES}] no response, waiting {delay:.0f}s")
            time.sleep(delay)
            continue

        data = extract_json(resp)
        if data is None:
            delay = BASE_DELAY * (2 ** attempt) + random.uniform(5, 15)
            print(f"\n    [retry {attempt+1}/{MAX_RETRIES}] parse failed, waiting {delay:.0f}s")
            time.sleep(delay)
            continue

        qs = data.get("questions", [])
        if not qs:
            delay = BASE_DELAY * (2 ** attempt) + random.uniform(5, 15)
            print(f"\n    [retry {attempt+1}/{MAX_RETRIES}] empty questions, waiting {delay:.0f}s")
            time.sleep(delay)
            continue

        # Normalize and enrich
        source_text = text[:500].strip()
        for q in qs:
            q["id"] = f"{guideline}-{chapter_slug}-{next_id[0]:03d}"
            next_id[0] += 1
            q["chapter"] = chapter_slug
            q["guideline"] = guideline
            q["section"] = anchor
            q["section_title"] = title
            q["source_text"] = source_text

            # Normalize options: always {id, text}
            normalized_opts = []
            for opt in q.get("options", []):
                if isinstance(opt, str):
                    # Parse "A. Something" format
                    m = re.match(r'^([A-D])\.\s*(.*)', opt.strip())
                    if m:
                        normalized_opts.append({"id": m.group(1), "text": m.group(2)})
                    else:
                        normalized_opts.append({"id": "A", "text": str(opt)})
                elif isinstance(opt, dict):
                    normalized_opts.append({"id": opt.get("id", "A"), "text": opt.get("text", str(opt))})
            q["options"] = normalized_opts

            # Ensure correct is 0-3
            if isinstance(q.get("correct"), str):
                q["correct"] = ord(q["correct"].upper()) - ord("A")
            q["correct"] = int(q.get("correct", 0)) % 4

        return qs

    return []

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    guideline_slug = GUIDELINE
    chapters_dir = Path(f"data/chapters/{guideline_slug}")
    out_dir = Path(f"data/questions")
    out_dir.mkdir(parents=True, exist_ok=True)

    chapter_files = sorted(chapters_dir.glob("*.json"))
    skip_names = {"citation-information","conflict-of-interest","copyright-and-terms-of-use","introduction","methods","references"}
    chapter_files = [f for f in chapter_files if f.stem not in skip_names]

    print(f"Guideline: {guideline_slug}")
    print(f"Chapters: {[f.stem for f in chapter_files]}")
    print()

    next_id = [1]
    total_qs = 0

    for chapter_file in chapter_files:
        chapter_slug = chapter_file.stem
        print(f"=== {chapter_slug} ===")

        with open(chapter_file, encoding="utf-8") as f:
            chapter = json.load(f)

        sections = [s for s in chapter.get("sections", []) if len(s.get("text", "").strip()) >= 80]
        print(f"  {len(sections)} sections to process")

        out_file = out_dir / f"{guideline_slug}_{chapter_slug}.json"
        chapter_questions = []
        processed_anchors = set()

        # Resume: load existing
        if out_file.exists():
            try:
                with open(out_file, encoding="utf-8") as f:
                    saved = json.load(f)
                chapter_questions = saved.get("questions", [])
                for q in chapter_questions:
                    parts = q["id"].rsplit("-", 1)
                    if len(parts) == 2:
                        try:
                            nid = int(parts[1])
                            if nid >= next_id[0]:
                                next_id[0] = nid + 1
                        except ValueError:
                            pass
                anchors_list = saved.get("processed_anchors", [])
                processed_anchors = set(anchors_list)
                print(f"  Resuming: {len(chapter_questions)} qs already done, next_id={next_id[0]}")
            except (json.JSONDecodeError, KeyError):
                pass

        chapter_start = time.time()

        for i, section in enumerate(sections):
            anchor = section["anchor"]
            title = section["title"]

            if anchor in processed_anchors:
                print(f"  [skip {i+1}/{len(sections)}] {anchor} (done)")
                continue

            elapsed = time.time() - chapter_start
            rate = (i + 1) / (elapsed / 60) if elapsed > 10 else 0
            eta_min = (len(sections) - i - 1) / max(rate, 0.1)

            print(f"  [{i+1}/{len(sections)}] {anchor} | {title[:45]}... (ETA {eta_min:.0f}min)", end="", flush=True)

            qs = generate_for_section(section, guideline_slug, chapter_slug, next_id)

            if qs:
                chapter_questions.extend(qs)
                processed_anchors.add(anchor)
                print(f" → {len(qs)} qs (total {len(chapter_questions)})")
                result = {
                    "guideline": guideline_slug, "chapter": chapter_slug,
                    "url": chapter.get("url", ""),
                    "question_count": len(chapter_questions),
                    "questions": chapter_questions,
                    "processed_anchors": list(processed_anchors)
                }
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            else:
                print(f" → FAILED (all retries)")
                processed_anchors.add(anchor)

            # NO arbitrary sleep between sections — only retry delays are needed

        # Final save
        result = {
            "guideline": guideline_slug, "chapter": chapter_slug,
            "url": chapter.get("url", ""),
            "question_count": len(chapter_questions),
            "questions": chapter_questions,
            "processed_anchors": list(processed_anchors)
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  → Saved {len(chapter_questions)} questions to {out_file.name}")
        total_qs += len(chapter_questions)
        print()

    print(f"\n✓ COMPLETE: {total_qs} total questions for {guideline_slug}")


if __name__ == "__main__":
    main()