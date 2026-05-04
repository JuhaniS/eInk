#!/usr/bin/env python3
"""
main.py – E-ink dashboard main program.
Fetches data, renders the image and displays it.
"""

import argparse
import logging
import platform
import sys
from pathlib import Path

import yaml

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("cache/error.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("dashboard")


# ── Configuration ────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        log.warning(
            "config.yaml not found. Copy config.example.yaml → config.yaml and fill in the details."
        )
        return {}
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── Display ───────────────────────────────────────────────────────────────────

def get_display():
    """Selects the correct display driver based on the runtime environment."""
    if platform.system() == "Linux" and platform.machine().startswith("aarch"):
        from display.epaper import EPaperDisplay
        return EPaperDisplay()
    else:
        from display.simulator import SimulatorDisplay
        return SimulatorDisplay()


# ── Data fetching ───────────────────────────────────────────────────────────

def fetch_module(name: str, config: dict, use_cache: bool) -> "dict | None":
    """Fetches data for a single module. Returns None if fetching fails."""
    try:
        if name == "weather":
            from data.weather import fetch
        elif name == "electricity":
            from data.electricity import fetch
        elif name == "waste":
            from data.waste import fetch
        elif name == "calendar":
            from data.calendar import fetch
        elif name == "evaka":
            from data.evaka import fetch
        elif name == "hsl":
            from data.hsl import fetch
        elif name == "news":
            from data.news import fetch
        else:
            log.error("Unknown module: %s", name)
            return None

        data = fetch(config, use_cache=use_cache)
        stale = data.get("_stale", False)
        status = " (stale cache)" if stale else ""
        log.info("✓ %s%s", name, status)
        return data

    except Exception as e:
        log.error("✗ %s failed: %s", name, e)
        return None


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="E-ink dashboard")
    parser.add_argument(
        "--preview", action="store_true",
        help="Open the rendered image in Preview (Mac only)"
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Force data refresh, ignore cache"
    )
    parser.add_argument(
        "--only",
        choices=["weather", "electricity", "waste", "calendar", "evaka", "hsl", "news"],
        help="Run only one module (for testing)"
    )
    parser.add_argument(
        "--full-refresh", action="store_true",
        help="Use a true full refresh instead of fast refresh (clears ghosting)"
    )
    parser.add_argument(
        "--partial-only", action="store_true",
        help="Partial-refresh all cells enabled in config.yaml's partial_updates"
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Configuration file (default: config.yaml)"
    )
    return parser.parse_args()


# ── Main program ───────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Ensure cache directory exists
    Path("cache").mkdir(exist_ok=True)

    config = load_config(args.config)
    use_cache = not args.no_cache

    display_cfg = config.get("display", {})
    width  = display_cfg.get("width",  800)
    height = display_cfg.get("height", 480)

    if args.only:
        # Run only one module and print the result
        data = fetch_module(args.only, config, use_cache)
        import json
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.partial_only:
        import importlib
        import json

        def _load_cache(name):
            path = Path(f"cache/{name}.json")
            if not path.exists():
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("cache/%s.json unreadable: %s", name, e)
                return None

        def _resolve_filter(spec: str):
            mod_name, fn_name = spec.split(":", 1)
            return getattr(importlib.import_module(mod_name), fn_name)

        from render import render, PARTIAL_CELLS

        enabled_cfg = config.get("partial_updates") or {}
        enabled = [name for name, on in enabled_cfg.items()
                   if on and name in PARTIAL_CELLS]
        if not enabled:
            log.warning("partial_updates: no cells enabled in config; nothing to do")
            return

        # Load all module caches once (no API calls)
        data = {n: _load_cache(n) for n in
                ("weather", "electricity", "waste", "calendar", "evaka", "hsl", "news")}

        # Apply per-cell filters (currently only HSL has one)
        for name in enabled:
            cell = PARTIAL_CELLS[name]
            if cell["filter"] and cell["data_key"]:
                fn = _resolve_filter(cell["filter"])
                data[cell["data_key"]] = fn(data[cell["data_key"]])

        image = render(
            weather=data["weather"], electricity=data["electricity"],
            waste=data["waste"], calendar=data["calendar"],
            daycare=data["evaka"], hsl=data["hsl"], news=data["news"],
        )

        regions = [(image.crop(PARTIAL_CELLS[n]["region"]),
                    PARTIAL_CELLS[n]["region"]) for n in enabled]

        log.info("Partial-refresh: %s", ", ".join(enabled))
        display = get_display()
        display.show_partials(regions, open_preview=args.preview)
        log.info("Done.")
        return

    # Fetch all modules independently
    log.info("Fetching data...")
    weather     = fetch_module("weather",     config, use_cache)
    electricity = fetch_module("electricity", config, use_cache)
    waste       = fetch_module("waste",       config, use_cache)
    calendar    = fetch_module("calendar",    config, use_cache)

    # eVaka – only fetch if configured
    daycare = None
    if config.get("evaka", {}).get("username"):
        daycare = fetch_module("evaka", config, use_cache)

    # HSL – only fetch if api_key is configured
    hsl = None
    if config.get("hsl", {}).get("api_key"):
        hsl = fetch_module("hsl", config, use_cache)

    # News – always fetch (uses public RSS, no credentials needed)
    news = fetch_module("news", config, use_cache)

    # Render image
    log.info("Rendering image...")
    from render import render
    image = render(
        weather=weather,
        electricity=electricity,
        waste=waste,
        calendar=calendar,
        daycare=daycare,
        hsl=hsl,
        news=news,
        width=width,
        height=height,
    )

    # Display image
    display = get_display()
    if args.full_refresh and hasattr(display, "show_full"):
        display.show_full(image, open_preview=args.preview)
    else:
        display.show(image, open_preview=args.preview)
    log.info("Done.")


if __name__ == "__main__":
    main()
