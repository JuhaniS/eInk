import math
import platform
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Font paths ──────────────────────────────────────────────────────────────

# Place Inter font files in fonts/ directory for the best look:
#   fonts/Inter-Regular.ttf  and  fonts/Inter-Bold.ttf
# Download from: https://github.com/rsms/inter/releases
_FONTS_DIR = Path(__file__).parent / "fonts"

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates: list[tuple[str, int]] = []

    # 1. Bundled Inter (works on both macOS and Raspberry Pi)
    inter = _FONTS_DIR / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf")
    if inter.exists():
        candidates.append((str(inter), 0))

    # 2. Platform system fonts
    if platform.system() == "Darwin":
        candidates += [
            ("/System/Library/Fonts/Supplemental/Futura.ttc", 4 if bold else 0),
            ("/Library/Fonts/Futura.ttc",                      4 if bold else 0),
            ("/System/Library/Fonts/Helvetica.ttc",            1 if bold else 0),
        ]
    else:
        base = "/usr/share/fonts/truetype/"
        candidates += [
            (base + "inter/Inter-Bold.ttf"   if bold else base + "inter/Inter-Regular.ttf", 0),
            (base + "dejavu/DejaVuSans-Bold.ttf" if bold else base + "dejavu/DejaVuSans.ttf", 0),
        ]

    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size, index=index)
        except (OSError, IOError):
            continue

    return ImageFont.load_default()


# ── Constants ──────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 800, 480
BG = 255       # white
FG = 0         # black
GRAY = 160     # gray (used during development only)
DIVIDER = 100  # gray color for divider lines

PAD = 12       # general padding
LEFT_W = 380   # left column width
RIGHT_X = LEFT_W + 1  # right column start x

FONT_HUGE  = _load_font(52, bold=True)
FONT_LARGE = _load_font(26, bold=True)
FONT_MED   = _load_font(20)
FONT_SMALL = _load_font(16)
FONT_TINY  = _load_font(13)

# ── Weather icons (geometric, drawn with Pillow) ───────────────────────────

def _cloud(draw: ImageDraw.Draw, ox: int, oy: int, s: int, fill=FG):
    """Cloud base: filled cloud positioned within the (ox, oy) – (ox+s, oy+s) box."""
    # Three ellipses forming the cloud silhouette
    w, h = s, s
    draw.ellipse([ox + int(0.12*w), oy + int(0.52*h), ox + int(0.52*w), oy + int(0.82*h)], fill=fill)
    draw.ellipse([ox + int(0.25*w), oy + int(0.30*h), ox + int(0.70*w), oy + int(0.72*h)], fill=fill)
    draw.ellipse([ox + int(0.44*w), oy + int(0.46*h), ox + int(0.84*w), oy + int(0.78*h)], fill=fill)
    draw.rectangle([ox + int(0.12*w), oy + int(0.64*h), ox + int(0.84*w), oy + int(0.82*h)], fill=fill)


def _sun(draw: ImageDraw.Draw, cx: int, cy: int, r: int, rays: int = 8, fill=FG):
    """Sun: circle + rays."""
    ri, ro = int(r * 0.55), r
    draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=fill)
    for i in range(rays):
        angle = math.radians(i * 360 / rays)
        x1 = cx + int(math.cos(angle) * (ri + 3))
        y1 = cy + int(math.sin(angle) * (ri + 3))
        x2 = cx + int(math.cos(angle) * ro)
        y2 = cy + int(math.sin(angle) * ro)
        draw.line([x1, y1, x2, y2], fill=fill, width=2)


