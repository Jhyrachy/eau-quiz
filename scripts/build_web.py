#!/usr/bin/env python3
"""
Build script: prepares web/ directory for GitHub Pages deployment.
- Copies guidelines.json and index.json to web/data/
- Symlinks or copies question JSON files to web/data/questions/
- Overwrites existing web/data/ with fresh symlinks

Usage:
    python scripts/build_web.py
"""
import json, shutil, os
from pathlib import Path

WEB_DATA = Path("web/data")
QUESTIONS_SRC = Path("data/questions")
QUESTIONS_DEST = WEB_DATA / "questions"

def build():
    # Copy static files (handle symlink case: skip if src==dst via symlink)
    static = {
        "data/guidelines.json": WEB_DATA / "guidelines.json",
        "data/index.json": WEB_DATA / "index.json",
    }
    for src, dst in static.items():
        try:
            shutil.copy2(src, dst)
            print(f"  copied {src} → {dst}")
        except shutil.SameFileError:
            print(f"  skipped (symlink): {dst}")

    # Copy question files
    if QUESTIONS_SRC.exists():
        QUESTIONS_DEST.mkdir(parents=True, exist_ok=True)
        for f in QUESTIONS_SRC.glob("*.json"):
            shutil.copy2(f, QUESTIONS_DEST / f.name)
            print(f"  copied questions/{f.name}")

    # Copy chapters (for potential future use)
    CHAPTERS_DEST = WEB_DATA / "chapters"
    CHAPTERS_SRC = Path("data/chapters")
    if CHAPTERS_SRC.exists():
        # Copy chapter index only (not all chapter JSON — too large)
        pass

    print(f"\n✓ Build complete → web/data/")

    # Print total question count
    total = 0
    for f in sorted(QUESTIONS_DEST.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            n = len(data.get("questions", []))
            print(f"  {f.name}: {n} questions")
            total += n
        except Exception:
            pass
    print(f"\n  Total: {total} questions across all guidelines")

if __name__ == "__main__":
    build()
