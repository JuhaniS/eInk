# E-ink Dashboard

A home dashboard for a Waveshare 7.5" e-ink display (800×480), running on a Raspberry Pi. Displays weather, calendar events, news headlines, waste collection schedule, daycare events, and public transit departures.

## Layout

```
┌──────────────────┬──────────────────┬──────────────────┐
│  PÄIVÄKOTI       │  KALENTERI       │  SÄÄ + PVM/KELLO │
│  Daycare events  │  Calendar events │  Weather         │
├──────────────────┼──────────────────┼──────────────────┤
│  SÄHKÖ           │  HSL             │  JÄTEHUOLTO      │
│  Electricity     │  Transit         │  Waste schedule  │
├──────────────────┴──────────────────┴──────────────────┤
│  UUTISET  (full width, 2 headlines)                    │
└────────────────────────────────────────────────────────┘
```

## Hardware

| Part | Model | Notes |
|---|---|---|
| Display | Waveshare 7.5" e-Paper HAT V2 (800×480) | Black/white |
| Computer | Raspberry Pi Zero 2 W (or any Pi with 40-pin GPIO) | Needs pre-soldered headers |
| Power | 5V micro-USB charger, ≥1A | Standard phone charger works |

> **Important:** The Raspberry Pi Zero 2 W is sold both with and without GPIO headers.
> The Waveshare HAT has a female connector and requires **male pins** on the Pi.
> Make sure to buy the **"with headers" (WH) version**, or solder a 2×20 male header yourself.

## Data sources

