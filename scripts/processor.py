import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from openai import OpenAI


def build_client() -> tuple[OpenAI, str]:
    api_key = os.environ.get("LLM_API_KEY" or "").strip()
    base_url = os.environ.get("LLM_BASE_URL" or "https://api.deepseek.com/v1").strip()
    model = os.environ.get("LLM_MODEL", "deepseek-flash").strip()

    if not api_key:
        raise RuntimeError(
            "Missing LLM_API_KEY environment variable. Please set it in GitHub Repository Secrets."
        )

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


def extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def process_single_item(
    item: dict,
    system_prompt: str,
    client: OpenAI,
    model: str,
) -> Optional[dict]:
    user_payload = (
        f"领域分类：{item['category']}\n"
        f"来源：{item['source']}\n"
        f"发布日期：{item['published_at']}\n"
        f"原文标题：{item['title_orig']}\n"
        f"摘要/正文内容：\n{item.get('summary_orig') or '（无摘要，请基于标题与来源背景审慎评估，并在拆解中注明仅有标题信息）'}"
    )

    last_err = None
    for attempt in range(3):
        try:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_payload},
                ],
                "temperature": 0.3,
            }
            if attempt == 0:
                kwargs["response_format"] = {"type": "json_object"}

            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            parsed = extract_json_object(content)

            score = float(parsed.get("score", 3.0))
            score = max(1.0, min(5.0, round(score, 1)))
            tldr = parsed.get("tldr") or {}
            tags = parsed.get("tags") or []
            if not isinstance(tags, list):
                tags = [str(tags)]

            return {
                "id": item["id"],
                "title_zh": str(parsed.get("title_zh") or item["title_orig"]).strip(),
                "title_orig": item["title_orig"],
                "source": item["source"],
                "category": item["category"],
                "url": item["url"],
                "published_at": item["published_at"],
                "score": score,
                "tags": [str(t).strip() for t in tags[:5] if str(t).strip()],
                "tldr": {
                    "problem": str(tldr.get("problem", "")).strip(),
                    "method": str(tldr.get("method", "")).strip(),
                    "takeaway": str(tldr.get("takeaway", "")).strip(),
                },
                "conditions_and_metrics": str(parsed.get("conditions_and_metrics", "")).strip(),
                "deep_dive": str(parsed.get("deep_dive", "")).strip(),
                "inspiration": str(parsed.get("inspiration", "")).strip(),
            }
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))

    print(f"[AI] Failed after retries for '{item['title_orig'][:60]}': {last_err}")
    return None


def process_items(items: List[dict], system_prompt: str, max_workers: int = 4) -> List[dict]:
    if not items:
        return []

    client, model = build_client()
    results = []
    print(f"[AI] Processing {len(items)} items with model '{model}'...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(process_single_item, item, system_prompt, client, model): item
            for item in items
        }
        for future in as_completed(future_map):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: (x.get("score", 0), x.get("published_at", "")), reverse=True)
    if not results:
        raise RuntimeError(
        f"All {len(items)} AI requests failed. Check secrets LLM_API_KEY / "
        f"LLM_BASE_URL / LLM_MODEL (current model: {model}, base_url: {base_url}."
        )
    return results
