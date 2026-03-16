"""
evaka.py – Fetches daycare events from the Espoo eVaka service.

Authenticates via the weak-login endpoint. The session cookie is stored in
cache/evaka_session.json – re-login only happens when the session expires.

Config:
  evaka:
    username: "sahkoposti@example.com"
    password: "salasana"
    base_url: "https://espoonvarhaiskasvatus.fi"  # optional
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

CACHE_FILE   = Path("cache/evaka.json")
SESSION_FILE = Path("cache/evaka_session.json")
BASE_URL     = "https://espoonvarhaiskasvatus.fi"
WINDOW_DAYS  = 14


class DataFetchError(Exception):
    pass


# ── Cache ────────────────────────────────────────────────────────────────────

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


# ── Session cookie management ──────────────────────────────────────────────

def _load_session() -> dict:
    try:
        return json.loads(SESSION_FILE.read_text())
    except Exception:
        return {}


def _save_session(cookies: dict):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(cookies, ensure_ascii=False))


# ── HTTP helper functions ──────────────────────────────────────────────────

def _make_session(cookies: dict | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "accept":       "application/json, text/plain, */*",
        "user-agent":   "Mozilla/5.0",
        "x-evaka-csrf": "1",
    })
    if cookies:
        for name, value in cookies.items():
            s.cookies.set(name, value)
    return s


def _login(base_url: str, username: str, password: str) -> requests.Session:
    """Logs in and returns a session object with cookies."""
    s = _make_session()
    try:
        resp = s.post(
            f"{base_url}/api/citizen/auth/weak-login",
            json={"username": username, "password": password},
            headers={"content-type": "application/json",
                     "referer": f"{base_url}/login/form?next=%2F"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise DataFetchError(f"eVaka login failed: {e}") from e

    _save_session(dict(s.cookies))
    return s


def _fetch_raw(s: requests.Session, base_url: str, start: date, end: date) -> list:
    """Fetches raw data from the API. Raises DataFetchError on failure."""
    try:
        resp = s.get(
            f"{base_url}/api/citizen/calendar-events",
            params={"start": start.isoformat(), "end": end.isoformat()},
            headers={"referer": f"{base_url}/calendar"},
            timeout=15,
        )
        if resp.status_code in (401, 403):
            raise DataFetchError("_relogin")   # internal signal
        resp.raise_for_status()
        return resp.json()
    except DataFetchError:
        raise
    except requests.RequestException as e:
        raise DataFetchError(f"eVaka event fetch failed: {e}") from e


# ── Conversion to standard format ──────────────────────────────────────────

def _parse_events(raw: list, today: date, end: date) -> list[dict]:
    events = []
    for ev in raw:
        period    = ev.get("period", {})
        start_str = period.get("start", "")
        if not start_str:
            continue
        try:
            ev_date = date.fromisoformat(start_str)
        except ValueError:
            continue
        if not (today <= ev_date <= end):
            continue

        title = ev.get("title", "")
        desc  = ev.get("description", "")

        events.append({
            "title":       title,
            "description": desc,
            "date":        ev_date.isoformat(),
            "time":        None,
            "all_day":     True,
            "calendar":    "Päiväkoti",
        })

    events.sort(key=lambda e: e["date"])
    return events


# ── Public interface ────────────────────────────────────────────────────────

def fetch(config: dict, use_cache: bool = True) -> dict:
    ttl = config.get("cache", {}).get("evaka_ttl_minutes",
          config.get("cache", {}).get("ttl_minutes", 1440))

    if use_cache and _cache_is_fresh(ttl):
        return _load_cache()

    evaka_cfg = config.get("evaka", {})
    username  = evaka_cfg.get("username", "")
    password  = evaka_cfg.get("password", "")
    base_url  = evaka_cfg.get("base_url", BASE_URL).rstrip("/")

    if not username or not password:
        raise DataFetchError(
            "eVaka credentials missing from config (evaka.username, evaka.password)"
        )

    today = date.today()
    end   = today + timedelta(days=WINDOW_DAYS)

    # Try with saved cookies first
    raw = None
    saved = _load_session()
    if saved:
        s = _make_session(saved)
        try:
            raw = _fetch_raw(s, base_url, today, end)
        except DataFetchError as e:
            if "_relogin" not in str(e):
                raise
            # Session expired – will re-login below

    # Log in if no cookies existed or session had expired
    if raw is None:
        s   = _login(base_url, username, password)
        raw = _fetch_raw(s, base_url, today, end)

    events = _parse_events(raw, today, end)
    data   = {
        "events":     events,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(data)
    return data
