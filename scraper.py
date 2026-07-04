"""
scraper.py
Fetches FreeJobAlert's category listing pages and parses the actual data
TABLES on each page (columns: Post Date, Recruitment Board, Post Name,
Qualification, Advt No, Last Date, More Information/Get Details link).
This targets real job rows only - no menu links, no junk.

Pages that map to a single category (bank-jobs, railway-jobs,
police-defence-jobs) are tagged directly. Mixed pages (latest-notifications,
admit-card) are filtered using keyword matching against your 6 focus
categories: SSC, UPSC, Railways, Defence, Banks, Andhra Pradesh.

robots.txt for freejobalert.com explicitly allows crawling (checked
2026-07-02).

Output: raw_today.json - a flat list of:
  {id, title, url, category, post_date, qualification, advt_no, last_date}
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

DIRECT_CATEGORY_PAGES = {
    "https://www.freejobalert.com/bank-jobs/": "Banks",
    "https://www.freejobalert.com/railway-jobs/": "Railways",
    "https://www.freejobalert.com/police-defence-jobs/": "Defence",
}

MIXED_PAGES = [
    "https://www.freejobalert.com/latest-notifications/",
    "https://www.freejobalert.com/admit-card/",
]

CATEGORY_KEYWORDS = {
    "SSC": ["ssc", "staff-selection", "staff selection"],
    "UPSC": ["upsc", "civil-services", "civil services", "capf", "cds", "nda"],
    "Railways": ["railway", "rrb", "rrc", "irctc", "ircon", "metro rail"],
    "Defence": ["defence", "army", "navy", "air force", "coast guard",
                "bsf", "crpf", "itbp", "cisf", "police"],
    "Banks": ["bank", "ibps", "sbi", "rbi", "nabard", "sidbi"],
    "Andhra Pradesh": ["andhra pradesh", "ap govt", "appsc"],
}

# Recognized column headers -> normalized field name.
# FreeJobAlert varies "Bank Name" / "Recruitment Board" / "Organization"
# across pages, so map several variants to the same field.
HEADER_MAP = {
    "post date": "post_date",
    "bank name": "board",
    "recruitment board": "board",
    "organization": "board",
    "post name": "title",
    "exam / post name": "title",
    "exam/post name": "title",
    "qualification": "qualification",
    "advt no": "advt_no",
    "last date": "last_date",
    "more information": "link",
}


def make_stable_id(url: str) -> str:
    match = re.search(r"(\d{4,})", url)
    if match:
        return match.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")
    return slug[-80:]


def detect_category(text: str) -> str | None:
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return None


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_tables(html: str) -> list:
    """
    Finds every <table> on the page, reads its header row to figure out
    column order, then extracts each data row as a dict using HEADER_MAP.
    Rows are skipped if no usable link or title is found.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows_out = []

    for table in soup.find_all("table"):
        header_cells = table.find("tr")
        if header_cells is None:
            continue
        headers = [th.get_text(strip=True).lower() for th in header_cells.find_all(["th", "td"])]
        field_order = [HEADER_MAP.get(h) for h in headers]

        if "title" not in field_order and "link" not in field_order:
            continue  # not a job table, skip (e.g. a layout table)

        body_rows = table.find_all("tr")[1:]  # skip header row
        for row in body_rows:
            cells = row.find_all("td")
            if len(cells) != len(field_order):
                continue

            record = {}
            link_href = None
            for field, cell in zip(field_order, cells):
                if field is None:
                    continue
                text = cell.get_text(strip=True)
                record[field] = text
                a_tag = cell.find("a", href=True)
                if a_tag and field == "link":
                    link_href = a_tag["href"]

            if not link_href or "title" not in record or not record["title"]:
                continue

            record["url"] = link_href
            rows_out.append(record)

    return rows_out


def build_item(record: dict, category: str) -> dict:
    return {
        "id": make_stable_id(record["url"]),
        "title": record.get("title", "").strip(),
        "url": record["url"],
        "category": category,
        "post_date": record.get("post_date", ""),
        "board": record.get("board", ""),
        "qualification": record.get("qualification", ""),
        "advt_no": record.get("advt_no", ""),
        "last_date": record.get("last_date", ""),
    }


def main():
    all_items = []
    seen_ids = set()

    # 1. Direct-category pages
    for url, category in DIRECT_CATEGORY_PAGES.items():
        try:
            html = fetch_page(url)
            records = parse_tables(html)
            print(f"Parsed {len(records)} table rows from {url}")
        except requests.RequestException as e:
            print(f"Failed to fetch {url}: {e}")
            continue

        for record in records:
            item = build_item(record, category)
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            all_items.append(item)
        time.sleep(REQUEST_DELAY_SECONDS)

    # 2. Mixed pages - keyword-filter to your 6 focus categories only
    for url in MIXED_PAGES:
        try:
            html = fetch_page(url)
            records = parse_tables(html)
            print(f"Parsed {len(records)} table rows from {url}")
        except requests.RequestException as e:
            print(f"Failed to fetch {url}: {e}")
            continue

        for record in records:
            search_text = f"{record.get('title','')} {record.get('board','')} {record['url']}"
            category = detect_category(search_text)
            if category is None:
                continue

            item = build_item(record, category)
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            all_items.append(item)
        time.sleep(REQUEST_DELAY_SECONDS)

    with open("data/raw_today.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"Total matching items (focus categories only): {len(all_items)}")
    for cat in ["SSC", "UPSC", "Railways", "Defence", "Banks", "Andhra Pradesh"]:
        count = sum(1 for i in all_items if i["category"] == cat)
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
