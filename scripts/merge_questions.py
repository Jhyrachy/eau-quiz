#!/usr/bin/env python3
"""
Merge per-chapter question JSON files into per-guideline JSON files.
Run after generate_quiz_json.py to consolidate chapter outputs for the UI.

Usage:
    python scripts/merge_questions.py [--all | <guideline_slug>]
"""
import json, sys, re
from pathlib import Path

QUESTIONS_DIR = Path("data/questions")

def merge_guideline(slug: str) -> dict | None:
    """Merge all chapter files for a guideline into one JSON."""
    chapter_files = sorted(QUESTIONS_DIR.glob(f"{slug}_*.json"))
    if not chapter_files:
        return None

    all_questions = []
    for f in chapter_files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        all_questions.extend(data.get("questions", []))

    # Deduplicate by question id
    seen = set()
    unique = []
    for q in all_questions:
        if q["id"] not in seen:
            seen.add(q["id"])
            unique.append(q)

    # Re-number IDs to be sequential within the merged file
    for i, q in enumerate(unique, 1):
        q["id"] = f"{slug}-{i:05d}"

    merged = {
        "guideline": slug,
        "question_count": len(unique),
        "questions": unique
    }

    out_path = QUESTIONS_DIR / f"{slug}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    return merged


def main():
    if len(sys.argv) < 2:
        print("Usage: python merge_questions.py [--all | <guideline_slug>]")
        sys.exit(1)

    if sys.argv[1] == "--all":
        # Find all unique guideline slugs from chapter files
        chapter_files = list(QUESTIONS_DIR.glob("*_*.json"))
        slugs = sorted(set(re.match(r"([^_]+)_.+", f.name).group(1) for f in chapter_files))
    else:
        slugs = [sys.argv[1]]

    total = 0
    for slug in slugs:
        result = merge_guideline(slug)
        if result:
            print(f"  {slug}: {result['question_count']} questions → {slug}.json")
            total += result["question_count"]
        else:
            print(f"  {slug}: no chapter files found, skipped")
    print(f"\nTotal: {total} questions merged")


if __name__ == "__main__":
    main()
