"""
scraper.py
Fetches FreeJobAlert's category listing pages directly and extracts
title + URL for each posting. Pages that map to a single category
(bank-jobs, railway-jobs, police-defence-jobs) are tagged directly.
Mixed pages (latest-notifications, admit-card) are filtered using
keyword matching against your 6 focus categories: SSC, UPSC, Railways,
Defence, Banks, Andhra Pradesh - anything else is dropped.

robots.txt for freejobalert.com explicitly allows crawling (checked
2026-07-02).

Output: raw_today.json - a flat list of {id, title, url, category}
"""

import json
import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobTrackerBot/1.0; +https://easyapplications.in/about-bot)"
}

REQUEST_DELAY_SECONDS = 3  # be polite - don't hammer the server

# Pages that map directly to ONE category - every link on these pages
# is tagged with that category, no keyword filtering needed.
DIRECT_CATEGORY_PAGES = {
    "https://www.freejobalert.com/bank-jobs/": "Banks",
    "https://www.freejobalert.com/railway-jobs/": "Railways",
    "https://www.freejobalert.com/police-defence-jobs/": "Defence",
}

# Pages with a mix of everything - each link is checked against
# CATEGORY_KEYWORDS below, and only matches to your 6 focus areas are kept.
MIXED_PAGES = [
    "https://www.freejobalert.com/latest-notifications/",
    "https://www.freejobalert.com/admit-card/",
]

CATEGORY_KEYWORDS = {
    "SSC": ["ssc", "staff-selection"],
    "UPSC": ["upsc", "civil-services", "capf", "cds", "nda"],
    "Railways": ["railway", "rrb", "rrc", "irctc", "ircon", "metro-rail"],
    "Defence": ["defence", "army", "navy", "air-force", "indian-army",
                "indian-navy", "coast-guard", "bsf", "crpf", "itbp", "cisf",
                "police", "ncc"],
    "Banks": ["bank", "ibps", "sbi", "rbi", "nabard", "sidbi", "cooperative-bank"],
    "Andhra Pradesh": ["andhra-pradesh", "ap-govt", "appsc", "ap-jobs", "-ap-"],
}


def make_stable_id(url: str) -> str:
    match = re.search(r"(\d{4,})", url)
    if match:
        return match.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")
    return slug[-80:]


def detect_category(url: str, title: str) -> str | None:
    text = f"{url} {title}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return None


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_links(html: str) -> list:
    """
    NOTE: This uses a generic heuristic (table/list links with reasonably
    long text). If results look sparse or wrong after your first run,
    inspect the actual page HTML (right-click a job link -> Inspect) and
    tell me the surrounding tag/class so I can tighten this selector.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for link in soup.select("a[href]"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or len(title) < 12:
            continue
        if not href.startswith("http"):
            continue
        if "freejobalert.com" not in href:
            continue
        items.append({"title": title, "url": href})
    return items


def main():
    all_items = []
    seen_ids = set()

    # 1. Direct-category pages - every matching link gets that category
    for url, category in DIRECT_CATEGORY_PAGES.items():
        try:
            html = fetch_page(url)
            links = extract_links(html)
            print(f"Fetched {len(links)} links from {url}")
        except requests.RequestException as e:
            print(f"Failed to fetch {url}: {e}")
            continue

        for link in links:
            item_id = make_stable_id(link["url"])
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            all_items.append({
                "id": item_id,
                "title": link["title"],
                "url": link["url"],
                "category": category,
            })
        time.sleep(REQUEST_DELAY_SECONDS)

    # 2. Mixed pages - filter by keyword to your 6 focus categories only
    for url in MIXED_PAGES:
        try:
            html = fetch_page(url)
            links = extract_links(html)
            print(f"Fetched {len(links)} links from {url}")
        except requests.RequestException as e:
            print(f"Failed to fetch {url}: {e}")
            continue

        for link in links:
            category = detect_category(link["url"], link["title"])
            if category is None:
                continue  # not one of your 6 focus categories - skip

            item_id = make_stable_id(link["url"])
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            all_items.append({
                "id": item_id,
                "title": link["title"],
                "url": link["url"],
                "category": category,
            })
        time.sleep(REQUEST_DELAY_SECONDS)

    with open("data/raw_today.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"Total matching items (focus categories only): {len(all_items)}")
    for cat in ["SSC", "UPSC", "Railways", "Defence", "Banks", "Andhra Pradesh"]:
        count = sum(1 for i in all_items if i["category"] == cat)
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
