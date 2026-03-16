"""
weather.py – Fetches weather data from the Open-Meteo API (free, no API key required).
"""

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests

CACHE_FILE = Path("cache/weather.json")
API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → icon key and Finnish description
_WMO_MAP = {
    0:  ("clear",         "Selkeää"),
    1:  ("mainly_clear",  "Pääosin selkeää"),
    2:  ("partly_cloudy", "Puolipilvistä"),
    3:  ("overcast",      "Pilvistä"),
    45: ("fog",           "Sumua"),
    48: ("fog",           "Huurteinen sumu"),
    51: ("drizzle",       "Tihkusadetta"),
    53: ("drizzle",       "Kohtalaista tihkua"),
    55: ("drizzle",       "Runsasta tihkua"),
    61: ("rain",          "Heikkoa sadetta"),
    63: ("rain",          "Kohtalaista sadetta"),
    65: ("rain",          "Runsasta sadetta"),
    71: ("snow",          "Heikkoa lumisadetta"),
    73: ("snow",          "Kohtalaista lumisadetta"),
    75: ("snow",          "Runsasta lumisadetta"),
    80: ("rain",          "Sadekuuroja"),
    81: ("rain",          "Kohtalaisia kuuroja"),
    82: ("rain",          "Rankkakuuroja"),
    95: ("thunderstorm",  "Ukkosmyrsky"),
    96: ("thunderstorm",  "Ukkosmyrsky, raekuuroja"),
    99: ("thunderstorm",  "Voimakas ukkosmyrsky"),
}


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


def fetch(config: dict, use_cache: bool = True) -> dict:
    ttl = config.get("cache", {}).get("ttl_minutes", 55)

    if use_cache and _cache_is_fresh(ttl):
        return _load_cache()

    loc = config.get("location", {})
    lat = loc.get("latitude", 60.1699)
    lon = loc.get("longitude", 24.9384)

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
            "precipitation",
        ],
        "daily": ["temperature_2m_max", "temperature_2m_min", "weather_code"],
        "timezone": "auto",
        "forecast_days": 5,
    }

    try:
        resp = requests.get(API_URL, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as e:
        cached = _load_cache()
        if cached:
            cached["_stale"] = True
            return cached
        raise DataFetchError(f"Weather fetch failed: {e}") from e

    cur = raw.get("current", {})
    daily = raw.get("daily", {})
    wmo = cur.get("weather_code", 0)
    icon, cond_fi = _WMO_MAP.get(wmo, ("unknown", "Tuntematon"))

    _FI_DAYS = ["Ma", "Ti", "Ke", "To", "Pe", "La", "Su"]
    dates      = daily.get("time", [])
    max_temps  = daily.get("temperature_2m_max", [])
    min_temps  = daily.get("temperature_2m_min", [])
    day_codes  = daily.get("weather_code", [])

    forecast = []
    for i in range(1, min(5, len(dates))):
        try:
            d = date.fromisoformat(dates[i])
        except (ValueError, TypeError):
            continue
        wmo_i = day_codes[i] if i < len(day_codes) else 0
        fc_icon, _ = _WMO_MAP.get(wmo_i, ("unknown", ""))
        forecast.append({
            "day":  _FI_DAYS[d.weekday()],
            "date": f"{d.day}.{d.month}.",
            "high": max_temps[i] if i < len(max_temps) else None,
            "low":  min_temps[i] if i < len(min_temps) else None,
            "icon": fc_icon,
        })

    data = {
        "temperature":         cur.get("temperature_2m"),
        "feels_like":          cur.get("apparent_temperature"),
        "condition":           cond_fi,
        "condition_fi":        cond_fi,
        "wind_speed":          cur.get("wind_speed_10m"),
        "precipitation":       cur.get("precipitation"),
        "icon":                icon,
        "forecast_today_high": max_temps[0] if max_temps else None,
        "forecast_today_low":  min_temps[0] if min_temps else None,
        "forecast":            forecast,
        "fetched_at":          datetime.now().isoformat(timespec="seconds"),
    }

    _save_cache(data)
    return data
