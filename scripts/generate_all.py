"""
generate_all.py
───────────────
Master script: generates MCQs for all EAU guidelines.
Loads data/chapters/ directory, iterates all guideline folders,
runs generate_guideline.py for each.

Usage:
  python scripts/generate_all.py

Or for specific guidelines:
  python scripts/generate_all.py prostate-cancer non-muscle-invasive-bladder-cancer
"""

import json
import sys
import time
from pathlib import Path
from generate_guideline import generate_guideline

CHAPTERS_DIR = Path("/opt/data/eau-quiz/data/chapters")
OUTPUT_DIR = Path("/opt/data/eau-quiz/data/questions")


def get_all_guidelines() -> list:
    """Discover all available guidelines in data/chapters/."""
    if not CHAPTERS_DIR.exists():
        print(f"Chapters directory not found: {CHAPTERS_DIR}")
        return []

    guidelines = []
    for d in CHAPTERS_DIR.iterdir():
        if d.is_dir():
            guidelines.append(d.name)
    return sorted(guidelines)


if __name__ == "__main__":
    # Determine which guidelines to process
    if len(sys.argv) > 1:
        guidelines = sys.argv[1:]
        print(f"Processing {len(guidelines)} specified guideline(s): {guidelines}")
    else:
        guidelines = get_all_guidelines()
        print(f"Found {len(guidelines)} guidelines to process")

    if not guidelines:
        print("No guidelines found. Exiting.")
        sys.exit(0)

    results = {}
    total_questions = 0

    for i, guideline in enumerate(guidelines):
        print(f"\n{'#'*70}")
        print(f"# [{i+1}/{len(guidelines)}] {guideline}")
        print(f"{'#'*70}")
        start = time.time()
        try:
            result = generate_guideline(guideline)
            n = len(result.get("questions", []))
            results[guideline] = n
            total_questions += n
            elapsed = time.time() - start
            print(f"✅ {guideline}: {n} questions in {elapsed:.1f}s")
        except Exception as e:
            print(f"❌ {guideline}: FAILED — {e}")
            results[guideline] = 0
            continue

    # Summary
    print(f"\n{'='*70}")
    print(f"ALL GUIDELINES COMPLETE")
    print(f"{'='*70}")
    for g, n in results.items():
        print(f"  {g}: {n} questions")
    print(f"  ─────────────────────")
    print(f"  TOTAL: {total_questions} questions across {len(results)} guidelines")
    print(f"{'='*70}")