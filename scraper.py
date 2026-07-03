"""
scraper.py
Fetches FreeJobAlert's sitemap(s), extracts URL + last-modified date for
each entry, and keeps ONLY items matching your focus categories:
SSC, UPSC, Railways, Defence, Banks, Andhra Pradesh.

robots.txt for freejobalert.com explicitly allows crawling (checked
2026-07-02) and publishes these sitemaps directly, so we read structured
data from there instead of scraping raw HTML - more stable and lighter
on their server.

Output: raw_today.json - a flat list of {id, title, url, category, lastmod}
"""

import json
import re
import time
import requests
from xml.etree import ElementTree

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobTrackerBot/1.0; +https://easyapplications.in/about-bot)"
}

SITEMAPS = [
    "https://www.freejobalert.com/sitemap-general.xml",
    "https://www.freejobalert.com/google-news-sitemap.xml",
]

REQUEST_DELAY_SECONDS = 2

# Only these categories are tracked - everything else is ignored.
# Keywords are matched against the URL slug and title (case-insensitive).
CATEGORY_KEYWORDS = {
    "SSC": ["ssc", "staff-selection"],
    "UPSC": ["upsc", "civil-services", "capf", "cds", "nda"],
    "Railways": ["railway", "rrb", "rrc", "irctc", "ircon", "metro-rail"],
    "Defence": ["defence", "army", "navy", "air-force", "indian-army",
                "indian-navy", "coast-guard", "bsf", "crpf", "itbp", "cisf"],
    "Banks": ["bank", "ibps", "sbi", "rbi", "nabard", "sidbi", "cooperative-bank"],
    "Andhra Pradesh": ["andhra-pradesh", "ap-govt", "appsc", "ap-jobs", "-ap-"],
}


def make_stable_id(url: str) -> str:
    match = re.search(r"(\d{4,})", url)
    if match:
        return match.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")
    return slug[-80:]


def detect_category(url: str, title: str = "") -> str | None:
    text = f"{url} {title}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return None


def title_from_slug(url: str) -> str:
    """Sitemaps often don't include a title, so derive a readable one
    from the URL slug as a fallback."""
    slug = url.rstrip("/").split("/")[-1]
    slug = slug.replace("-", " ").strip()
    return slug.title()


def fetch_sitemap(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_sitemap(xml_text: str) -> list:
    """
    Handles standard <urlset> sitemaps and Google News sitemaps
    (which include <news:title> - much better than guessing from slug).
    """
    ns = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "news": "http://www.google.com/schemas/sitemap-news/0.9",
    }
    root = ElementTree.fromstring(xml_text)
    entries = []

    for url_el in root.findall("sm:url", ns):
        loc_el = url_el.find("sm:loc", ns)
        if loc_el is None or not loc_el.text:
            continue
        loc = loc_el.text.strip()

        lastmod_el = url_el.find("sm:lastmod", ns)
        lastmod = lastmod_el.text.strip() if lastmod_el is not None else ""

        news_el = url_el.find("news:news", ns)
        title = ""
        if news_el is not None:
            title_el = news_el.find("news:title", ns)
            if title_el is not None and title_el.text:
                title = title_el.text.strip()
        if not title:
            title = title_from_slug(loc)

        entries.append({"url": loc, "title": title, "lastmod": lastmod})

    return entries


def main():
    all_items = []
    seen_ids = set()

    for sitemap_url in SITEMAPS:
        try:
            xml_text = fetch_sitemap(sitemap_url)
            entries = parse_sitemap(xml_text)
            print(f"Parsed {len(entries)} entries from {sitemap_url}")
        except (requests.RequestException, ElementTree.ParseError) as e:
            print(f"Failed to fetch/parse {sitemap_url}: {e}")
            continue

        for entry in entries:
            category = detect_category(entry["url"], entry["title"])
            if category is None:
                continue  # not one of your 6 focus categories - skip

            item_id = make_stable_id(entry["url"])
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            all_items.append({
                "id": item_id,
                "title": entry["title"],
                "url": entry["url"],
                "category": category,
                "lastmod": entry["lastmod"],
            })

        time.sleep(REQUEST_DELAY_SECONDS)

    with open("data/raw_today.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"Total matching items (focus categories only): {len(all_items)}")
    for cat in CATEGORY_KEYWORDS:
        count = sum(1 for i in all_items if i["category"] == cat)
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