def _draw_weather_icon(draw: ImageDraw.Draw, right_x: int, top_y: int, icon_key: str, size: int = 56):
    """Draws the weather icon so that its top-right corner is at (right_x, top_y)."""
    ox = right_x - size
    oy = top_y
    s  = size

    if icon_key in ("clear", "mainly_clear"):
        _sun(draw, ox + s // 2, oy + s // 2, s // 2 - 2)

    elif icon_key == "partly_cloudy":
        # Small sun in the upper left, cloud in front
        _sun(draw, ox + int(s * 0.32), oy + int(s * 0.30), int(s * 0.26))
        _cloud(draw, ox + int(s * 0.18), oy + int(s * 0.38), int(s * 0.82), fill=BG)
        _cloud(draw, ox + int(s * 0.18), oy + int(s * 0.38), int(s * 0.82))

    elif icon_key == "overcast":
        _cloud(draw, ox + int(s * 0.05), oy + int(s * 0.14), int(s * 0.90))

    elif icon_key == "fog":
        for i in range(4):
            y = oy + int(s * (0.22 + i * 0.18))
            w = int(s * (0.85 - i * 0.10))
            x = ox + (s - w) // 2
            draw.rectangle([x, y, x + w, y + 3], fill=FG)

    elif icon_key in ("drizzle", "rain"):
        _cloud(draw, ox, oy, int(s * 0.80))
        drop_y0 = oy + int(s * 0.70)
        for i in range(5):
            x = ox + int(s * (0.15 + i * 0.18))
            draw.line([x, drop_y0, x - 3, drop_y0 + int(s * 0.22)], fill=FG, width=2)

    elif icon_key == "snow":
        _cloud(draw, ox, oy, int(s * 0.80))
        dot_y = oy + int(s * 0.78)
        for i in range(4):
            cx2 = ox + int(s * (0.18 + i * 0.22))
            r2 = 3
            draw.ellipse([cx2 - r2, dot_y - r2, cx2 + r2, dot_y + r2], fill=FG)

    elif icon_key == "thunderstorm":
        _cloud(draw, ox, oy, int(s * 0.80))
        # Lightning bolt
        bx, by = ox + int(s * 0.40), oy + int(s * 0.68)
        bolt = [
            (bx,          by),
            (bx - int(s * 0.14), by + int(s * 0.18)),
            (bx + int(s * 0.04), by + int(s * 0.16)),
            (bx - int(s * 0.12), by + int(s * 0.34)),
            (bx + int(s * 0.14), by + int(s * 0.12)),
            (bx + int(s * 0.00), by + int(s * 0.13)),
        ]
        draw.polygon(bolt, fill=FG)

    else:
        # Unknown – small cloud
        _cloud(draw, ox + int(s * 0.10), oy + int(s * 0.20), int(s * 0.80))


# ── Helper functions ──────────────────────────────────────────────────────────

def _divider(draw: ImageDraw.Draw, x1: int, y: int, x2: int):
    draw.line([(x1, y), (x2, y)], fill=DIVIDER, width=1)


def _vertical_divider(draw: ImageDraw.Draw, x: int, y1: int, y2: int):
    draw.line([(x, y1), (x, y2)], fill=DIVIDER, width=1)


def _text(draw: ImageDraw.Draw, xy, text: str, font, fill=FG, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _stale_mark(draw: ImageDraw.Draw, x: int, y: int):
    """Small '*' if the data is stale."""
    _text(draw, (x, y), "*", FONT_TINY, fill=GRAY)


# ── Section drawers ────────────────────────────────────────────────────────

def _draw_weather_datetime(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int, h: int):
    """Weather + date & time in the same panel (bottom-left)."""
    title_y = y + PAD
    _text(draw, (x + PAD, title_y), "SÄÄ", FONT_LARGE)
    if data and data.get("_stale"):
        _stale_mark(draw, x + PAD + 60, title_y)

    # Date & time in the top-right corner
    now = datetime.now()
    _text(draw, (x + w - PAD, title_y + 2),  now.strftime("%-d.%-m.%Y"), FONT_SMALL, fill=GRAY, anchor="ra")
    _text(draw, (x + w - PAD, title_y + 18), now.strftime("%H:%M"),       FONT_MED,   anchor="ra")

    if not data:
        _text(draw, (x + PAD, title_y + 50), "Ei saatavilla", FONT_MED, fill=GRAY)
        return

    temp     = data.get("temperature")
    icon_key = data.get("icon", "unknown")
    temp_str = f"{temp:.0f}°" if temp is not None else "—°"
    temp_y   = title_y + 46

    _text(draw, (x + PAD, temp_y), temp_str, FONT_HUGE)
    _draw_weather_icon(draw, x + PAD + 130, temp_y + 4, icon_key, size=46)

    cx = x + PAD + 185
    cond = data.get("condition_fi") or data.get("condition", "")
    _text(draw, (cx, temp_y + 4), cond, FONT_SMALL)

    wind   = data.get("wind_speed")
    precip = data.get("precipitation")
    feels  = data.get("feels_like")
    hi     = data.get("forecast_today_high")
    lo     = data.get("forecast_today_low")

    parts = []
    if wind   is not None: parts.append(f"Tuuli {wind:.0f} m/s")
    if precip is not None: parts.append(f"Sade {precip:.1f} mm")
    if parts:
        _text(draw, (cx, temp_y + 22), "  ·  ".join(parts), FONT_TINY)

    row3 = []
    if feels is not None:                     row3.append(f"Tuntuu {feels:.0f}°")
    if hi is not None and lo is not None:     row3.append(f"{lo:.0f}°–{hi:.0f}°")
    if row3:
        _text(draw, (cx, temp_y + 38), "   ".join(row3), FONT_TINY, fill=GRAY)



def _draw_electricity(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int):
    title_y = y + PAD
    _text(draw, (x + PAD, title_y), "SÄHKÖ", FONT_LARGE)
    if data and data.get("_stale"):
        _stale_mark(draw, x + PAD + 90, title_y)

    if not data:
        _text(draw, (x + PAD, title_y + 34), "Ei saatavilla", FONT_MED, fill=GRAY)
        return

    kwh = data.get("yesterday_kwh")
    date = data.get("yesterday_date", "")
    cost = data.get("cost_estimate_eur")

    kwh_str = f"{kwh:.1f} kWh" if kwh is not None else "— kWh"
    _text(draw, (x + PAD, title_y + 34), kwh_str, FONT_LARGE)

    if date:
        today = datetime.now().date()
        try:
            data_date = datetime.strptime(date, "%Y-%m-%d").date()
            delta = (today - data_date).days
            if delta == 1:
                label = f"Eilen ({data_date.day}.{data_date.month}.)"
            elif delta == 0:
                label = "Tänään"
            else:
                label = f"{data_date.day}.{data_date.month}. ({delta} pv sitten)"
        except ValueError:
            label = date
        _text(draw, (x + PAD, title_y + 64), label, FONT_SMALL, fill=GRAY)
    if cost is not None:
        _text(draw, (x + PAD, title_y + 82), f"≈ {cost:.2f} €", FONT_SMALL)


def _draw_datetime(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int):
    now = datetime.now()
    date_str = now.strftime("%-d.%-m.%Y")
    time_str = now.strftime("%H:%M")

    cy = y + h // 2
    _text(draw, (x + PAD, cy - 18), date_str, FONT_MED)
    _text(draw, (x + PAD, cy + 4), time_str, FONT_SMALL, fill=GRAY)


def _draw_calendar(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int, h: int):
    title_y = y + PAD
    _text(draw, (x + PAD, title_y), "KALENTERI", FONT_LARGE)
    if data and data.get("_stale"):
        _stale_mark(draw, x + PAD + 140, title_y)

    if not data:
        _text(draw, (x + PAD, title_y + 34), "Ei saatavilla", FONT_MED, fill=GRAY)
        return

    events = data.get("events", [])
    if not events:
        _text(draw, (x + PAD, title_y + 38), "Ei tulevia tapahtumia", FONT_SMALL, fill=GRAY)
        return

    event_y = title_y + 38
    row_h1  = 20   # title row height
    row_h2  = 17   # date/time row height
    row_gap = 7
    block_h = row_h1 + row_h2 + row_gap
    # Collect visible events
    visible = []
    tmp_y = event_y
    for ev in events:
        if tmp_y + block_h > y + h - 10:
            break
        visible.append(ev)
        tmp_y += block_h
    for i, ev in enumerate(visible):
        ev_date = ev.get("date", "")
        time    = ev.get("time")
        title   = ev.get("title", "")

        try:
            from datetime import date as _d
            d = _d.fromisoformat(ev_date)
            dt_str = f"{d.day}.{d.month}."
        except ValueError:
            dt_str = ev_date[5:]
        if time:
            dt_str += f" {time[:5]}"

        _text(draw, (x + PAD, event_y), title[:32], FONT_SMALL)
        _text(draw, (x + PAD, event_y + row_h1), dt_str, FONT_TINY, fill=GRAY)

        event_y += block_h


def _draw_hsl(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int, h: int):
    title_y = y + PAD
    _text(draw, (x + PAD, title_y), "HSL", FONT_LARGE)
    if data and data.get("_stale"):
        _stale_mark(draw, x + PAD + 200, title_y)

    if not data:
        _text(draw, (x + PAD, title_y + 38), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    connections = data.get("connections", [])
    if not connections:
        _text(draw, (x + PAD, title_y + 38), "Ei yhteyksiä", FONT_SMALL, fill=GRAY)
        return

    row_y   = title_y + 38
    row_h1  = 22   # top row height (time + minutes)
    row_h2  = 18   # bottom row height (walk + lines + stop)
    row_gap = 8    # gap to next connection
    block_h = row_h1 + row_h2 + row_gap
    # Collect visible connections
    visible = []
    tmp_y = row_y
    for conn in connections:
        if tmp_y + block_h > y + h - 10:
            break
        visible.append(conn)
        tmp_y += block_h
    for i, conn in enumerate(visible):
        dep          = conn.get("departure", "")
        arr          = conn.get("arrival", "")
        mins         = conn.get("minutes_until", 0)
        lines        = conn.get("lines", "")
        walk         = conn.get("walk_minutes", 0)
        first_stop   = conn.get("first_stop", "")
        first_depart = conn.get("first_depart", "")

        # Top row: "13:35->14:16" on the left, "19 min" on the right
        time_str = f"{dep}->{arr}" if arr else dep
        mins_str = f"{mins} min" if mins > 0 else "Nyt"
        _text(draw, (x + PAD,     row_y), time_str, FONT_SMALL)
        _text(draw, (x + w - PAD, row_y), mins_str, FONT_SMALL, anchor="ra")

        # Bottom row: "4min -> 165 -> U" on the left, "Satulamaakarintie 13:39" on the right
        route_str = f"{walk}min -> {lines}" if walk else lines
        stop_str  = f"{first_stop} {first_depart}".strip() if first_stop else ""
        _text(draw, (x + PAD,     row_y + row_h1), route_str, FONT_TINY, fill=GRAY)
        if stop_str:
            _text(draw, (x + w - PAD, row_y + row_h1), stop_str, FONT_TINY, fill=GRAY, anchor="ra")

        row_y += block_h


def _draw_daycare(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int, h: int):
    title_y = y + PAD
    _text(draw, (x + PAD, title_y), "PÄIVÄKOTI", FONT_LARGE)
    if data and data.get("_stale"):
        _stale_mark(draw, x + PAD + 130, title_y)

    if not data:
        _text(draw, (x + PAD, title_y + 30), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    events = data.get("events", [])
    if not events:
        _text(draw, (x + PAD, title_y + 38), "Ei tulevia tapahtumia", FONT_SMALL, fill=GRAY)
        return

    event_y = title_y + 38
    row_h1  = 22   # title row height
    row_h2  = 18   # description row height
    row_gap = 8    # gap to next event
    block_h = row_h1 + row_h2 + row_gap
    # Collect visible events
    visible = []
    tmp_y = event_y
    for ev in events:
        if tmp_y + block_h > y + h - 10:
            break
        visible.append(ev)
        tmp_y += block_h
    for i, ev in enumerate(visible):
        ev_date = ev.get("date", "")
        title   = ev.get("title", "")
        desc    = ev.get("description", "")

        try:
            from datetime import date as _d
            d = _d.fromisoformat(ev_date)
            dt_str = f"{d.day}.{d.month}."
        except ValueError:
            dt_str = ev_date[5:]

        # Top row: date in gray on the left, title in black
        _text(draw, (x + PAD,      event_y), dt_str,     FONT_SMALL, fill=GRAY)
        _text(draw, (x + PAD + 50, event_y), title[:30], FONT_SMALL)

        # Bottom row: description in gray
        if desc:
            _text(draw, (x + PAD, event_y + row_h1), desc[:42], FONT_TINY, fill=GRAY)

        event_y += block_h


def _draw_waste(draw: ImageDraw.Draw, data: dict | None, x: int, y: int, w: int, h: int):
    title_y = y + PAD
    _text(draw, (x + PAD, title_y), "JÄTEHUOLTO", FONT_LARGE)
    if data and data.get("_stale"):
        _stale_mark(draw, x + PAD + 140, title_y)

    if not data:
        _text(draw, (x + PAD, title_y + 38), "Ei saatavilla", FONT_MED, fill=GRAY)
        return

    collections = data.get("next_collections", [])
    if not collections:
        _text(draw, (x + PAD, title_y + 38), "Ei tietoja", FONT_SMALL, fill=GRAY)
        return

    item_y = title_y + 38
    line_h = 38
    for col in collections[:4]:
        if item_y + line_h > y + h - PAD:
            break
        ctype = col.get("type", "")
        days = col.get("days_until")
        date = col.get("date", "")

        date_short = date[5:] if len(date) >= 7 else date  # YYYY-MM-DD → MM-DD
        if days == 0:
            days_str = "Tänään"
        elif days == 1:
            days_str = "Huomenna"
        elif days is not None:
            days_str = f"{days} pv"
        else:
            days_str = date_short

        _text(draw, (x + PAD, item_y), ctype, FONT_MED)
        _text(draw, (x + w - PAD, item_y + 2), days_str, FONT_SMALL, fill=GRAY, anchor="ra")
        item_y += line_h


# ── Main function ───────────────────────────────────────────────────────────

def render(
    weather: dict | None = None,
    electricity: dict | None = None,
    waste: dict | None = None,
    calendar: dict | None = None,
    daycare: dict | None = None,
    hsl: dict | None = None,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> Image.Image:
    """
    Renders the dashboard and returns a PIL Image object.
    Each data parameter can be None (section shows 'Ei saatavilla').

    Layout (3 rows × 2 columns):
      ┌─────────────────────┬───────────────────────┐
      │  PÄIVÄKOTI          │  KALENTERI            │
      ├─────────────────────┼───────────────────────┤
      │  SÄHKÖ              │  HSL                  │
      ├─────────────────────┼───────────────────────┤
      │  SÄÄ + PVM/KELLO    │  JÄTTEET              │
      └─────────────────────┴───────────────────────┘
    """
    img  = Image.new("L", (width, height), BG)
    draw = ImageDraw.Draw(img)

    ROW1_H = 162   # daycare / calendar
    ROW2_H = 148   # electricity / HSL
    ROW3_H = height - ROW1_H - ROW2_H  # weather+date / waste  (170)
    RW     = width - RIGHT_X           # right column width

    # Vertical divider
    _vertical_divider(draw, LEFT_W, 0, height)

    # Horizontal dividers (full width)
    _divider(draw, 0, ROW1_H, width)
    _divider(draw, 0, ROW1_H + ROW2_H, width)

    # Left column
    _draw_daycare    (draw, daycare,     0,       0,              LEFT_W, ROW1_H)
    _draw_electricity(draw, electricity, 0,       ROW1_H,         LEFT_W)
    _draw_weather_datetime(draw, weather, 0, ROW1_H + ROW2_H, LEFT_W, ROW3_H)

    # Right column
    _draw_calendar(draw, calendar, RIGHT_X, 0,              RW, ROW1_H)
    _draw_hsl     (draw, hsl,      RIGHT_X, ROW1_H,         RW, ROW2_H)
    _draw_waste   (draw, waste,    RIGHT_X, ROW1_H + ROW2_H, RW, ROW3_H)

    return img
