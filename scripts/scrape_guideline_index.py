#!/usr/bin/env python3
"""
scrape_guideline_index.py

Scrape uroweb.org/guidelines to get all guideline slugs, names, years, and chapters.
Saves to data/guidelines.json

Usage:
    python scripts/scrape_guideline_index.py

Output:
    data/guidelines.json — registry of all EAU guidelines with chapters
"""

import re, json, html as html_module, urllib.request, urllib.error
from pathlib import Path

BASE_URL = "https://uroweb.org/guidelines"
OUTPUT_FILE = Path("data/guidelines.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EAU-Quiz-Bot/1.0; +https://github.com/jhyrachy/eau-quiz)"
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def extract_nuxt_data(html: str) -> list:
    """Extract all entries from __NUXT_DATA__ <script> tag."""
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    raw = m.group(1)
    # Just return raw text for inspection
    return [raw]


def extract_chapters(html: str, guideline_slug: str) -> list:
    """Extract chapter list from a guideline index page.

    The page has a sidebar nav with links like:
    /guidelines/<slug>/chapter/<chapter-slug>

    We extract the nav items from the HTML.
    """
    chapters = []

    # Pattern 1: sidebar nav links
    nav_pattern = re.compile(
        r'href="(/guidelines/' + re.escape(guideline_slug) + r'/chapter/([^"]+))"[^>]*>([^<]+)<'
    )
    seen = set()
    for m in nav_pattern.finditer(html):
        href, chapter_slug, title = m.group(1), m.group(2), m.group(3)
        if chapter_slug in seen:
            continue
        seen.add(chapter_slug)
        clean_title = html_module.unescape(title.strip())
        chapters.append({
            "slug": chapter_slug,
            "title": clean_title,
            "url": f"https://uroweb.org{href}"
        })

    # Pattern 2: if no nav found, try __NUXT_DATA__ for chapter links
    if not chapters:
        nuxt = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nuxt:
            data = nuxt.group(1)
            link_pattern = re.compile(r'/guidelines/' + re.escape(guideline_slug) + r'/chapter/([^"\\]+)')
            for m in link_pattern.finditer(data):
                cs = m.group(1)
                if cs in seen:
                    continue
                seen.add(cs)
                chapters.append({
                    "slug": cs,
                    "title": cs.replace("-", " ").title(),
                    "url": f"https://uroweb.org/guidelines/{guideline_slug}/chapter/{cs}"
                })

    return chapters


def extract_title_and_year(html: str) -> tuple:
    """Get guideline name and year from the page."""
    # Try <title> tag
    m = re.search(r'<title>([^<]+)</title>', html)
    title = None
    if m:
        raw = html_module.unescape(m.group(1))
        # Format: "Prostate Cancer | EAU Guidelines"
        title = re.sub(r'\s*\|\s*EAU.*', '', raw).strip()

    # Try meta description for year
    m = re.search(r'"datePublished"\s*:\s*"(\d{4})"', html)
    year = int(m.group(1)) if m else 2026

    return title, year


def build_slug_map() -> dict:
    """Fetch main guidelines page, extract all guideline slugs."""
    print(f"Fetching {BASE_URL}...")
    html = fetch(BASE_URL)

    # All guideline slugs are listed in the page
    slugs = re.findall(r'/guidelines/([a-z0-9-]+)/chapter/', html)
    slugs = sorted(set(slugs))
    print(f"Found {len(slugs)} guideline slugs: {slugs}")
    return slugs


def main():
    Path("data").mkdir(exist_ok=True)

    slugs = build_slug_map()
    guidelines = []

    for slug in slugs:
        print(f"\nProcessing: {slug}")
        url = f"https://uroweb.org/guidelines/{slug}"
        try:
            html = fetch(url)
        except urllib.error.HTTPError as e:
            print(f"  ✗ HTTP {e.code} for {url}")
            continue

        name, year = extract_title_and_year(html)
        chapters = extract_chapters(html, slug)

        entry = {
            "slug": slug,
            "name": name or slug.replace("-", " ").title(),
            "year": year,
            "url": url,
            "chapters": chapters
        }
        guidelines.append(entry)
        print(f"  ✓ {entry['name']} ({year}) — {len(chapters)} chapters")

        # Be polite
        import time; time.sleep(1)

    # Sort by name
    guidelines.sort(key=lambda g: g["name"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(guidelines, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(guidelines)} guidelines → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()