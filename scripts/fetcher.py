import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import feedparser
import httpx

USER_AGENT = "PersonalHub/1.0 (+https://github.com; mailto:personal-hub@example.com)"
SOURCES_CACHE_PATH = os.path.join("data", "openalex_sources_cache.json")


def clean_html(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_item_id(url: str, title: str) -> str:
    key = (url or title).strip().lower()
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    if not inverted_index:
        return ""
    words = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words.keys()))


def load_source_cache() -> Dict[str, str]:
    if os.path.exists(SOURCES_CACHE_PATH):
        try:
            with open(SOURCES_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_source_cache(cache: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(SOURCES_CACHE_PATH), exist_ok=True)
    with open(SOURCES_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def resolve_openalex_source_ids(journals: List[str], client: httpx.Client) -> Dict[str, str]:
    cache = load_source_cache()
    updated = False
    resolved = {}

    for journal in journals:
        if journal in cache and cache[journal]:
            resolved[journal] = cache[journal]
            continue

        try:
            resp = client.get(
                "https://api.openalex.org/sources",
                params={"search": journal, "per-page": 5},
                timeout=15.0,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            chosen_id = None
            for r in results:
                if (r.get("display_name") or "").strip().lower() == journal.strip().lower():
                    chosen_id = r["id"].split("/")[-1]
                    break
            if not chosen_id and results:
                chosen_id = results[0]["id"].split("/")[-1]

            if chosen_id:
                cache[journal] = chosen_id
                resolved[journal] = chosen_id
                updated = True
                print(f"[OpenAlex] Resolved journal '{journal}' -> {chosen_id}")
            else:
                print(f"[OpenAlex] Warning: Could not resolve journal '{journal}'")
        except Exception as e:
            print(f"[OpenAlex] Failed to resolve '{journal}': {e}")

    if updated:
        save_source_cache(cache)

    return resolved


def match_any_keyword(text_lower: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    for kw in keywords:
        kw_l = kw.strip().lower()
        if not kw_l:
            continue
        if len(kw_l) <= 4 and kw_l.isalpha():
            if re.search(rf"\b{re.escape(kw_l)}\b", text_lower):
                return True
        else:
            if kw_l in text_lower:
                return True
    return False


def fetch_openalex_streams(streams: List[dict], client: httpx.Client) -> List[dict]:
    items = []
    for stream in streams:
        name = stream.get("name", "OpenAlex")
        category = stream.get("category", "battery")
        journals = stream.get("journals", [])
        lookback_days = int(stream.get("lookback_days", 14))
        max_items = int(stream.get("max_items", 10))
        search_query = stream.get("search_query", "")
        must_a = stream.get("must_match_a", [])
        must_b = stream.get("must_match_b", [])

        source_map = resolve_openalex_source_ids(journals, client)
        source_ids = list(set(source_map.values()))
        if not source_ids:
            print(f"[OpenAlex] Skipping '{name}': no valid journal IDs.")
            continue

        since_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        filter_str = (
            f"primary_location.source.id:{'|'.join(source_ids)},"
            f"from_publication_date:{since_date},"
            f"has_abstract:true"
        )

        params = {
            "filter": filter_str,
            "sort": "publication_date:desc",
            "per-page": 60,
        }
        if search_query:
            params["search"] = search_query

        try:
            resp = client.get("https://api.openalex.org/works", params=params, timeout=25.0)
            resp.raise_for_status()
            works = resp.json().get("results", [])
        except Exception as e:
            print(f"[OpenAlex] Error fetching '{name}': {e}")
            continue

        count = 0
        for w in works:
            if count >= max_items:
                break
            title = (w.get("title") or "").strip()
            if not title:
                continue
            abstract = reconstruct_abstract(w.get("abstract_inverted_index"))
            combined = f"{title} {abstract}".lower()

            if not (match_any_keyword(combined, must_a) and match_any_keyword(combined, must_b)):
                continue

            primary_loc = w.get("primary_location") or {}
            source_info = primary_loc.get("source") or {}
            journal_name = source_info.get("display_name") or name
            doi = w.get("doi") or ""
            landing_url = primary_loc.get("landing_page_url") or doi or w.get("id") or ""
            pub_date = w.get("publication_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

            items.append(
                {
                    "id": make_item_id(landing_url, title),
                    "title_orig": title,
                    "summary_orig": abstract[:3500],
                    "source": journal_name,
                    "category": category,
                    "url": landing_url,
                    "published_at": pub_date,
                }
            )
            count += 1

        print(f"[OpenAlex] '{name}': matched {count} papers (from {len(works)} candidates)")

    return items


def fetch_hf_daily_papers(cfg: dict, client: httpx.Client) -> List[dict]:
    if not cfg or not cfg.get("enabled", False):
        return []
    category = cfg.get("category", "ai")
    max_items = int(cfg.get("max_items", 6))
    items = []

    try:
        resp = client.get("https://huggingface.co/api/daily_papers", timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
        data.sort(key=lambda x: (x.get("paper") or {}).get("upvotes", 0), reverse=True)
        for entry in data[:max_items]:
            paper = entry.get("paper") or {}
            paper_id = paper.get("id") or ""
            title = (paper.get("title") or entry.get("title") or "").strip()
            summary = (paper.get("summary") or entry.get("summary") or "").strip()
            if not title:
                continue
            url = f"https://huggingface.co/papers/{paper_id}" if paper_id else "https://huggingface.co/papers"
            pub_raw = paper.get("publishedAt") or entry.get("publishedAt") or ""
            pub_date = pub_raw[:10] if len(pub_raw) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            upvotes = paper.get("upvotes", 0)
            items.append(
                {
                    "id": make_item_id(url, title),
                    "title_orig": title,
                    "summary_orig": f"[HF Upvotes: {upvotes}] {summary}"[:3500],
                    "source": "Hugging Face Daily Papers",
                    "category": category,
                    "url": url,
                    "published_at": pub_date,
                }
            )
        print(f"[HF Daily Papers] Fetched {len(items)} papers")
    except Exception as e:
        print(f"[HF Daily Papers] Error: {e}")

    return items


def parse_feed_date(entry) -> str:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return f"{parsed.tm_year:04d}-{parsed.tm_mon:02d}-{parsed.tm_mday:02d}"
            except Exception:
                pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_rss_sources(rss_sources: List[dict], client: httpx.Client) -> List[dict]:
    items = []
    for src in rss_sources:
        name = src.get("name", "RSS")
        url = src.get("url", "")
        category = src.get("category", "ai")
        max_items = int(src.get("max_items", 5))
        keywords = src.get("keywords", [])

        if not url:
            continue

        try:
            resp = client.get(url, timeout=20.0, follow_redirects=True)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            print(f"[RSS] Error fetching '{name}' ({url}): {e}")
            continue

        count = 0
        for entry in feed.entries:
            if count >= max_items:
                break
            title = clean_html(getattr(entry, "title", ""))
            link = getattr(entry, "link", "").strip()
            raw_summary = ""
            if hasattr(entry, "content") and entry.content:
                raw_summary = entry.content[0].get("value", "")
            if not raw_summary:
                raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            summary = clean_html(raw_summary)

            if not title:
                continue

            if keywords:
                combined = f"{title} {summary}".lower()
                if not match_any_keyword(combined, keywords):
                    continue

            items.append(
                {
                    "id": make_item_id(link, title),
                    "title_orig": title,
                    "summary_orig": summary[:3500],
                    "source": name,
                    "category": category,
                    "url": link,
                    "published_at": parse_feed_date(entry),
                }
            )
            count += 1

        print(f"[RSS] '{name}': fetched {count} items")

    return items


def fetch_all(config: dict) -> List[dict]:
    headers = {"User-Agent": USER_AGENT}
    all_items = []
    with httpx.Client(headers=headers, timeout=20.0) as client:
        all_items.extend(fetch_openalex_streams(config.get("openalex_streams", []), client))
        all_items.extend(fetch_hf_daily_papers(config.get("hf_daily_papers", {}), client))
        all_items.extend(fetch_rss_sources(config.get("rss_sources", []), client))

    unique = {}
    for item in all_items:
        if item["id"] not in unique:
            unique[item["id"]] = item
    return list(unique.values())