| Module | Source | Auth |
|---|---|---|
| Weather | [Open-Meteo](https://open-meteo.com/) | None |
| Calendar | Google Calendar iCal | Secret URL token |
| News | YLE Uutiset RSS | None |
| Waste | Manual schedule in config | None |
| Daycare | Espoo eVaka (`/api/citizen/auth/weak-login`) | Username + password |
| Transit | [HSL Digitransit v2 GraphQL](https://portal-api.digitransit.fi/) | API key |

## Development setup (macOS)

### 1. Clone and create virtualenv

```bash
git clone <repo>
cd eInk
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your credentials and location. The file contains passwords and API keys — do not commit it.

Key settings:

```yaml
location:
  latitude: 60.1699
  longitude: 24.9384
  name: "Helsinki"

hsl:
  api_key: "your-key-from-portal-api.digitransit.fi"
  to_name: "Pasila"
  to_lat: 60.1985
  to_lon: 24.9323
  min_walk_bus: 3       # minutes to nearest bus stop
  min_walk_rail: 15     # minutes to nearest train station

waste:
  collections:
    - type: "Sekajäte"
      interval_weeks: 2
      next_date: "2026-03-25"
    - type: "Biojäte"
      interval_weeks: 4
      next_date: "2026-03-16"
```

### 3. Google Calendar iCal link

In Google Calendar: *Calendar settings → "Private address in iCal format"*. Add the URL to `config.yaml`:

```yaml
calendars:
  - name: "Oma"
    ical_url: "https://calendar.google.com/calendar/ical/.../basic.ics"
```

### 4. HSL API key

Register at [portal-api.digitransit.fi](https://portal-api.digitransit.fi/) and create a subscription for the Routing API. Add the key to `config.yaml`.

### 5. Run

```bash
source venv/bin/activate

# Full run, open preview on macOS
python main.py --preview

# Force data refresh (skip cache)
python main.py --no-cache --preview

# Test a single module
python main.py --only weather
python main.py --only hsl --no-cache

# Partial-refresh just the cells listed in config.partial_updates (no API calls).
# On macOS the simulator overlays the patched regions onto output/dashboard.png.
python main.py --partial-only

# Force a true full refresh instead of the default fast refresh
python main.py --full-refresh
```

## Raspberry Pi deployment

### 1. Flash SD card

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/):
- OS: Raspberry Pi OS Lite (64-bit)
- Enable SSH, set username/password, configure WiFi (country: FI)

### 2. Connect display

Attach the Waveshare HAT to the 40-pin GPIO header with the Pi powered off.

### 3. Enable SPI

```bash
ssh -t USER@HOSTNAME "sudo raspi-config nonint do_spi 0"
```

### 4. Install system dependencies

```bash
ssh -t USER@HOSTNAME "sudo apt install -y git python3-venv python3-pip swig liblgpio-dev"
```

### 5. Sync project files from Mac

```bash
./sync.sh
```

Or manually:
```bash
rsync -av --exclude venv --exclude cache --exclude output --exclude .git \
  /path/to/eInk/ USER@HOSTNAME:~/eInk/
```

### 6. Set up virtualenv and install Python dependencies

```bash
ssh USER@HOSTNAME "cd ~/eInk && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
```

The e-paper driver is `betterepd7in5` (on PyPI, pulled in by `requirements.txt`). It fixes the partial-update-after-sleep corruption the stock Waveshare driver exhibits and is significantly faster on the Pi Zero 2 W.

### 7. Create required directories

```bash
ssh USER@HOSTNAME "mkdir -p ~/eInk/cache ~/eInk/output"
```

### 8. Copy config

```bash
scp config.yaml USER@HOSTNAME:~/eInk/config.yaml
```

### 9. Test

```bash
ssh USER@HOSTNAME "cd ~/eInk && venv/bin/python main.py --no-cache"
```

### 10. Set up cron

The crontab is checked in at `cron/eink.crontab` and installed via `sync_cron.sh`. Three rhythms run on `flock`-protected mutually-exclusive minute slots so they can't collide on the SPI bus:

| Slot | Command | Purpose |
|---|---|---|
| Minutes 1–9, 11–19, …, 51–59 | `main.py --partial-only` | Partial-refresh cells in `config.partial_updates` (no API calls) |
| Minutes 10, 20, 30, 40, 50 | `main.py` | Fast refresh of the full dashboard |
| Minute 0 (every hour) + `@reboot` | `main.py --full-refresh` | True full refresh — clears ghosting, bootstraps partial baseline |

Edit `cron/eink.crontab` (update `juhani` to your username) then push:

```bash
./sync_cron.sh
```

The script preserves any other crontab entries on the Pi — it only replaces the block between `# >>> eink-managed >>>` markers.

### Sync changes from Mac

```bash
./sync.sh        # rsync project files (excludes venv, cache, output, .git)
./sync_cron.sh   # only when cron/eink.crontab changed
```

## Project structure

```
eInk/
├── main.py              # Entry point, CLI args, module orchestration
├── render.py            # Pillow-based image renderer (800×480, grayscale)
├── sync.sh              # rsync project files Mac → Pi
├── sync_cron.sh         # Push cron/eink.crontab to the Pi
├── config.yaml          # Your config (not committed)
├── config.example.yaml  # Template
├── cron/
│   └── eink.crontab     # Managed crontab block (installed via sync_cron.sh)
├── data/
│   ├── weather.py       # Open-Meteo
│   ├── calendar.py      # iCal / Google Calendar
│   ├── news.py          # YLE RSS feed
│   ├── electricity.py   # Caruna / pycaruna
│   ├── waste.py         # Manual waste schedule
│   ├── evaka.py         # Espoo daycare (eVaka)
│   └── hsl.py           # HSL Digitransit transit (incl. drop_past_departures filter)
├── display/
│   ├── simulator.py     # PNG output for macOS development
│   └── epaper.py        # Waveshare 7.5" V2 driver via betterepd7in5
├── fonts/               # Optional: place Inter-Regular.ttf + Inter-Bold.ttf here
├── cache/               # JSON cache files + cur_display.png partial baseline (auto-generated)
└── output/              # Output PNG (auto-generated, macOS only)
```

## Caching

Each module writes a JSON cache file under `cache/`. TTLs are configurable per module in `config.yaml`. Stale cache is used as a fallback when an API call fails — the dashboard always shows something even when offline.

```yaml
cache:
  ttl_minutes: 55           # weather, calendar
  hsl_ttl_minutes: 10       # real-time transit
  hsl_active_hours: [6, 22] # no HSL fetches outside these hours
  evaka_ttl_minutes: 1440   # daycare: once per day
  electricity_ttl_minutes: 720
```

## Partial updates

The cron's per-minute slot runs `main.py --partial-only`, which re-renders the dashboard from cache only (no API calls) and partial-refreshes the cells listed in config:

```yaml
partial_updates:
  clock: true   # ticks every minute
  hsl: true     # drops connections whose departure has passed
```

Available cells are defined in `render.py` as `PARTIAL_CELLS`. Each entry is `{region, data_key, filter}` where `filter` is an optional `module:function` that mutates the cell's data before render — the HSL cell uses `data.hsl:drop_past_departures` to remove connections where the recomputed `minutes_until ≤ 0`. New partial-eligible cells need an `x`-aligned region (multiples of 8) and an entry in the registry.

If `partial_updates` is missing or empty, `--partial-only` is a no-op.
