"""
news.py – Fetches top headlines from an RSS feed (default: YLE Uutiset).

Config (all optional):
  news:
    url: "https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_UUTISET"
    num_items: 3        # how many headlines to show (1–5)
    label: "UUTISET"   # section label shown in the dashboard
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

CACHE_FILE = Path("cache/news.json")
DEFAULT_URL = "https://feeds.yle.fi/uutiset/v1/majorHeadlines/YLE_UUTISET.rss"
DEFAULT_NUM = 3
DEFAULT_TTL = 30   # minutes


class DataFetchError(Exception):
    pass


def _cache_is_fresh(ttl_minutes: int) -> bool:
    if not CACHE_FILE.exists():
        return False
    age = datetime.now().timestamp() - CACHE_FILE.stat().st_mtime
    return age < ttl_minutes * 60


def _load_cache() -> dict | None:
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return None


def _save_cache(data: dict):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _parse_rss(content: bytes, num_items: int) -> list[dict]:
    """Parses RSS XML and returns a list of headline dicts."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise DataFetchError(f"RSS parse error: {e}") from e

    # Namespace-aware search — RSS 2.0 has no default namespace
    channel = root.find("channel")
    if channel is None:
        raise DataFetchError("RSS: no <channel> element found")

    items = []
    for item in channel.findall("item")[:num_items]:
        title = (item.findtext("title") or "").strip()
        desc  = (item.findtext("description") or "").strip()

        # Strip HTML tags from description (YLE wraps in <p> etc.)
        if "<" in desc:
            try:
                desc = ET.fromstring(f"<x>{desc}</x>").text or ""
            except ET.ParseError:
                # Simple fallback: remove anything between < >
                import re
                desc = re.sub(r"<[^>]+>", "", desc).strip()

        if title:
            items.append({"title": title, "description": desc})

    return items


def fetch(config: dict, use_cache: bool = True) -> dict:
    news_cfg  = config.get("news", {})
    ttl       = news_cfg.get("ttl_minutes",
                config.get("cache", {}).get("ttl_minutes", DEFAULT_TTL))
    url       = news_cfg.get("url", DEFAULT_URL)
    num_items = int(news_cfg.get("num_items", DEFAULT_NUM))

    if use_cache and _cache_is_fresh(ttl):
        cached = _load_cache()
        if cached:
            return cached

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "eink-dashboard/1.0"})
        resp.raise_for_status()
        items = _parse_rss(resp.content, num_items)
    except DataFetchError:
        raise
    except requests.RequestException as e:
        cached = _load_cache()
        if cached:
            cached["_stale"] = True
            return cached
        raise DataFetchError(f"News fetch failed: {e}") from e

    label = news_cfg.get("label", "UUTISET")
    data  = {
        "items":      items,
        "label":      label,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(data)
    return data
