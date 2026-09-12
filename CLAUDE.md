# E-ink Dashboard – CLAUDE.md

## Project overview

Home dashboard for Waveshare 7.5" e-ink display (800×480px, grayscale).
Development on macOS (PNG simulation), deployed on Raspberry Pi Zero 2 W.

Hardware: Waveshare 7.5" e-Paper HAT V2 + Raspberry Pi Zero 2 W (wall-mounted in kitchen).
Network: 2.4 GHz WiFi only (Zero 2 W limitation), hostname `kitchen.local` (192.168.1.241).
WiFi power-save is disabled (`nmcli connection modify netplan-wlan0-asdasda2.4
802-11-wireless.powersave 2`, persists across reboots) — with the NetworkManager
default the Pi slept too deeply to answer ping/SSH/mDNS between fetches.

## Running

```bash
cd /Users/sihvojuh/Personal/Projects/eInk
source venv/bin/activate

python main.py --preview           # full run, open PNG on macOS
python main.py --no-cache --preview
python main.py --only hsl --no-cache   # test single module
```

Sync to Pi:
```bash
./sync.sh   # rsync to juhani@kitchen.local:~/eInk/ (excludes venv, cache, output, .git)
```

Run on Pi:
```bash
ssh juhani@kitchen.local "cd ~/eInk && venv/bin/python main.py"
ssh juhani@kitchen.local "cd ~/eInk && venv/bin/python main.py --no-cache"
```

Python: 3.13, venv at `venv/`

## File structure

```
main.py              – entry point, CLI, module orchestration
render.py            – Pillow renderer, 800×480 grayscale (mode L)
sync.sh              – rsync helper script (Mac → Pi)
config.yaml          – credentials + settings (NOT committed)
config.example.yaml  – template

fonts/
  Inter-Regular.ttf  – preferred font (both Mac and Pi)
  Inter-Bold.ttf

data/
  weather.py         – Open-Meteo REST (no auth)
  calendar.py        – iCal / Google Calendar (secret URL token)
  electricity.py     – Caruna via pycaruna (username/password)
  waste.py           – manual schedule from config
  evaka.py           – Espoo eVaka weak-login session API
  hsl.py             – HSL Digitransit v2 GraphQL

display/
  simulator.py       – saves output/dashboard.png (macOS)
  epaper.py          – Waveshare 7.5" V2 driver (Raspi only)
```

## Layout (NOW band + content row + stats line + forecast strip)

```
┌────────────────────────────────────────────────────────┐  BAND_H = 118px
│  07:42  to 6.8.   ☁ 18° Pilvistä        lähtö 12 min  │  (inverted: white bg)
├──────────────────┬──────────────────┬──────────────────┤  MID_H = 190px
│  PÄIVÄKOTI       │  KALENTERI       │  HSL lähdöt      │
├──────────────────┴──────────────────┴──────────────────┤  STATS_Y = 308
│  Sähkö 32.0 kWh eilen · Sekajäte 7 pv · Biojäte 26 pv  │
├────────────────────────────────────────────────────────┤  FORECAST_H = 140px
│  ENNUSTE  (full width, 7 days as columns)              │
└────────────────────────────────────────────────────────┘
COL_W ≈ 266px, COL2_X = 267, COL3_X = 534, FORECAST_Y = 340
```

- NOW band (`_draw_now_band`): 72px clock + date, current weather (black icon
  via `_draw_weather_icon(..., ink=BG, paper=FG)`), leave-in countdown for the
  first HSL connection ("12 min"). Electricity + waste render as one stats
  line (`_draw_stats_line`) — they no longer have cells.
- Partial regions live in the band: CLOCK_REGION = (0, 0, 240, 118),
  HSL_REGION = (624, 0, 800, 118) — clock and countdown tick every minute.

## Rendering conventions (render.py)

- **Fonts**: Inter (fonts/ dir) → Futura (macOS) → Helvetica (macOS) → DejaVu (Linux)
- **Colors**: inverted — BG=0 (black), FG=255 (white), GRAY=255, DIVIDER=255
  (pure white: the panel is 1-bit, mid-grays dither to speckle)
- FONT_CLOCK72=72bold, FONT_HERO=46bold, FONT_MED=18bold, FONT_SMALL=17bold,
  FONT_TINY=14bold, FONT_TINY_R=14 regular, FONT_REG18=18 regular, FONT_LABEL=12
