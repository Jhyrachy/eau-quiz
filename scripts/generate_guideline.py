"""
generate_guideline.py
─────────────────────
Generates MCQs for all sections of a single guideline.
Loads data/chapters/{guideline}/, iterates all section anchors,
runs generate_section.py for each, merges results.

Usage:
  python scripts/generate_guideline.py prostate-cancer

Output:
  data/questions/{guideline}.json (merged all sections)
"""

import json
import sys
import time
from pathlib import Path
from generate_section import generate_section

GUIDELINE_DIR = Path("/opt/data/eau-quiz/data/chapters")
OUTPUT_DIR = Path("/opt/data/eau-quiz/data/questions")


def get_all_sections(guideline_slug: str) -> list:
    """Discover all sections for a guideline."""
    guideline_path = GUIDELINE_DIR / guideline_slug
    if not guideline_path.exists():
        print(f"Guideline directory not found: {guideline_path}")
        return []

    sections = []
    for json_file in guideline_path.glob("*.json"):
        with open(json_file) as f:
            data = json.load(f)
        for sec in data.get("sections", []):
            # Build section anchor: filename#anchor
            anchor = sec.get("anchor", "").replace("#", "")
            sections.append({
                "anchor": f"{json_file.stem}#{anchor}",
                "title": sec.get("title", ""),
                "level": sec.get("level", 0),
                "text_len": len(sec.get("text", "")),
            })
    return sections


def merge_section_results(guideline_slug: str, sections: list) -> dict:
    """
    Load all section result files and merge into single guideline JSON.
    Also handles case where some sections failed — partial merge.
    """
    all_questions = []
    total_metadata = {
        "guideline": guideline_slug,
        "sections_processed": 0,
        "sections_failed": 0,
        "total_questions": 0,
    }

    for sec in sections:
        section_file = OUTPUT_DIR / guideline_slug / f"{sec['anchor'].replace('#', '-')}.json"
        if not section_file.exists():
            print(f"  ⚠️  No result for {sec['anchor']} — skipping")
            total_metadata["sections_failed"] += 1
            continue

        with open(section_file) as f:
            data = json.load(f)

        questions = data.get("questions", [])
        all_questions.extend(questions)
        total_metadata["sections_processed"] += 1
        total_metadata["total_questions"] += len(questions)

    result = {
        "questions": all_questions,
        "metadata": total_metadata,
    }

    out_file = OUTPUT_DIR / f"{guideline_slug}.json"
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


def generate_guideline(guideline_slug: str) -> dict:
    """Generate all MCQs for one guideline."""
    print(f"\n{'='*60}")
    print(f"GUIDELINE: {guideline_slug}")
    print(f"{'='*60}")

    sections = get_all_sections(guideline_slug)
    if not sections:
        print(f"No sections found for {guideline_slug}")
        return {"questions": [], "metadata": {"error": "no sections found"}}

    print(f"Found {len(sections)} sections")

    # Filter to h3 sections only (main content sections, not sub-subsections)
    h3_sections = [s for s in sections if s.get("level") == 3]
    print(f"  → {len(h3_sections)} h3 sections to process")

    # Process each section
    for i, sec in enumerate(h3_sections):
        print(f"\n[{i+1}/{len(h3_sections)}] Processing: {sec['anchor']}")
        start = time.time()
        try:
            result = generate_section(guideline_slug, sec["anchor"])
            elapsed = time.time() - start
            print(f"  ✅ Done in {elapsed:.1f}s — {len(result.get('questions', []))} questions")
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            continue

    # Merge all sections
    print(f"\nMerging all section results...")
    merged = merge_section_results(guideline_slug, h3_sections)
    total = len(merged.get("questions", []))
    print(f"\n{'='*60}")
    print(f"GUIDELINE COMPLETE: {guideline_slug}")
    print(f"  Sections processed: {merged['metadata']['sections_processed']}")
    print(f"  Sections failed:   {merged['metadata']['sections_failed']}")
    print(f"  Total questions:  {total}")
    print(f"  Output: {OUTPUT_DIR}/{guideline_slug}.json")
    print(f"{'='*60}")

    return merged


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_guideline.py <guideline-slug>")
        print("Example: python generate_guideline.py prostate-cancer")
        sys.exit(1)

    guideline = sys.argv[1]
    result = generate_guideline(guideline)
    print(f"\nDone. {len(result.get('questions', []))} total questions saved.")