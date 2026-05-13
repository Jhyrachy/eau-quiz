"""
Minimal headless browser check using urllib to confirm the anchor URL
actually returns a page that has the target text near the top.
This doesn't need JS execution — just HTTP GET.
"""
import urllib.request, re, json

url = "https://uroweb.org/guidelines/prostate-cancer/chapter/diagnostic-evaluation#5-2-diagnostic-tools"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as r:
    html = r.read().decode()

# The browser loads the page and scrolls to the anchor server-side
# Check if the anchor text appears early in the page (top 50KB = near top after scroll)
pos = html.find("5.2.1. Digital rectal examination")
print(f"Position of '5.2.1. Digital rectal examination': {pos}")
print(f"In top 5KB? {pos > 0 and pos < 5000}")
print(f"In top 50KB? {pos > 0 and pos < 50000}")

# Check what the server returns for the anchor URL
# Does the server render the page with the anchor pre-scrolled?
# Or does it just serve the same HTML and browser handles the anchor?

# Let's check: does the HTML contain any indication it pre-scrolled?
# Look for the h4 at the beginning vs end of HTML
first_occurrence = html.find("5.2.1. Digital rectal examination")
last_occurrence = html.rfind("5.2.1. Digital rectal examination")
print(f"\nFirst occurrence at: {first_occurrence}")
print(f"Last occurrence at: {last_occurrence}")
print(f"Total page size: {len(html)}")

# Check if server does anchor-based server-side rendering
print(f"\nServer appears to: {'pre-render anchor' if first_occurrence < 5000 else 'serve full page (JS scroll)'}")
