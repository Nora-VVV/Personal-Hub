import json
import os
from datetime import datetime, timedelta, timezone

import yaml

from fetcher import fetch_all
from processor import process_items

BJ_TZ = timezone(timedelta(hours=8))
SEEN_PATH = os.path.join("data", "seen.json")
DOCS_DATA_DIR = os.path.join("docs", "data")
ARCHIVE_DIR = os.path.join(DOCS_DATA_DIR, "archive")


def load_seen() -> dict:
    if os.path.exists(SEEN_PATH):
        try:
            with open(SEEN_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_seen(seen: dict, retention_days: int = 60) -> None:
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    cutoff = (datetime.now(BJ_TZ) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)


def main():
    with open(os.path.join("config", "sources.yaml"), "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with open(os.path.join("config", "prompt.txt"), "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    now_bj = datetime.now(BJ_TZ)
    today_str = now_bj.strftime("%Y-%m-%d")

    print(f"=== Personal Hub Daily Pipeline ({today_str}) ===")
    raw_items = fetch_all(config)
    print(f"[Pipeline] Total fetched unique items: {len(raw_items)}")

    seen = load_seen()
    new_items = [item for item in raw_items if item["id"] not in seen]
    print(f"[Pipeline] New unseen items: {len(new_items)}")

    max_daily = int(os.environ.get("MAX_DAILY_ITEMS", "35"))
    if len(new_items) > max_daily:
        print(f"[Pipeline] Capping items to MAX_DAILY_ITEMS={max_daily} for cost control.")
        new_items = new_items[:max_daily]

    if not new_items:
        print("[Pipeline] No new items today. Skipping AI processing and keeping existing latest.json.")
        return

    processed = process_items(new_items, system_prompt, max_workers=4)
    if not processed:
        print("[Pipeline] Warning: AI processing returned 0 items.")
        raise SystemExit(1)

    for item in processed:
        seen[item["id"]] = today_str
    save_seen(seen)

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_file = os.path.join(ARCHIVE_DIR, f"{today_str}.json")

    existing_items = []
    if os.path.exists(archive_file):
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                existing_items = existing_data.get("items", [])
        except Exception:
            existing_items = []

    merged_map = {item["id"]: item for item in existing_items}
    for item in processed:
        merged_map[item["id"]] = item
    merged_items = sorted(
        merged_map.values(),
        key=lambda x: (x.get("score", 0), x.get("published_at", "")),
        reverse=True,
    )

    high_value_count = sum(1 for x in merged_items if x.get("score", 0) >= 4.0)
    payload = {
        "date": today_str,
        "generated_at": now_bj.isoformat(timespec="seconds"),
        "categories": config.get("categories", []),
        "stats": {
            "fetched": len(raw_items),
            "processed": len(merged_items),
            "high_value": high_value_count,
        },
        "items": merged_items,
    }

    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DOCS_DATA_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    dates = sorted(
        [fn[:-5] for fn in os.listdir(ARCHIVE_DIR) if fn.endswith(".json")],
        reverse=True,
    )
    with open(os.path.join(DOCS_DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"dates": dates, "latest": today_str}, f, ensure_ascii=False, indent=2)

    print(
        f"[Pipeline] Done! Saved {len(merged_items)} items "
        f"({high_value_count} high-value >= 4.0) for {today_str}."
    )


if __name__ == "__main__":
    main()
