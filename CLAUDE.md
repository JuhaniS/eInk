# E-ink Dashboard – CLAUDE.md

## Project overview

Home dashboard for Waveshare 7.5" e-ink display (800×480px, grayscale).
Development on macOS (PNG simulation), deployment target: Raspberry Pi Zero 2 W.

Hardware decision still pending — also considering Inkplate (ESP32-based, battery-powered)
for wireless/fridge-door mounting. See architecture note below.

## Running

```bash
cd /Users/sihvojuh/Personal/Projects/eInk
source venv/bin/activate

python main.py --preview           # full run, open PNG on macOS
python main.py --no-cache --preview
python main.py --only hsl --no-cache   # test single module
```

Python: 3.13, venv at `venv/`

## File structure

```
main.py          – entry point, CLI, module orchestration
render.py        – Pillow renderer, 800×480 grayscale (mode L)
config.yaml      – credentials + settings (not committed)
config.example.yaml

data/
  weather.py     – Open-Meteo REST (no auth)
  calendar.py    – iCal / Google Calendar (secret URL token)
  electricity.py – Caruna via pycaruna (username/password)
  waste.py       – manual schedule from config
  evaka.py       – Espoo eVaka weak-login session API
  hsl.py         – HSL Digitransit v2 GraphQL

display/
  simulator.py   – saves output/dashboard.png
  epaper.py      – Waveshare 7.5" V2 driver (Raspi only)
```

## Layout (3 rows × 2 columns)

```
┌──────────────────────┬──────────────────────┐  ROW1_H = 162px
│  PÄIVÄKOTI           │  KALENTERI           │
├──────────────────────┼──────────────────────┤  ROW2_H = 148px
│  SÄHKÖ               │  HSL                 │
├──────────────────────┼──────────────────────┤  ROW3_H = 170px
│  SÄÄ                 │  JÄTTEET             │
└──────────────────────┴──────────────────────┘
LEFT_W = 380px, RIGHT_X = 381px
```

## Rendering conventions (render.py)

- Fonts: Helvetica (macOS), DejaVu (Linux)
- FONT_HUGE=52bold, FONT_LARGE=26bold, FONT_MED=20, FONT_SMALL=16, FONT_TINY=13
- FG=0 (black), BG=255 (white), GRAY=160
- Section headers: FONT_LARGE bold ("PÄIVÄKOTI", "HSL" etc.)
- Each list section uses two rows per item:
  - Row 1 (FONT_SMALL, black): main content + right-aligned value
  - Row 2 (FONT_TINY, GRAY): secondary info
  - Divider between items, but NOT after the last item
- Weather icons: geometric Pillow drawing (no emoji/unicode symbols)
- Arrows: use `->` not `→` (Helvetica doesn't render unicode arrows)

## Data module patterns

Each module follows the same pattern:
```python
def fetch(config: dict, use_cache: bool = True) -> dict:
    ttl = config.get("cache", {}).get("MODULE_ttl_minutes", DEFAULT)
    if use_cache and _cache_is_fresh(ttl): return _load_cache()
    # ... fetch from API ...
    _save_cache(data)
    return data
```

Stale cache fallback on network errors: `data["_stale"] = True`

## Cache TTLs (config.yaml)

```yaml
cache:
  ttl_minutes: 55          # weather, calendar (default)
  hsl_ttl_minutes: 10      # real-time transit
  hsl_active_hours: [6, 22] # no HSL fetches outside these hours
  evaka_ttl_minutes: 1440  # daycare: once per day
  electricity_ttl_minutes: 720  # electricity: twice per day
```

Cron runs `main.py` every 10 minutes; each module decides independently.

## HSL module specifics (data/hsl.py)

- Digitransit v2 GraphQL: `https://api.digitransit.fi/routing/v2/hsl/gtfs/v1`
- Variable types: `CoordinateValue!` for lat/lon, `OffsetDateTime!` for time
- startTime/endTime from API are **epoch milliseconds** (not ISO strings)
- Mode-specific walk time filtering:
  - BUS/TRAM/FERRY: `min_walk_bus` (default 3 min)
  - RAIL/SUBWAY: `min_walk_rail` (default 15 min)
- Each connection returns: departure, arrival, minutes_until, lines ("165 -> U"),
  walk_minutes, first_stop, first_depart
- Outside `hsl_active_hours`: returns stale cache or empty result (no API call)

## eVaka module specifics (data/evaka.py)

- POST `/api/citizen/auth/weak-login` → session cookie saved to `cache/evaka_session.json`
- GET `/api/citizen/calendar-events?start=...&end=...`
- Auto re-login on 401/403
- Events have separate `title` and `description` fields (not combined)
- 14-day window

## Calendar module specifics (data/calendar.py)

- iCal links from config (no OAuth needed)
- 30-day window (was 7, extended)
- Date uses local timezone (`.astimezone().date()`), not UTC
- Returns up to 5 events, sorted by date+time

## Known issues / TODO

- [ ] Hardware decision: Waveshare 7.5" + Raspi Zero 2 W (wired) vs
      Inkplate (ESP32, battery-powered, WiFi fetch of pre-rendered PNG)
- [ ] If Inkplate: add simple HTTP server to serve `output/dashboard.png`,
      and write Inkplate Arduino/MicroPython sketch to fetch + display it
- [ ] Raspi deployment: install Waveshare e-Paper library, set up cron
- [ ] Test pycaruna (electricity) with real Caruna credentials
- [ ] Consider adding `config.example.yaml` update when new config keys added

## Git

Branch: main
Last commit: "Add e-ink dashboard with weather, calendar, electricity, waste, daycare and transit"
Uncommitted changes after that commit: README.md, CLAUDE.md, cache schedule changes,
HSL active hours, per-module TTLs, last-divider fix, calendar 30-day window.
