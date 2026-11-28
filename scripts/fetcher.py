import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

import feedparser
import httpx

USER_AGENT = "PersonalHub/1.0 (+[https://github.com](https://github.com); mailto:personal-hub@example.com)"
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
        json.dump(cache, f, ensure_ascii=False, indent=2
