import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

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


def clean_doi(raw_doi: str) -> str:
    if not raw_doi:
        return ""
    doi = str(raw_doi).strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip()


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


def parse_openalex_work(
    w: dict,
    category: str,
    fallback_source: str,
    must_a: List[str],
    must_b: List[str],
    source_suffix: str = "",
    summary_prefix: str = "",
) -> Optional[dict]:
    title = (w.get("title") or "").strip()
    if not title:
        return None
    abstract = reconstruct_abstract(w.get("abstract_inverted_index"))
    combined = f"{title} {abstract}".lower()

    if not (match_any_keyword(combined, must_a) and match_any_keyword(combined, must_b)):
        return None

    primary_loc = w.get("primary_location") or {}
    source_info = primary_loc.get("source") or {}
    journal_name = source_info.get("display_name") or fallback_source
    raw_doi = w.get("doi") or ""
    doi = clean_doi(raw_doi)
    landing_url = primary_loc.get("landing_page_url") or raw_doi or w.get("id") or ""
    pub_date = w.get("publication_date") or f"{w.get('publication_year', '')}"
    if not pub_date:
        pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    work_type = (w.get("type") or "").lower()
    type_tag = "[综述 Review] " if work_type == "review" else ""

    authors = []
    for auth in (w.get("authorships") or [])[:12]:
        author_name = (auth.get("author") or {}).get("display_name") or ""
        if author_name.strip():
            authors.append(author_name.strip())

    source_display = f"{journal_name}{source_suffix}"
    if work_type == "review" and "综述" not in source_display:
        source_display = f"{source_display} · 综述"

    return {
        "id": make_item_id(landing_url, title),
        "title_orig": title,
        "summary_orig": f"{summary_prefix}{type_tag}{abstract}"[:3500],
        "source": source_display,
        "category": category,
        "url": landing_url,
        "doi": doi,
        "authors": authors,
        "published_at": pub_date,
    }


def fetch_classic_streams(
    streams: List[dict],
    seen_classics: Set[str],
    client: httpx.Client,
) -> List[dict]:
    items = []
    picked_ids = set(seen_classics)

    for stream in streams:
        name = stream.get("name", "经典回溯")
        category = stream.get("category", "classics")
        journals = stream.get("journals", [])
        year_range = str(stream.get("year_range", "2018-2024")).strip()
        min_citations = int(stream.get("min_citations", 10))
        max_items = int(stream.get("max_items", 1))
        search_query = stream.get("search_query", "")
        must_a = stream.get("must_match_a", [])
        must_b = stream.get("must_match_b", [])

        source_map = resolve_openalex_source_ids(journals, client)
        source_ids = list(set(source_map.values()))
        if not source_ids:
            print(f"[Classics] Skipping '{name}': no valid journal IDs.")
            continue

        cite_floor = max(0, min_citations - 1)
        filter_str = (
            f"primary_location.source.id:{'|'.join(source_ids)},"
            f"publication_year:{year_range},"
            f"cited_by_count:>{cite_floor},"
            f"type:article|review,"
            f"has_abstract:true"
        )

        count = 0
        for page in range(1, 5):
            if count >= max_items:
                break
            params = {
                "filter": filter_str,
                "sort": "cited_by_count:desc",
                "per-page": 100,
                "page": page,
            }
            if search_query:
                params["search"] = search_query

            try:
                resp = client.get("https://api.openalex.org/works", params=params, timeout=25.0)
                resp.raise_for_status()
                works = resp.json().get("results", [])
            except Exception as e:
                print(f"[Classics] Error fetching '{name}' (page {page}): {e}")
                break

            if not works:
                break

            for w in works:
                if count >= max_items:
                    break
                title = (w.get("title") or "").strip()
                if not title:
                    continue

                primary_loc = w.get("primary_location") or {}
                raw_doi = w.get("doi") or ""
                landing_url = primary_loc.get("landing_page_url") or raw_doi or w.get("id") or ""
                item_id = make_item_id(landing_url, title)
                if item_id in picked_ids:
                    continue

                pub_year = str(w.get("publication_year") or (w.get("publication_date") or "")[:4])
                cited_by = int(w.get("cited_by_count") or 0)
                suffix = f" · {pub_year} · 被引{cited_by}"
                prefix = f"[经典回溯 · {name} · {pub_year}年发表 · 被引{cited_by}次] "

                parsed = parse_openalex_work(
                    w=w,
                    category=category,
                    fallback_source=name,
                    must_a=must_a,
                    must_b=must_b,
                    source_suffix=suffix,
                    summary_prefix=prefix,
                )
                if not parsed:
                    continue

                items.append(parsed)
                picked_ids.add(item_id)
                count += 1

        print(f"[Classics] '{name}': picked {count} unseen classic(s)")

    return items


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
            f"type:article|review,"
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
            parsed = parse_openalex_work(
                w=w,
                category=category,
                fallback_source=name,
                must_a=must_a,
                must_b=must_b,
            )
            if not parsed:
                continue
            items.append(parsed)
            count += 1

        print(f"[OpenAlex] '{name}': matched {count} papers (from {len(works)} candidates)")

    return items


