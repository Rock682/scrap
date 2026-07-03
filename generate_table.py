"""
generate_table.py
Reads data/today_changes.json and writes a markdown table showing
only what changed this run (New / Update), with status emoji, stage,
date, and official link. This is what you check each morning/afternoon
before writing your blog post - it does NOT publish anything itself.
"""

import json
from datetime import datetime, timezone, timedelta

CHANGES_FILE = "data/today_changes.json"
OUTPUT_FILE = "data/table.md"
HISTORY_FILE = "data/run_history.json"  # log of every run, kept for your reference

IST = timezone(timedelta(hours=5, minutes=30))

STATUS_EMOJI = {
    "New": "\U0001F195",       # 🆕
    "Update": "\U0001F504",    # 🔄
}


def now_ist() -> datetime:
    # GitHub Actions runners use UTC system time - always convert explicitly
    return datetime.now(timezone.utc).astimezone(IST)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def generate_table(changes: list, run_time: datetime) -> str:
    run_label = run_time.strftime("%A, %d %B %Y — %I:%M %p IST")

    if not changes:
        return f"### Job Alert Check — {run_label}\n\nNo new updates found this run."

    # Group by category so SSC/UPSC/Railways/Defence/Banks/AP are each clear
    by_category = {}
    for job in changes:
        by_category.setdefault(job.get("category", "Other"), []).append(job)

    lines = [f"### Job Alert Changes — {run_label}", ""]

    for category in ["SSC", "UPSC", "Railways", "Defence", "Banks", "Andhra Pradesh"]:
        jobs_in_cat = by_category.get(category, [])
        if not jobs_in_cat:
            continue
        lines.append(f"#### {category}")
        lines.append("")
        lines.append("| Status | Title | Stage | Detected On | Official Link |")
        lines.append("|---|---|---|---|---|")
        for job in jobs_in_cat:
            emoji = STATUS_EMOJI.get(job["status"], "")
            detected = f"{job.get('last_updated', '')} {job.get('last_updated_time', '')}".strip()
            lines.append(
                f"| {emoji} {job['status']} | {job['title']} | {job['current_stage']} "
                f"| {detected} | [Link]({job['official_url']}) |"
            )
        lines.append("")

    return "\n".join(lines)


def update_run_history(run_time: datetime, changes: list):
    """Keep a running log of every single run - date, time, and counts -
    so you have a full audit trail of when checks happened and what they found."""
    history = load_json(HISTORY_FILE, [])
    history.append({
        "run_date": run_time.strftime("%Y-%m-%d"),
        "run_time_ist": run_time.strftime("%H:%M"),
        "run_datetime_ist": run_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "new_count": sum(1 for c in changes if c["status"] == "New"),
        "update_count": sum(1 for c in changes if c["status"] == "Update"),
    })
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    run_time = now_ist()
    changes = load_json(CHANGES_FILE, [])

    table_md = generate_table(changes, run_time)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(table_md)

    update_run_history(run_time, changes)

    print(table_md)
    print(f"\nRun logged at {run_time.strftime('%Y-%m-%d %H:%M:%S')} IST")


if __name__ == "__main__":
    main()
