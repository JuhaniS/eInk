"""
waste.py – Waste collection schedule.

Reads the schedule directly from config.yaml. The user enters their own collection days,
and the module automatically calculates the next collections and how many days away they are.

Config structure:
  waste:
    collections:
      - type: "Sekajäte"
        weekday: 3          # weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
        interval_weeks: 2   # every other week
        next_date: "2026-03-20"  # next known date (anchor point)
      - type: "Biojäte"
        weekday: 3
        interval_weeks: 1   # every week
        next_date: "2026-03-20"
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

CACHE_FILE = Path("cache/waste.json")


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


def _next_occurrences(next_date: date, interval_weeks: int, count: int = 3) -> list[date]:
    """Calculates upcoming collection dates starting from the anchor date."""
    today = date.today()
    delta = timedelta(weeks=interval_weeks)

    # Advance from anchor until we reach today or the future
    current = next_date
    while current < today:
        current += delta

    results = []
    for _ in range(count):
        results.append(current)
        current += delta

    return results


def fetch(config: dict, use_cache: bool = True) -> dict:
    ttl = config.get("cache", {}).get("ttl_minutes", 55)

    # Waste data is calculated from config rather than fetched from the network,
    # but cache prevents unnecessary recalculation
    if use_cache and _cache_is_fresh(ttl):
        return _load_cache()

    waste_cfg = config.get("waste", {})
    collections_cfg = waste_cfg.get("collections", [])

    if not collections_cfg:
        raise DataFetchError(
            "Waste collection schedule is missing from configuration. "
            "Add a 'waste.collections' list to config.yaml. "
            "See config.example.yaml for an example."
        )

    today = date.today()
    all_collections = []

    for col in collections_cfg:
        col_type     = col.get("type", "Tuntematon")
        interval     = int(col.get("interval_weeks", 2))
        next_date_str = col.get("next_date", "")

        if not next_date_str:
            continue

        try:
            anchor = date.fromisoformat(next_date_str)
        except ValueError:
            continue

        upcoming = _next_occurrences(anchor, interval, count=1)
        for d in upcoming:
            all_collections.append({
                "type":       col_type,
                "date":       d.isoformat(),
                "days_until": (d - today).days,
            })

    # Sort by date
    all_collections.sort(key=lambda c: c["date"])

    data = {
        "next_collections": all_collections[:6],
        "fetched_at":       datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(data)
    return data