- Section labels: FONT_LABEL gray at top of each cell (`_label()` helper)
- No dividers between list items (removed for cleaner look)
- Weather icons: geometric Pillow drawing (no emoji/unicode symbols)
- HSL mode icons: removed — lines ("165 -> U") are self-explanatory
- Arrows: use `->` not `→` (unicode arrows unreliable across fonts)
- Text wrapping: `_wrap_text(draw, text, font, max_width)` — pixel-based, not char-based
- Badge: `_badge(draw, x, y, text)` — black pill with white text (used in HSL)

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
  ttl_minutes: 55           # weather, calendar (default)
  hsl_ttl_minutes: 10       # real-time transit
  hsl_active_hours: [6, 22] # no HSL fetches outside these hours
  evaka_ttl_minutes: 1440   # daycare: once per day
  electricity_ttl_minutes: 720  # electricity: twice per day
```

Cron runs `main.py` every 10 minutes + `@reboot`; each module decides independently.

## HSL module specifics (data/hsl.py)

- Digitransit v2 GraphQL: `https://api.digitransit.fi/routing/v2/hsl/gtfs/v1`
- Variable types: `CoordinateValue!` for lat/lon, `OffsetDateTime!` for time
- startTime/endTime from API are **epoch milliseconds** (not ISO strings)
- Mode-specific walk time filtering:
  - BUS/TRAM/FERRY: `min_walk_bus` (default 3 min)
  - RAIL/SUBWAY: `min_walk_rail` (default 15 min)
- Each connection returns: departure, arrival, minutes_until, lines ("165 -> U"),
  walk_minutes, first_mode, first_stop, first_depart
- Outside `hsl_active_hours`: returns stale cache or empty result (no API call)
- `drop_past_departures()` recomputes `minutes_until` against `fetched_at` and
  drops connections that have already left. `main.py` applies it on every run
  (not just `--partial-only`), so a stale fallback (fetch failure) shows a
  correctly-decaying countdown instead of flashing the original, un-decayed
  minutes for up to one full cron cycle before the next per-minute partial
  tick empties it out.
- Render: first connection shown with FONT_MED + badge, rest compact

## eVaka module specifics (data/evaka.py)

- POST `/api/citizen/auth/weak-login` → session cookie saved to `cache/evaka_session.json`
- GET `/api/citizen/calendar-events?start=...&end=...`
- Auto re-login on 401/403
- The signed 90-day device cookie (`__Host-evaka-device-user-<sha256(personId)>`) MUST be
  persisted and replayed on every login — eVaka emails the user about a "login from a new
  browser" whenever a weak login arrives without it. Cookies are seeded with the real host
  as domain so Set-Cookie responses replace them instead of duplicating in the jar
  (duplicates make `dict(jar)` raise CookieConflictError).
- Events have separate `title` and `description` fields
- 14-day window
- `_apply_cutoff()`: called on both fresh and cached data — hides today's events
  after `_AFTERNOON_CUTOFF_HOUR = 18`

## Calendar module specifics (data/calendar.py)

- iCal links from config (no OAuth needed)
- 30-day window
- Date uses local timezone (`.astimezone().date()`), not UTC
- Filters out timed events that have already ended (uses DTEND)
- Returns up to 8 events, renderer shows ~3 that fit in the cell

## Forecast strip specifics

- Bottom strip renders `weather["forecast"]` — up to 7 coming days as columns
  (day+date, weather icon, high/low temps), drawn by `_draw_forecast()` in render.py
- Forecast data comes from the weather module (Open-Meteo `forecast_days: 8`,
  index 0 = today used by the SÄÄ cell, indices 1-7 = the strip)
- Day icons use the dominant daytime (08–20) hourly weather_code, NOT the daily
  code — Open-Meteo's daily code is the day's worst hour, so a trace shower
  would turn a sunny day into a rain icon. The worst-case daily code is kept
  when the day is genuinely wet (precipitation_sum ≥ 1 mm or ≥ 5 rain-hours).
- News module was removed in favor of this (data/news.py deleted Aug 2026)

## Known issues / TODO

- [ ] Caruna (pycaruna) returning null kWh — likely Caruna API change, check pycaruna updates
- [ ] Pi Zero 2 W with headers (WH version) would avoid needing to solder headers

## Git

Branch: main
Repo: https://github.com/JuhaniS/eInk
Last major commits:
- "Refine layout, fonts, and config" — Inter fonts, 3-col layout, news strip, evaka cutoff fix
- "Update README" — layout diagram, hardware info
