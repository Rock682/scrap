"""
track_status.py
Compares today's scraped items (raw_today.json) against the persistent
store (data/jobs.json). Classifies each item as New, Update (stage change),
or Duplicate (skip). Uses fuzzy title matching so near-identical titles
across stages (Notification -> Admit Card -> Result) are linked to the
same job record.

Output:
  - data/jobs.json updated in place (persistent store)
  - data/today_changes.json (only what changed this run - feeds the table)
"""

import json
import os
from datetime import datetime, timedelta, timezone
from rapidfuzz import fuzz

JOBS_FILE = "data/jobs.json"
RAW_TODAY_FILE = "data/raw_today.json"
CHANGES_FILE = "data/today_changes.json"

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    # GitHub Actions runners use UTC system time - always convert explicitly
    return datetime.now(timezone.utc).astimezone(IST)

FUZZY_THRESHOLD = 85
ARCHIVE_AFTER_DAYS = 90

STAGE_KEYWORDS = {
    "Result": ["result", "declared"],
    "Admit Card": ["admit card", "hall ticket", "call letter"],
    "Answer Key": ["answer key"],
    "Notification": ["recruitment", "notification", "vacancy", "online form"],
}


def detect_stage(title: str) -> str:
    title_lower = title.lower()
    for stage, keywords in STAGE_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return stage
    return "Notification"


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_existing_job(title: str, jobs: list):
    best_score = 0
    best_job = None
    for job in jobs:
        score = fuzz.token_sort_ratio(title, job["title"])
        if score > best_score:
            best_score = score
            best_job = job
    if best_score >= FUZZY_THRESHOLD:
        return best_job
    return None


def archive_old_jobs(jobs: list) -> list:
    cutoff = now_ist().replace(tzinfo=None) - timedelta(days=ARCHIVE_AFTER_DAYS)
    active = []
    for job in jobs:
        last_updated = datetime.fromisoformat(job["last_updated"])
        if last_updated > cutoff or job.get("current_stage") != "Result":
            active.append(job)
    return active


def main():
    run_time = now_ist()
    today_str = run_time.strftime("%Y-%m-%d")
    time_str = run_time.strftime("%H:%M")
    raw_items = load_json(RAW_TODAY_FILE, [])
    jobs = load_json(JOBS_FILE, [])

    changes = []

    for item in raw_items:
        title = item["title"]
        url = item["url"]
        category = item.get("category", "Other")
        stage = detect_stage(title)

        existing = find_existing_job(title, jobs)

        if existing is None:
            new_job = {
                "id": item["id"],
                "title": title,
                "official_url": url,
                "category": category,
                "board": item.get("board", ""),
                "qualification": item.get("qualification", ""),
                "advt_no": item.get("advt_no", ""),
                "last_date": item.get("last_date", ""),
                "post_date": item.get("post_date", ""),
                "first_seen": today_str,
                "first_seen_time": time_str,
                "last_updated": today_str,
                "last_updated_time": time_str,
                "current_stage": stage,
                "stage_history": [
                    {"stage": stage, "date": today_str, "time": time_str, "url": url}
                ],
            }
            jobs.append(new_job)
            changes.append({**new_job, "status": "New"})

        else:
            already_has_stage = any(
                s["stage"] == stage for s in existing["stage_history"]
            )
            if not already_has_stage:
                existing["stage_history"].append(
                    {"stage": stage, "date": today_str, "time": time_str, "url": url}
                )
                existing["current_stage"] = stage
                existing["category"] = category
                existing["last_updated"] = today_str
                existing["last_updated_time"] = time_str
                existing["official_url"] = url
                # refresh these fields in case they were missing/updated
                existing["last_date"] = item.get("last_date", existing.get("last_date", ""))
                existing["qualification"] = item.get("qualification", existing.get("qualification", ""))
                changes.append({**existing, "status": "Update"})
            # else: duplicate, no action, not added to changes

    jobs = archive_old_jobs(jobs)

    save_json(JOBS_FILE, jobs)
    save_json(CHANGES_FILE, changes)

    print(f"New: {sum(1 for c in changes if c['status'] == 'New')}, "
          f"Updated: {sum(1 for c in changes if c['status'] == 'Update')}, "
          f"Total active jobs tracked: {len(jobs)}")


if __name__ == "__main__":
    main()
