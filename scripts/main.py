import json
import os
from datetime import datetime, timedelta, timezone

import yaml

from fetcher import fetch_all, fetch_category_backfill
from processor import process_items

BJ_TZ = timezone(timedelta(hours=8))
SEEN_PATH = os.path.join("data", "seen.json")
SEEN_CLASSICS_PATH = os.path.join("data", "seen_classics.json")
BACKFILL_STATE_PATH = os.path.join("data", "backfill_state.json")
DOCS_DATA_DIR = os.path.join("docs", "data")
ARCHIVE_DIR = os.path.join(DOCS_DATA_DIR, "archive")


def load_json_dict(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_json_dict(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_seen(seen: dict, retention_days: int = 90) -> None:
    cutoff = (datetime.now(BJ_TZ) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    save_json_dict(SEEN_PATH, pruned)


def get_initial_backfill_cursor(config: dict, category: str, now_bj: datetime) -> str:
    """
    首次触发历史追溯时，自动计算看板当前正常搜索范围的最早日期作为起点
    （例如电池板块 lookback_days=14，则默认从 14 天前开始向前追溯）。
    """
    lookbacks = [
        int(s.get("lookback_days", 14))
        for s in config.get("openalex_streams", [])
        if s.get("category") == category
    ]
    base_days = max(lookbacks) if lookbacks else 14
    return (now_bj - timedelta(days=base_days)).strftime("%Y-%m-%d")


def main():
    with open(os.path.join("config", "sources.yaml"), "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with open(os.path.join("config", "prompt.txt"), "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    now_bj = datetime.now(BJ_TZ)
    today_str = now_bj.strftime("%Y-%m-%d")

    print(f"=== Personal Hub Daily Pipeline ({today_str}) ===")
    seen = load_json_dict(SEEN_PATH)
    seen_classics = load_json_dict(SEEN_CLASSICS_PATH)
    backfill_state = load_json_dict(BACKFILL_STATE_PATH)

    raw_items = fetch_all(config, seen_classics=set(seen_classics.keys()))
    print(f"[Pipeline] Total fetched unique items: {len(raw_items)}")

    new_classics = [
        item for item in raw_items
        if item["category"] == "classics" and item["id"] not in seen_classics
    ]
    new_battery = [
        item for item in raw_items
        if item["category"] == "battery"
        and item["id"] not in seen
        and item["id"] not in seen_classics
    ]
    new_others = [
        item for item in raw_items
        if item["category"] not in ("classics", "battery") and item["id"] not in seen
    ]

    backfill_count = 0
    # 若当天电池与储能学术板块未读新论文数为 0，自动触发 3 天步进地毯式历史追溯
    if not new_battery:
        battery_state = backfill_state.get("battery") or {}
        cursor_date = battery_state.get("cursor_date") or get_initial_backfill_cursor(
            config, "battery", now_bj
        )
        print(
            f"[Pipeline] Today's new battery papers = 0. "
            f"Triggering 3-day backfill from cursor {cursor_date}..."
        )
        all_known_ids = set(seen.keys()) | set(seen_classics.keys())
        backfill_items, next_cursor = fetch_category_backfill(
            config=config,
            target_category="battery",
            cursor_date_str=cursor_date,
            seen_ids=all_known_ids,
            step_days=3,
            max_steps=20,
            min_date_str="2018-01-01",
            max_items_per_backfill=6,
        )
        backfill_state["battery"] = {
            "cursor_date": next_cursor,
            "last_triggered_on": today_str,
            "last_found_count": len(backfill_items),
        }
        save_json_dict(BACKFILL_STATE_PATH, backfill_state)
        new_battery = backfill_items
        backfill_count = len(backfill_items)

    # 优先保留经典回溯与电池学术论文，避免被 MAX_DAILY_ITEMS 截断
    new_items = new_classics + new_battery + new_others
    print(
        f"[Pipeline] New unseen items: {len(new_items)} "
        f"(classics: {len(new_classics)}, battery: {len(new_battery)}, others: {len(new_others)})"
    )

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
        if item.get("category") == "classics":
            seen_classics[item["id"]] = today_str
        else:
            seen[item["id"]] = today_str
    save_seen(seen)
    save_json_dict(SEEN_CLASSICS_PATH, seen_classics)

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
            "fetched": len(raw_items) + backfill_count,
            "processed": len(merged_items),
            "high_value": high_value_count,
        },
        "items": merged_items,
    }

    save_json_dict(archive_file, payload)
    save_json_dict(os.path.join(DOCS_DATA_DIR, "latest.json"), payload)

    dates = sorted(
        [fn[:-5] for fn in os.listdir(ARCHIVE_DIR) if fn.endswith(".json")],
        reverse=True,
    )
    save_json_dict(os.path.join(DOCS_DATA_DIR, "index.json"), {"dates": dates, "latest": today_str})

    print(
        f"[Pipeline] Done! Saved {len(merged_items)} items "
        f"({high_value_count} high-value >= 4.0) for {today_str}."
    )


if __name__ == "__main__":
    main()
