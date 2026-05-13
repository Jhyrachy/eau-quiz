#!/usr/bin/env python3
"""
EAU Guidelines Chapter Text Scraper

Uses Playwright (Node.js) to extract real heading IDs from Vue-rendered DOM,
then parses HTML to extract sections with verified nav_anchors.

Workflow:
1. GET HTML page (urllib)
2. Launch Playwright headless browser → extract heading IDs from rendered DOM
   → These are the ONLY anchors that actually scroll in the browser
3. Parse HTML to extract sections (by h2/h3/h4 tag content)
4. Compute nav_anchor: for each section, find parent h2/h3 that exists in browser IDs
   - Use section number matching (e.g., h4 with 5.2.1 → parent h3 with 5.2)
   - Fallback: use last available h2/h3 in document order
"""
import json, re, os, sys, time, subprocess
from urllib.request import urlopen, Request

HEADERS = {"User-Agent": "Mozilla/5.0"}
NODE_SCRIPT = os.path.join(os.path.dirname(__file__), "extract_anchors.mjs")


def slug_from_heading(text):
    """
    Convert heading text to URL anchor slug, PRESERVING section number prefix.
    '5.2.1. Digital rectal examination' → '#5-2-1-digital-rectal-examination'
    '5.1. Individual early detection and screening' → '#5-1-individual-early-detection-and-screening'
    """
    text = text.strip()
    text = re.sub(r'\.\s*$', '', text)  # strip trailing period
    parts = re.split(r'\.\s+', text, maxsplit=3)
    if len(parts) >= 4:
        prefix = '-'.join(parts[:3])
        title_slug = parts[3]
    elif len(parts) == 3:
        prefix = '-'.join(parts[:2])
        title_slug = parts[2]
    elif len(parts) == 2:
        prefix = parts[0]
        title_slug = parts[1]
    else:
        prefix = ''
        title_slug = parts[0]
    title_slug = title_slug.lower()
    title_slug = re.sub(r'[^a-z0-9\s-]', '', title_slug)
    title_slug = re.sub(r'[\s]+', '-', title_slug)
    title_slug = re.sub(r'-+', '-', title_slug).strip('-')
    return f"{prefix}-{title_slug}" if prefix else title_slug


def parse_section_number(anchor):
    """
    Extract [5, 2, 1] from '#5-2-1-digital-rectal-examination' or '#5.2.1-title'.
    Supports both dashed and dotted formats.
    """
    m = re.search(r'#?(\d+)-(\d+)-(\d+)', anchor)
    if m:
        return [int(m.group(1)), int(m.group(2)), int(m.group(3))]
    m = re.search(r'#?(\d+)\.(\d+)\.(\d+)', anchor)
    if m:
        return [int(m.group(1)), int(m.group(2)), int(m.group(3))]
    m = re.search(r'#?(\d+)[.-](\d+)', anchor)
    if m:
        return [int(m.group(1)), int(m.group(2))]
    return []


def heading_section_nums(h_id):
    """
    Extract section number from browser heading ID like '5-2-diagnostic-tools'.
    Returns [5, 2] for h3, [] for h2 (no sub-level).
    """
    m = re.search(r'^(\d+)-(\d+)(?:-(\d+))?', h_id)
    if m:
        nums = [int(m.group(1)), int(m.group(2))]
        if m.group(3):
            nums.append(int(m.group(3)))
        return nums
    return []


