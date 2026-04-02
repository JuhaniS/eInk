import math
import platform
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Font loading ─────────────────────────────────────────────────────────────
#
# Place Inter font files in fonts/ for the best look on both macOS and Pi:
#   fonts/Inter-Regular.ttf  and  fonts/Inter-Bold.ttf
# Download from: https://github.com/rsms/inter/releases
#
# Fallback chain:  Inter → Futura (macOS) → Helvetica (macOS) → DejaVu (Linux)

_FONTS_DIR = Path(__file__).parent / "fonts"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates: list[tuple[str, int]] = []

    inter = _FONTS_DIR / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf")
    if inter.exists():
        candidates.append((str(inter), 0))

    if platform.system() == "Darwin":
        candidates += [
            ("/System/Library/Fonts/Supplemental/Futura.ttc", 4 if bold else 0),
            ("/Library/Fonts/Futura.ttc",                      4 if bold else 0),
            ("/System/Library/Fonts/Helvetica.ttc",            1 if bold else 0),
        ]
    else:
        base = "/usr/share/fonts/truetype/"
        candidates += [
            (base + ("inter/Inter-Bold.ttf" if bold else "inter/Inter-Regular.ttf"), 0),
            (base + ("dejavu/DejaVuSans-Bold.ttf" if bold else "dejavu/DejaVuSans.ttf"), 0),
        ]

    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size, index=index)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── Constants ────────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 800, 480
BG      = 255   # white
FG      = 0     # black
GRAY    = 80    # dark gray for secondary text
DIVIDER = 180   # light gray for grid lines

PAD = 12   # cell padding

# Grid: 3 equal columns, 2 rows, dark header
HEADER_H = 46
COL_W    = (WIDTH - 2) // 3     # ≈ 266 px  (2 px for dividers)
COL2_X   = COL_W + 1            # 267
COL3_X   = COL_W * 2 + 2        # 534
ROW_H    = (HEIGHT - HEADER_H) // 2  # 217 px
ROW2_Y   = HEADER_H + ROW_H          # 263

# Fonts
FONT_HUGE   = _load_font(52, bold=True)   # temperature, kWh value
FONT_LARGE  = _load_font(28, bold=True)   # HSL departure times
FONT_MED    = _load_font(20, bold=True)   # event titles, waste types
FONT_SMALL  = _load_font(16)              # detail rows
FONT_TINY   = _load_font(13)              # gray secondary text
FONT_LABEL  = _load_font(11)             # section labels
FONT_HEADER = _load_font(22, bold=True)   # header "KOTINÄKYMÄ"


# ── Drawing primitives ───────────────────────────────────────────────────────