def fetch_category_backfill(
    config: dict,
    target_category: str,
    cursor_date_str: str,
    seen_ids: Set[str],
    step_days: int = 3,
    max_steps: int = 20,
    min_date_str: str = "2018-01-01",
    max_items_per_backfill: int = 6,
) -> Tuple[List[dict], str]:
    """
    当某学术板块当天未读新论文数为 0 时，从 cursor_date_str 开始每次向前追溯 step_days 天，
    直到找到至少 1 篇未读论文（或达到最大步数/最早日期），返回 (找到的论文列表, 更新后的历史日期游标)。
    """
    target_streams = [
        s for s in config.get("openalex_streams", [])
        if s.get("category") == target_category
    ]
    if not target_streams:
        return [], cursor_date_str

    headers = {"User-Agent": USER_AGENT}
    cur_end = datetime.strptime(cursor_date_str, "%Y-%m-%d").date()
    min_date = datetime.strptime(min_date_str, "%Y-%m-%d").date()

    found_items: List[dict] = []
    local_seen = set(seen_ids)

    with httpx.Client(headers=headers, timeout=25.0) as client:
        stream_sources = []
        for s in target_streams:
            source_map = resolve_openalex_source_ids(s.get("journals", []), client)
            source_ids = list(set(source_map.values()))
            if source_ids:
                stream_sources.append((s, source_ids))

        if not stream_sources:
            return [], cursor_date_str

        for step in range(1, max_steps + 1):
            if cur_end <= min_date:
                print(f"[Backfill:{target_category}] Reached minimum date {min_date_str}, stopping.")
                break

            cur_start = max(min_date, cur_end - timedelta(days=step_days))
            start_str = cur_start.strftime("%Y-%m-%d")
            end_str = cur_end.strftime("%Y-%m-%d")
            print(f"[Backfill:{target_category}] Step {step}: searching {start_str} ~ {end_str}...")

            window_items = []
            for s, source_ids in stream_sources:
                name = s.get("name", "OpenAlex")
                search_query = s.get("search_query", "")
                must_a = s.get("must_match_a", [])
                must_b = s.get("must_match_b", [])

                filter_str = (
                    f"primary_location.source.id:{'|'.join(source_ids)},"
                    f"from_publication_date:{start_str},"
                    f"to_publication_date:{end_str},"
                    f"type:article|review,"
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
                    print(f"[Backfill:{target_category}] Error fetching '{name}': {e}")
                    continue

                for w in works:
                    if len(window_items) >= max_items_per_backfill:
                        break
                    parsed = parse_openalex_work(
                        w=w,
                        category=target_category,
                        fallback_source=name,
                        must_a=must_a,
                        must_b=must_b,
                        source_suffix=" · 历史追溯",
                        summary_prefix=f"[历史追溯 {start_str}~{end_str}] ",
                    )
                    if not parsed:
                        continue
                    if parsed["id"] in local_seen:
                        continue
                    local_seen.add(parsed["id"])
                    window_items.append(parsed)

            cur_end = cur_start

            if window_items:
                found_items.extend(window_items)
                print(
                    f"[Backfill:{target_category}] Found {len(window_items)} unseen paper(s) "
                    f"in {start_str} ~ {end_str}! New cursor -> {cur_end.strftime('%Y-%m-%d')}"
                )
                break

    return found_items, cur_end.strftime("%Y-%m-%d")


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
            doi = f"10.48550/arXiv.{paper_id}" if paper_id else ""
            pub_raw = paper.get("publishedAt") or entry.get("publishedAt") or ""
            pub_date = pub_raw[:10] if len(pub_raw) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            upvotes = paper.get("upvotes", 0)

            authors = []
            for a in (paper.get("authors") or [])[:12]:
                a_name = a.get("name") or "" if isinstance(a, dict) else str(a)
                if a_name.strip():
                    authors.append(a_name.strip())

            items.append(
                {
                    "id": make_item_id(url, title),
                    "title_orig": title,
                    "summary_orig": f"[HF Upvotes: {upvotes}] {summary}"[:3500],
                    "source": "Hugging Face Daily Papers",
                    "category": category,
                    "url": url,
                    "doi": doi,
                    "authors": authors,
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


def extract_rss_authors(entry) -> List[str]:
    authors = []
    if hasattr(entry, "authors") and entry.authors:
        for a in entry.authors[:12]:
            name = clean_html(a.get("name", "")) if isinstance(a, dict) else clean_html(str(a))
            if name:
                authors.append(name)
    elif hasattr(entry, "author") and entry.author:
        raw = clean_html(str(entry.author))
        if raw:
            authors = [p.strip() for p in raw.split(",") if p.strip()][:12]
    return authors


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

            doi = ""
            arxiv_match = re.search(r"arxiv\.org/abs/([0-9]+\.[0-9]+)", link, flags=re.IGNORECASE)
            if arxiv_match:
                doi = f"10.48550/arXiv.{arxiv_match.group(1)}"

            items.append(
                {
                    "id": make_item_id(link, title),
                    "title_orig": title,
                    "summary_orig": summary[:3500],
                    "source": name,
                    "category": category,
                    "url": link,
                    "doi": doi,
                    "authors": extract_rss_authors(entry),
                    "published_at": parse_feed_date(entry),
                }
            )
            count += 1

        print(f"[RSS] '{name}': fetched {count} items")

    return items


def fetch_all(config: dict, seen_classics: Optional[Set[str]] = None) -> List[dict]:
    headers = {"User-Agent": USER_AGENT}
    all_items = []
    with httpx.Client(headers=headers, timeout=20.0) as client:
        all_items.extend(
            fetch_classic_streams(config.get("classic_streams", []), seen_classics or set(), client)
        )
        all_items.extend(fetch_openalex_streams(config.get("openalex_streams", []), client))
        all_items.extend(fetch_hf_daily_papers(config.get("hf_daily_papers", {}), client))
        all_items.extend(fetch_rss_sources(config.get("rss_sources", []), client))

    unique = {}
    for item in all_items:
        if item["id"] not in unique:
            unique[item["id"]] = item
    return list(unique.values())