def get_heading_ids_via_browser(url):
    """Get real heading IDs from Vue-rendered DOM via Playwright."""
    try:
        result = subprocess.run(
            ["node", NODE_SCRIPT, url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("headings", [])
    except Exception as e:
        print(f"  [browser anchor extraction failed] {e}")
    return []


def compute_nav_anchor(section_anchor, html_level, section_level, heading_ids):
    """
    Find the nearest parent h2/h3 that has a real ID in the browser DOM.

    Algorithm:
    1. Parse section number from section_anchor (e.g., [5, 2, 1] for h4)
    2. Compute target parent number (e.g., [5, 2] for h4 under 5.2)
    3. Find h2/h3 heading with matching section number
    4. Fallback: use last available h2/h3 in document order

    heading_ids: list of {id, level, tag} from browser
    """
    sec_nums = parse_section_number(section_anchor)
    if not sec_nums:
        return section_anchor

    level = len(sec_nums)  # 2=h2, 3=h3, 4=h4, 5=h5

    # Determine target parent section number using ACTUAL heading level, not derived len
    # h4 (level 4): section [5, 2, 1] → parent h3 with [5, 2]
    # h5 (level 5): section [5, 2, 4, a] → nums parsed as [5, 2, 4] → parent h4 with [5, 2, 4]
    # h3 (level 3): section [5, 1] → parent h2 with [5]
    # h2 (level 2): use self (already has a verified ID)
    if html_level == 4:
        target_parent = sec_nums[:2]   # [5, 2, 1] → [5, 2]
    elif html_level == 5:
        target_parent = sec_nums[:3] if len(sec_nums) >= 3 else sec_nums  # [5, 2, 4] → [5, 2, 4]
    elif html_level == 3:
        target_parent = sec_nums[:1]   # [5, 1] → [5]
    else:
        return section_anchor

    # Build id → section number map from browser heading IDs
    valid_ids = {h["id"]: heading_section_nums(h["id"]) for h in heading_ids}

    # Find heading whose nums are a PREFIX of sec_nums (closest parent in hierarchy)
    # e.g. h4 [5,2,1] → h3 [5,2] is a prefix → match
    # e.g. h3 [5,1] → h2 [5] is a prefix → match
    best = None
    best_len = 0
    for h_id, nums in valid_ids.items():
        if len(nums) > best_len and sec_nums[:len(nums)] == nums:
            best = h_id
            best_len = len(nums)

    if best:
        return f"#{best}"

    # Fallback: last available h2/h3
    h23 = [h for h in heading_ids if h["level"] in (2, 3)]
    if h23:
        return f"#{h23[-1]['id']}"

    return section_anchor


def parse_chapter_sections(html, heading_ids):
    """
    Split HTML by h2/h3/h4 tags (no id attr in static HTML).
    For each heading:
      - Compute section anchor from text pattern
      - nav_anchor = nearest parent h2/h3 with verified browser ID
    """
    tables_pattern = re.compile(r'<table[^>]*>.*?</table>', re.DOTALL)

    def strip_tags(text):
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def extract_tables(block_html):
        tables = []
        for t in tables_pattern.findall(block_html):
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.DOTALL)
            table_data = []
            for row in rows:
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
                cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                if any(cells):
                    table_data.append(cells)
            if table_data:
                tables.append(table_data)
        return tables

    sections = []
    # Split on ALL heading levels present in the HTML (h2..h5)
    # h5 sub-subsections are substantive and should be their own sections
    heading_pattern = re.compile(r'<h([2345])[^>]*>(.*?)</h\1>', re.DOTALL)

    prev_end = 0
    for m in heading_pattern.finditer(html):
        level = int(m.group(1))
        raw_text = m.group(2)
        h_text = re.sub(r'<[^>]+>', '', raw_text).strip()

        if len(h_text) < 5:
            prev_end = m.end()
            continue

        slug = slug_from_heading(h_text)
        section_anchor = f"#{slug}"
        nav_anchor = compute_nav_anchor(section_anchor, level, level, heading_ids)

        block_html = html[prev_end:m.start()]
        prev_end = m.end()

        section_text = strip_tags(block_html)
        tables = extract_tables(block_html)

        sections.append({
            "anchor": section_anchor,
            "nav_anchor": nav_anchor,
            "title": h_text,
            "text": section_text,
            "tables": tables,
            "level": level
        })

    return sections


def scrape_chapter(slug, chapter_slug, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{chapter_slug}.json")

    url = f"https://uroweb.org/guidelines/{slug}/chapter/{chapter_slug}"
    print(f"  Scraping: {url}")

    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")

    # Get verified heading IDs from browser
    print("  Getting heading IDs via headless browser...")
    heading_ids = get_heading_ids_via_browser(url)
    print(f"  → {len(heading_ids)} verified headings:")
    for h in heading_ids:
        print(f"      h{h['level']} id='{h['id']}' → {h['text'][:50]}")

    # Metadata
    title_m = re.search(r'<title>(.*?)\|', html)
    page_title = title_m.group(1).strip() if title_m else chapter_slug
    guideline_m = re.search(r'class="guidelines-title">(.*?)</', html)
    guideline_title = re.sub(r'<[^>]+>', '', guideline_m.group(1)).strip() if guideline_m else slug
    year_m = re.search(r'(\d{4})\s*Guideline', html)
    year = year_m.group(1) if year_m else "2024"

    # Parse sections
    sections = parse_chapter_sections(html, heading_ids)
    tables_count = len(re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL))

    chapter_data = {
        "url": url,
        "slug": slug,
        "chapter_slug": chapter_slug,
        "title": page_title,
        "guideline": guideline_title,
        "year": year,
        "sections": sections,
        "heading_ids": heading_ids,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chapter_data, f, ensure_ascii=False, indent=2)

    print(f"  → {len(sections)} sections, {tables_count} tables")
    return out_path


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else "prostate-cancer"
    chapter_slug = sys.argv[2] if len(sys.argv) > 2 else "diagnostic-evaluation"
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "data/chapters"
    output_dir = os.path.join(output_dir, slug)

    out = scrape_chapter(slug, chapter_slug, output_dir)
    print(f"Saved: {out}")