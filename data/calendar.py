"""
calendar.py – Fetches upcoming events via iCal links.

In Google Calendar the iCal link can be found at:
  Calendar settings → "Private address in iCal format"
  (Do not share this link – it contains a secret token)
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

CACHE_FILE = Path("cache/calendar.json")


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


def _parse_ical(content: bytes, cal_name: str, window_start: date, window_end: date) -> list[dict]:
    """Parses iCal content and returns events within the time window."""
    try:
        from icalendar import Calendar
        from icalendar.cal import Todo  # noqa: F401 – for type checking
    except ImportError:
        raise DataFetchError("icalendar is not installed. Run: pip install icalendar")

    try:
        cal = Calendar.from_ical(content)
    except Exception as e:
        raise DataFetchError(f"iCal parsing failed ({cal_name}): {e}") from e

    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("DTSTART")
        if not dtstart:
            continue

        start_val = dtstart.dt

        # All-day event (date) vs. timed event (datetime)
        if isinstance(start_val, datetime):
            event_date = start_val.astimezone().date()   # local time, not UTC
            time_str = start_val.astimezone().strftime("%H:%M")
            all_day = False
        else:
            event_date = start_val
            time_str = None
            all_day = True

        if not (window_start <= event_date <= window_end):
            continue

        summary = str(component.get("SUMMARY", "(ei otsikkoa)"))

        events.append({
            "title":    summary,
            "date":     event_date.isoformat(),
            "time":     time_str,
            "all_day":  all_day,
            "calendar": cal_name,
            "_sort":    event_date.isoformat() + (time_str or "00:00"),
        })

    return events


def fetch(config: dict, use_cache: bool = True) -> dict:
    ttl = config.get("cache", {}).get("ttl_minutes", 55)

    if use_cache and _cache_is_fresh(ttl):
        return _load_cache()

    calendars = config.get("calendars", [])
    if not calendars:
        raise DataFetchError(
            "No calendars in configuration. Add a 'calendars:' list with iCal links."
        )

    today = date.today()
    window_end = today + timedelta(days=30)
    all_events = []

    for cal_cfg in calendars:
        name = cal_cfg.get("name", "Kalenteri")
        url  = cal_cfg.get("ical_url", "")
        if not url:
            continue

        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            events = _parse_ical(resp.content, name, today, window_end)
            all_events.extend(events)
        except DataFetchError:
            raise
        except requests.RequestException as e:
            # Failure of a single calendar does not bring down the others
            cached = _load_cache()
            if cached:
                cached["_stale"] = True
                return cached
            raise DataFetchError(f"iCal fetch failed ({name}): {e}") from e

    all_events.sort(key=lambda e: e["_sort"])
    for ev in all_events:
        ev.pop("_sort", None)

    data = {
        "events":     all_events[:5],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(data)
    return data