def _text(draw: ImageDraw.Draw, xy, text: str, font, fill=FG, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _divider(draw: ImageDraw.Draw, x1: int, y: int, x2: int):
    draw.line([(x1, y), (x2, y)], fill=DIVIDER, width=1)


def _vertical_divider(draw: ImageDraw.Draw, x: int, y1: int, y2: int):
    draw.line([(x, y1), (x, y2)], fill=DIVIDER, width=1)


def _wrap_text(draw: ImageDraw.Draw, text: str, font, max_width: int) -> list[str]:
    """Word-wraps text to fit within max_width pixels. Returns a list of lines."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        w = draw.textlength(candidate, font=font)
        if w <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            # If a single word is wider than max_width, truncate it with ellipsis
            if draw.textlength(word, font=font) > max_width:
                while word and draw.textlength(word + "…", font=font) > max_width:
                    word = word[:-1]
                word = word + "…"
            current = word
    if current:
        lines.append(current)
    return lines


def _label(draw: ImageDraw.Draw, x: int, y: int, text: str, stale: bool = False) -> int:
    """Draws the small gray section label. Returns y-coordinate for content start."""
    _text(draw, (x + PAD, y + PAD), text, FONT_LABEL, fill=GRAY)
    if stale:
        _text(draw, (x + PAD + 5 + len(text) * 7, y + PAD), "*", FONT_LABEL, fill=GRAY)
    return y + PAD + 16   # label height (11px) + 5px gap


def _badge(draw: ImageDraw.Draw, x: int, y: int, text: str) -> int:
    """Black pill with white text. Returns the badge width."""
    bbox = draw.textbbox((0, 0), text, font=FONT_SMALL)
    bw = bbox[2] - bbox[0] + 18
    bh = bbox[3] - bbox[1] + 10
    draw.rectangle([x, y, x + bw, y + bh], fill=FG)
    draw.text((x + 9, y + 5), text, font=FONT_SMALL, fill=BG)
    return bw


_DAYS_FI = ["ma", "ti", "ke", "to", "pe", "la", "su"]


def _date_str(iso: str, weekday: bool = False) -> str:
    """'2026-03-22' → '22.3.'  (or 'su 22.3.' if weekday=True)"""
    try:
        d = date.fromisoformat(iso)
        s = f"{d.day}.{d.month}."
        if weekday:
            s = f"{_DAYS_FI[d.weekday()]} {s}"
        return s
    except ValueError:
        return iso[5:]


# ── Weather icons (geometric, drawn with Pillow) ─────────────────────────────

def _cloud(draw: ImageDraw.Draw, ox: int, oy: int, s: int, fill=FG):
    w, h = s, s
    draw.ellipse([ox + int(0.12*w), oy + int(0.52*h), ox + int(0.52*w), oy + int(0.82*h)], fill=fill)
    draw.ellipse([ox + int(0.25*w), oy + int(0.30*h), ox + int(0.70*w), oy + int(0.72*h)], fill=fill)
    draw.ellipse([ox + int(0.44*w), oy + int(0.46*h), ox + int(0.84*w), oy + int(0.78*h)], fill=fill)
    draw.rectangle([ox + int(0.12*w), oy + int(0.64*h), ox + int(0.84*w), oy + int(0.82*h)], fill=fill)


def _sun(draw: ImageDraw.Draw, cx: int, cy: int, r: int, rays: int = 8, fill=FG):
    ri, ro = int(r * 0.55), r
    draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=fill)
    for i in range(rays):
        angle = math.radians(i * 360 / rays)
        x1 = cx + int(math.cos(angle) * (ri + 3))
        y1 = cy + int(math.sin(angle) * (ri + 3))
        x2 = cx + int(math.cos(angle) * ro)
        y2 = cy + int(math.sin(angle) * ro)
        draw.line([x1, y1, x2, y2], fill=fill, width=2)


def _draw_weather_icon(draw: ImageDraw.Draw, ox: int, oy: int, icon_key: str, size: int = 44):
    s = size
    if icon_key in ("clear", "mainly_clear"):
        _sun(draw, ox + s // 2, oy + s // 2, s // 2 - 2)
    elif icon_key == "partly_cloudy":
        _sun(draw, ox + int(s * 0.32), oy + int(s * 0.30), int(s * 0.26))
        _cloud(draw, ox + int(s * 0.18), oy + int(s * 0.38), int(s * 0.82), fill=BG)
        _cloud(draw, ox + int(s * 0.18), oy + int(s * 0.38), int(s * 0.82))
    elif icon_key == "overcast":
        _cloud(draw, ox + int(s * 0.05), oy + int(s * 0.14), int(s * 0.90))
    elif icon_key == "fog":
        for i in range(4):
            fy = oy + int(s * (0.22 + i * 0.18))
            fw = int(s * (0.85 - i * 0.10))
            fx = ox + (s - fw) // 2
            draw.rectangle([fx, fy, fx + fw, fy + 3], fill=FG)
    elif icon_key in ("drizzle", "rain"):
        _cloud(draw, ox, oy, int(s * 0.80))
        dy0 = oy + int(s * 0.70)
        for i in range(5):
            dx = ox + int(s * (0.15 + i * 0.18))
            draw.line([dx, dy0, dx - 3, dy0 + int(s * 0.22)], fill=FG, width=2)
    elif icon_key == "snow":
        _cloud(draw, ox, oy, int(s * 0.80))
        dy = oy + int(s * 0.78)
        for i in range(4):
            cx2 = ox + int(s * (0.18 + i * 0.22))
            r2 = 3
            draw.ellipse([cx2 - r2, dy - r2, cx2 + r2, dy + r2], fill=FG)
    elif icon_key == "thunderstorm":
        _cloud(draw, ox, oy, int(s * 0.80))
        bx, by = ox + int(s * 0.40), oy + int(s * 0.68)
        bolt = [
            (bx,                   by),
            (bx - int(s * 0.14),   by + int(s * 0.18)),
            (bx + int(s * 0.04),   by + int(s * 0.16)),
            (bx - int(s * 0.12),   by + int(s * 0.34)),
            (bx + int(s * 0.14),   by + int(s * 0.12)),
            (bx,                   by + int(s * 0.13)),
        ]
        draw.polygon(bolt, fill=FG)
    else:
        _cloud(draw, ox + int(s * 0.10), oy + int(s * 0.20), int(s * 0.80))


# ── Section drawers ──────────────────────────────────────────────────────────
#
# Each drawer receives (draw, data, x, y, w, h) where (x, y) is the top-left
# corner of the cell, w is the usable column width, h is the row height.

def _draw_weather(draw: ImageDraw.Draw, data: dict | None,
                  x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "SÄÄ", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    temp     = data.get("temperature")
    icon_key = data.get("icon", "unknown")
    cond     = data.get("condition_fi") or data.get("condition", "")
    wind     = data.get("wind_speed")
    precip   = data.get("precipitation")
    feels    = data.get("feels_like")
    hi       = data.get("forecast_today_high")
    lo       = data.get("forecast_today_low")

    temp_str = f"{temp:.0f}°" if temp is not None else "-°"

    # Large temperature
    _text(draw, (x + PAD, cy), temp_str, FONT_HUGE)
    temp_bbox = draw.textbbox((0, 0), temp_str, font=FONT_HUGE)
    temp_w    = temp_bbox[2] - temp_bbox[0]

    # Icon to the right of temperature
    icon_x = x + PAD + temp_w + 8
    if icon_x + 44 < x + w:
        _draw_weather_icon(draw, icon_x, cy + 4, icon_key, size=44)

    detail_y = cy + 62
    _text(draw, (x + PAD, detail_y), cond, FONT_SMALL)

    parts = []
    if wind   is not None: parts.append(f"Tuuli {wind:.0f} m/s")
    if precip is not None: parts.append(f"Sade {precip:.1f} mm")
    if parts:
        _text(draw, (x + PAD, detail_y + 20), "  ·  ".join(parts), FONT_TINY, fill=GRAY)

    row3 = []
    if feels is not None:                   row3.append(f"Tuntuu {feels:.0f}°")
    if hi is not None and lo is not None:   row3.append(f"{lo:.0f}°-{hi:.0f}°")
    if row3:
        _text(draw, (x + PAD, detail_y + 38), "   ".join(row3), FONT_TINY, fill=GRAY)


def _draw_news(draw: ImageDraw.Draw, data: dict | None,
               x: int, y: int, w: int, h: int):
    label = (data.get("label", "UUTISET") if data else "UUTISET")
    cy    = _label(draw, x, y, label, stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    items = data.get("items", [])
    if not items:
        _text(draw, (x + PAD, cy), "Ei uutisia", FONT_TINY, fill=GRAY)
        return

    max_w   = w - 2 * PAD
    line_h1 = 18   # FONT_SMALL line height
    line_h2 = 15   # FONT_TINY line height
    gap     = 8    # gap between news items

    for item in items:
        title = item.get("title", "")
        desc  = item.get("description", "")

        title_lines = _wrap_text(draw, title, FONT_SMALL, max_w)[:2]
        desc_lines  = _wrap_text(draw, desc,  FONT_TINY,  max_w)[:2] if desc else []

        block_h = len(title_lines) * line_h1 + len(desc_lines) * line_h2 + gap
        if cy + block_h > y + h - PAD:
            break

        for line in title_lines:
            _text(draw, (x + PAD, cy), line, FONT_SMALL, fill=FG)
            cy += line_h1
        for line in desc_lines:
            _text(draw, (x + PAD, cy), line, FONT_TINY, fill=GRAY)
            cy += line_h2
        cy += gap


def _draw_electricity(draw: ImageDraw.Draw, data: dict | None,
                      x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "SÄHKÖ", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    kwh  = data.get("yesterday_kwh")
    dstr = data.get("yesterday_date", "")

    kwh_str = f"{kwh:.1f}" if kwh is not None else "-"
    _text(draw, (x + PAD, cy), kwh_str, FONT_HUGE)

    # "kWh" unit next to the number
    bbox = draw.textbbox((0, 0), kwh_str, font=FONT_HUGE)
    _text(draw, (x + PAD + bbox[2] - bbox[0] + 6, cy + 32), "kWh", FONT_SMALL, fill=GRAY)

    # Date label below
    if dstr:
        today = datetime.now().date()
        try:
            data_date = datetime.strptime(dstr, "%Y-%m-%d").date()
            delta = (today - data_date).days
            if delta == 1:
                label = f"eilen {data_date.day}.{data_date.month}."
            elif delta == 0:
                label = "tänään"
            else:
                label = f"{data_date.day}.{data_date.month}. ({delta} pv sitten)"
        except ValueError:
            label = dstr
        _text(draw, (x + PAD, cy + 62), label, FONT_TINY, fill=GRAY)


def _draw_calendar(draw: ImageDraw.Draw, data: dict | None,
                   x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "KALENTERI", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    events = data.get("events", [])
    if not events:
        _text(draw, (x + PAD, cy), "Ei tulevia tapahtumia", FONT_TINY, fill=GRAY)
        return

    row_h1  = 16   # date+time row
    row_h2  = 22   # title row
    row_gap = 10   # gap between events
    block_h = row_h1 + row_h2 + row_gap

    for ev in events:
        if cy + block_h > y + h - PAD:
            break
        dt  = _date_str(ev.get("date", ""), weekday=True)
        t   = ev.get("time")
        if t:
            dt += f"  {t[:5]}"
        title = ev.get("title", "")

        _text(draw, (x + PAD, cy),          dt,        FONT_TINY,  fill=GRAY)
        _text(draw, (x + PAD, cy + row_h1), title[:26], FONT_MED)
        cy += block_h


def _draw_hsl(draw: ImageDraw.Draw, data: dict | None,
              x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "HSL", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    connections = data.get("connections", [])
    if not connections:
        _text(draw, (x + PAD, cy), "Ei yhteyksiä", FONT_SMALL, fill=GRAY)
        return

    # First connection — large display
    first = connections[0]
    dep   = first.get("departure", "")
    arr   = first.get("arrival", "")
    mins  = first.get("minutes_until", 0)
    lines = first.get("lines", "")
    walk  = first.get("walk_minutes", 0)
    stop  = first.get("first_stop", "")
    fdep  = first.get("first_depart", "")

    time_str  = f"{dep}->{arr}" if arr else dep
    mins_str  = f"Lähtöön {mins} min" if mins > 0 else "Lähdettävä nyt"
    route_str = (f"{walk}min -> {lines}" if walk else lines).strip()
    stop_str  = f"{stop} {fdep}".strip() if stop else ""

    _text(draw, (x + PAD, cy), time_str, FONT_LARGE)
    cy += 34

    _text(draw, (x + PAD, cy), route_str, FONT_TINY, fill=GRAY)
    if stop_str:
        _text(draw, (x + w - PAD, cy), stop_str, FONT_TINY, fill=GRAY, anchor="ra")
    cy += 18

    # Minutes-until badge
    _badge(draw, x + PAD, cy, mins_str)
    cy += 30

    # Remaining connections — compact two-row style
    row_h1  = 18
    row_h2  = 15
    row_gap = 8
    block_h = row_h1 + row_h2 + row_gap

    for conn in connections[1:]:
        if cy + block_h > y + h - PAD:
            break
        dep2   = conn.get("departure", "")
        arr2   = conn.get("arrival", "")
        mins2  = conn.get("minutes_until", 0)
        lines2 = conn.get("lines", "")
        walk2  = conn.get("walk_minutes", 0)
        stop2  = conn.get("first_stop", "")
        fdep2  = conn.get("first_depart", "")

        t2     = f"{dep2}->{arr2}" if arr2 else dep2
        m2     = f"{mins2} min" if mins2 > 0 else "Nyt"
        r2     = (f"{walk2}min -> {lines2}" if walk2 else lines2).strip()
        s2     = f"{stop2} {fdep2}".strip() if stop2 else ""

        _text(draw, (x + PAD,     cy), t2, FONT_SMALL)
        _text(draw, (x + w - PAD, cy), m2, FONT_SMALL, anchor="ra")
        cy += row_h1
        _text(draw, (x + PAD,     cy), r2, FONT_TINY, fill=GRAY)
        if s2:
            _text(draw, (x + w - PAD, cy), s2, FONT_TINY, fill=GRAY, anchor="ra")
        cy += row_h2 + row_gap


def _draw_daycare(draw: ImageDraw.Draw, data: dict | None,
                  x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "PÄIVÄKOTI", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    events = data.get("events", [])
    if not events:
        _text(draw, (x + PAD, cy), "Ei tulevia tapahtumia", FONT_TINY, fill=GRAY)
        return

    row_h1  = 15   # date row
    row_h2  = 20   # title row (bold)
    row_h3  = 15   # description row
    row_gap = 8
    block_h = row_h1 + row_h2 + row_h3 + row_gap

    for ev in events:
        if cy + block_h > y + h - PAD:
            break
        dt    = _date_str(ev.get("date", ""), weekday=True)
        title = ev.get("title", "")
        desc  = ev.get("description", "")

        _text(draw, (x + PAD, cy),                    dt,         FONT_TINY, fill=GRAY)
        _text(draw, (x + PAD, cy + row_h1),           title[:28], FONT_MED)
        if desc:
            _text(draw, (x + PAD, cy + row_h1 + row_h2), desc[:36], FONT_TINY, fill=GRAY)
        cy += block_h


def _draw_waste(draw: ImageDraw.Draw, data: dict | None,
                x: int, y: int, w: int, h: int):
    cy = _label(draw, x, y, "JÄTEHUOLTO", stale=bool(data and data.get("_stale")))

    if not data:
        _text(draw, (x + PAD, cy), "Ei saatavilla", FONT_SMALL, fill=GRAY)
        return

    collections = data.get("next_collections", [])
    if not collections:
        _text(draw, (x + PAD, cy), "Ei tietoja", FONT_TINY, fill=GRAY)
        return

    line_h = 40
    for col in collections[:4]:
        if cy + line_h > y + h - PAD:
            break
        ctype = col.get("type", "")
        days  = col.get("days_until")

        if days == 0:
            days_str = "Tänään"
        elif days == 1:
            days_str = "Huomenna"
        elif days is not None:
            days_str = f"{days} pv"
        else:
            days_str = col.get("date", "")[5:]

        _text(draw, (x + PAD,     cy), ctype,    FONT_MED)
        _text(draw, (x + w - PAD, cy + 2), days_str, FONT_SMALL, fill=GRAY, anchor="ra")
        cy += line_h


# ── Header ───────────────────────────────────────────────────────────────────

def _draw_header(draw: ImageDraw.Draw, width: int):
    """Full-width black header bar with title and date/time."""
    draw.rectangle([0, 0, width, HEADER_H - 1], fill=FG)

    now      = datetime.now()
    day_abbr = _DAYS_FI[now.weekday()]
    date_str = f"{day_abbr} {now.day}.{now.month}.{now.year}"
    time_str = now.strftime("%H:%M")

    mid_y = HEADER_H // 2
    _text(draw, (PAD,         mid_y), "KOTINÄKYMÄ", FONT_HEADER, fill=BG, anchor="lm")
    _text(draw, (width - PAD, mid_y), date_str,     FONT_SMALL,  fill=BG, anchor="rm")
    # Time slightly left of the date — measure date width first
    date_bbox = draw.textbbox((0, 0), date_str, font=FONT_SMALL)
    date_w    = date_bbox[2] - date_bbox[0]
    _text(draw, (width - PAD - date_w - 14, mid_y), time_str, FONT_SMALL, fill=BG, anchor="rm")


# ── Main render function ─────────────────────────────────────────────────────

def render(
    weather:     dict | None = None,
    electricity: dict | None = None,
    waste:       dict | None = None,
    calendar:    dict | None = None,
    daycare:     dict | None = None,
    hsl:         dict | None = None,
    news:        dict | None = None,
    width:  int = WIDTH,
    height: int = HEIGHT,
) -> Image.Image:
    """
    Renders the dashboard and returns a PIL Image (mode L, 800×480).

    Layout — dark header + 3-column × 2-row grid:

      ┌──────────────────────────────────────────────────────────┐  HEADER (46px)
      │  KOTINÄKYMÄ                              ke 19.3.2026   │
      ├──────────────────┬──────────────────┬────────────────────┤
      │  PÄIVÄKOTI       │  KALENTERI       │  SÄÄ              │  ROW 1 (217px)
      ├──────────────────┼──────────────────┼────────────────────┤
      │  UUTISET         │  HSL             │  JÄTEHUOLTO       │  ROW 2 (217px)
      └──────────────────┴──────────────────┴────────────────────┘
       COL_W ≈ 266 px each
    """
    img  = Image.new("L", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Header
    _draw_header(draw, width)

    # Grid lines
    _vertical_divider(draw, COL_W,       HEADER_H, height)
    _vertical_divider(draw, COL_W * 2 + 1, HEADER_H, height)
    _divider(draw, 0, ROW2_Y, width)

    # Row 1: daycare | calendar | weather
    _draw_daycare (draw, daycare,  0,      HEADER_H, COL_W,          ROW_H)
    _draw_calendar(draw, calendar, COL2_X, HEADER_H, COL_W,          ROW_H)
    _draw_weather (draw, weather,  COL3_X, HEADER_H, width - COL3_X, ROW_H)

    # Row 2: news | hsl | waste
    _draw_news (draw, news,  0,      ROW2_Y, COL_W,          ROW_H)
    _draw_hsl  (draw, hsl,   COL2_X, ROW2_Y, COL_W,          ROW_H)
    _draw_waste(draw, waste,  COL3_X, ROW2_Y, width - COL3_X, ROW_H)

    return img
