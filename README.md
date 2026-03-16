# E-ink Dashboard

A home dashboard for a Waveshare 7.5" e-ink display (800×480), running on a Raspberry Pi. Displays weather, calendar events, electricity consumption, waste collection schedule, daycare events, and public transit departures.

![Dashboard layout](output/dashboard.png)

## Layout

```
┌─────────────────────┬─────────────────────┐
│  PÄIVÄKOTI          │  KALENTERI          │
│  Daycare events     │  Calendar events    │
├─────────────────────┼─────────────────────┤
│  SÄHKÖ              │  HSL                │
│  Electricity usage  │  Transit departures │
├─────────────────────┼─────────────────────┤
│  SÄÄ                │  JÄTTEET            │
│  Weather            │  Waste schedule     │
└─────────────────────┴─────────────────────┘
```

## Data sources

| Module | Source | Auth |
|---|---|---|
| Weather | [Open-Meteo](https://open-meteo.com/) | None |
| Calendar | Google Calendar iCal | Secret URL token |
| Electricity | Caruna via [pycaruna](https://github.com/tikonen/pycaruna) | Username + password |
| Waste | Manual schedule in config | None |
| Daycare | Espoo eVaka (`/api/citizen/auth/weak-login`) | Username + password |
| Transit | [HSL Digitransit v2 GraphQL](https://portal-api.digitransit.fi/) | API key |

## Setup

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

## Running

```bash
source venv/bin/activate

# Full run, open preview on macOS
python main.py --preview

# Force data refresh (skip cache)
python main.py --no-cache --preview

# Test a single module
python main.py --only weather
python main.py --only hsl --no-cache
```

## Raspberry Pi deployment

The display driver is selected automatically by platform:

- **macOS / Linux x86**: saves `output/dashboard.png`
- **Linux aarch64** (Raspberry Pi): drives the Waveshare 7.5" v2 e-paper display

Install the Waveshare Python library on the Pi, then run via cron:

```cron
*/10 * * * * cd /home/pi/eInk && venv/bin/python main.py >> cache/error.log 2>&1
```

Each module refreshes at its own pace regardless of how often cron runs — see `cache:` section in `config.yaml`.

## Project structure

```
eInk/
├── main.py              # Entry point, CLI args, module orchestration
├── render.py            # Pillow-based image renderer (800×480, grayscale)
├── config.yaml          # Your config (not committed)
├── config.example.yaml  # Template
├── data/
│   ├── weather.py       # Open-Meteo
│   ├── calendar.py      # iCal / Google Calendar
│   ├── electricity.py   # Caruna / pycaruna
│   ├── waste.py         # Manual waste schedule
│   ├── evaka.py         # Espoo daycare (eVaka)
│   └── hsl.py           # HSL Digitransit transit
├── display/
│   ├── simulator.py     # PNG output for development
│   └── epaper.py        # Waveshare 7.5" v2 driver
├── cache/               # JSON cache files (auto-generated)
└── output/              # Output image (auto-generated)
```

## Caching

Each module writes a JSON cache file under `cache/`. The default TTL is 55 minutes (slightly under one hour so a cron job running every hour always fetches fresh data). Transit data uses a 3-minute TTL. Stale cache is used as a fallback when an API call fails.
