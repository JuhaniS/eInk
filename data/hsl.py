"""
hsl.py – Next connections from the HSL journey planner.

Uses Digitransit Routing API v2 (GraphQL).
API key can be obtained at: https://portal-api.digitransit.fi/

Config:
  hsl:
    api_key: "your-subscription-key"
    to_name: "Pasila"
    to_lat: 60.1985
    to_lon: 24.9323
    num_results: 3   # optional, default 3
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

CACHE_FILE      = Path("cache/hsl.json")
DEFAULT_TTL_MIN = 10   # default: refresh every 10 minutes
API_URL         = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"

QUERY = """
query NextTrips($fromLat: CoordinateValue!, $fromLon: CoordinateValue!, $toLat: CoordinateValue!, $toLon: CoordinateValue!, $when: OffsetDateTime!, $n: Int!) {
  planConnection(
    origin: {
      location: { coordinate: { latitude: $fromLat, longitude: $fromLon } }
    }
    destination: {
      location: { coordinate: { latitude: $toLat, longitude: $toLon } }
    }
    first: $n
    dateTime: { earliestDeparture: $when }
    modes: {
      transit: {
        transit: [
          { mode: BUS }
          { mode: TRAM }
          { mode: RAIL }
          { mode: SUBWAY }
          { mode: FERRY }
        ]
      }
    }
  ) {
    edges {
      node {
        startTime
        endTime
        legs {
          startTime
          mode
          route { shortName }
          from { name }
        }
      }
    }
  }
}
"""


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


def _within_active_hours(active_hours: list) -> bool:
    """Returns True if current hour is within the active window [start, end]."""
    if not active_hours or len(active_hours) < 2:
        return True
    hour = datetime.now().hour
    return active_hours[0] <= hour <= active_hours[1]


def fetch(config: dict, use_cache: bool = True) -> dict:
    cache_cfg   = config.get("cache", {})
    ttl         = cache_cfg.get("hsl_ttl_minutes", DEFAULT_TTL_MIN)
    active_hours = cache_cfg.get("hsl_active_hours", [])

    if use_cache and _cache_is_fresh(ttl):
        return _load_cache()

    # Outside active hours: return stale cache if available, otherwise empty result
    if not _within_active_hours(active_hours):
        cached = _load_cache()
        if cached:
            cached["_stale"] = True
            return cached
        to_name = config.get("hsl", {}).get("to_name", "")
        return {"connections": [], "to_name": to_name, "fetched_at": datetime.now().isoformat(timespec="seconds")}

    hsl_cfg = config.get("hsl", {})
    api_key  = hsl_cfg.get("api_key", "")
    to_name  = hsl_cfg.get("to_name", "")
    to_lat   = hsl_cfg.get("to_lat")
    to_lon   = hsl_cfg.get("to_lon")
    n        = int(hsl_cfg.get("num_results", 3))

    if not api_key:
        raise DataFetchError(
            "HSL API key missing. Register at "
            "https://portal-api.digitransit.fi/ and add hsl.api_key to config."
        )
    if to_lat is None or to_lon is None:
        raise DataFetchError(
            "hsl.to_lat and hsl.to_lon are required in config.yaml"
        )

    loc = config.get("location", {})
    from_lat = loc.get("latitude")
    from_lon = loc.get("longitude")
    if from_lat is None or from_lon is None:
        raise DataFetchError(
            "location.latitude and location.longitude are required in config.yaml"
        )
    from_lat = float(from_lat)
    from_lon = float(from_lon)
    to_lat   = float(to_lat)
    to_lon   = float(to_lon)

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")

    headers = {
        "Content-Type":                  "application/json",
        "digitransit-subscription-key":  api_key,
    }
    payload = {
        "query": QUERY,
        "variables": {
            "fromLat": from_lat,
            "fromLon": from_lon,
            "toLat":   to_lat,
            "toLon":   to_lon,
            "when":    now_iso,
            "n":       n,
        },
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as e:
        cached = _load_cache()
        if cached:
            cached["_stale"] = True
            return cached
        raise DataFetchError(f"HSL fetch failed: {e}") from e

    errors = raw.get("errors")
    if errors:
        raise DataFetchError(f"HSL GraphQL error: {errors[0].get('message', errors)}")

    min_walk_bus  = int(hsl_cfg.get("min_walk_bus",  3))
    min_walk_rail = int(hsl_cfg.get("min_walk_rail", 15))

    edges = raw.get("data", {}).get("planConnection", {}).get("edges", [])
    now_ts = datetime.now().timestamp()
    connections = []

    for edge in edges:
        node = edge.get("node", {})
        start_iso = node.get("startTime")
        end_iso   = node.get("endTime")
        legs      = node.get("legs", [])

        if not start_iso:
            continue

        try:
            depart_dt = datetime.fromtimestamp(int(start_iso) / 1000)
            arrive_dt = datetime.fromtimestamp(int(end_iso)   / 1000) if end_iso else None
        except (ValueError, TypeError):
            continue

        # All non-walking legs in order → "165 -> U"
        transit_legs = [l for l in legs if l.get("mode") != "WALK"]
        lines_str = " -> ".join(
            l.get("route", {}).get("shortName", "?") for l in transit_legs
        )

        # Details of the first transit leg
        first_transit_minutes = None
        first_mode  = transit_legs[0].get("mode", "")    if transit_legs else ""
        first_stop  = transit_legs[0].get("from", {}).get("name", "") if transit_legs else ""
        first_depart_str = ""
        if transit_legs:
            try:
                first_ts = int(transit_legs[0].get("startTime", 0)) / 1000
                first_transit_minutes = int((first_ts - now_ts) / 60)
                first_depart_str = datetime.fromtimestamp(first_ts).strftime("%H:%M")
            except (ValueError, TypeError):
                pass

        # Filter out connections that can no longer be caught (mode-specific walk time)
        min_needed = min_walk_rail if first_mode in ("RAIL", "SUBWAY") else min_walk_bus
        if first_transit_minutes is not None and first_transit_minutes < min_needed:
            continue

        minutes_until = int((depart_dt.timestamp() - now_ts) / 60)

        # Walk time from home to stop = time from trip start to first transit leg
        walk_minutes = 0
        if transit_legs:
            try:
                walk_minutes = max(0, int(
                    (float(transit_legs[0].get("startTime", 0)) / 1000 - depart_dt.timestamp()) / 60
                ))
            except (ValueError, TypeError):
                pass

        connections.append({
            "departure":      depart_dt.strftime("%H:%M"),
            "arrival":        arrive_dt.strftime("%H:%M") if arrive_dt else "",
            "minutes_until":  minutes_until,
            "lines":          lines_str,
            "to":             to_name,
            "walk_minutes":   walk_minutes,
            "first_mode":     first_mode,
            "first_stop":     first_stop,
            "first_depart":   first_depart_str,
        })

    data = {
        "connections": connections,
        "to_name":     to_name,
        "fetched_at":  datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(data)
    return data
