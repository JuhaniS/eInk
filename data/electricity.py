"""
electricity.py – Hakee eilisen sähkönkulutuksen Caruna Plus -tililtä.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

CACHE_FILE = Path("cache/electricity.json")


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
    ttl = config.get("cache", {}).get("electricity_ttl_minutes",
          config.get("cache", {}).get("ttl_minutes", 720))

    if use_cache and _cache_is_fresh(ttl):
        return _load_cache()

    caruna_cfg = config.get("caruna", {})
    username = caruna_cfg.get("username", "")
    password = caruna_cfg.get("password", "")

    if not username or not password:
        raise DataFetchError(
            "Caruna-tunnukset puuttuvat konfiguraatiosta (caruna.username / caruna.password)"
        )

    yesterday = date.today() - timedelta(days=1)
    window_start = yesterday - timedelta(days=6)  # 7-day window

    def _collect_entries(energy_list: list, into: dict):
        for e in energy_list:
            val = e.get("invoicedConsumption") or e.get("totalConsumption")
            if val is not None:
                into[e["timestamp"][:10]] = float(val)  # YYYY-MM-DD -> kWh

    try:
        from pycaruna import Authenticator, CarunaPlus, TimeSpan

        # Kirjaudu sisään – palauttaa {'token': '...', 'user': {'ownCustomerNumbers': [...]}}
        login_result = Authenticator(username, password).login()
        token = login_result["token"]
        customer_id = login_result["user"]["ownCustomerNumbers"][0]

        client = CarunaPlus(token)
        metering_points = client.get_assets(customer_id)

        if not metering_points:
            raise DataFetchError("Caruna: ei mittauspisteitä löydetty")

        asset_id = metering_points[0]["assetId"]

        # TimeSpan.MONTHLY palauttaa päiväkohtaisen kulutuksen kuukaudelta
        energy = client.get_energy(
            customer_id, asset_id,
            TimeSpan.MONTHLY,
            yesterday.year, yesterday.month, yesterday.day,
        )

        # Collect all days with data from current month
        all_data: dict[str, float] = {}
        _collect_entries(energy, all_data)

        # If 7-day window crosses a month boundary, fetch previous month too
        if window_start.month != yesterday.month:
            prev_energy = client.get_energy(
                customer_id, asset_id,
                TimeSpan.MONTHLY,
                window_start.year, window_start.month, window_start.day,
            )
            _collect_entries(prev_energy, all_data)

        # Build sorted list for the 7-day window
        w_start_str = window_start.isoformat()
        w_end_str   = yesterday.isoformat()
        daily_kwh = [
            {"date": d, "kwh": round(all_data[d], 2)}
            for d in sorted(all_data)
            if w_start_str <= d <= w_end_str
        ]

        # Most recent day with data (may lag 1-2 days behind yesterday)
        kwh = None
        actual_date = None
        if daily_kwh:
            latest = daily_kwh[-1]
            kwh = latest["kwh"]
            actual_date = latest["date"]

    except DataFetchError:
        raise
    except Exception as e:
        cached = _load_cache()
        if cached:
            cached["_stale"] = True
            return cached
        raise DataFetchError(f"Caruna-haku epäonnistui: {e}") from e

    data = {
        "yesterday_kwh":     round(kwh, 2) if kwh is not None else None,
        "yesterday_date":    actual_date or yesterday.isoformat(),
        "cost_estimate_eur": None,
        "fetched_at":        datetime.now().isoformat(timespec="seconds"),
        "daily_kwh":         daily_kwh,
    }

    kwh_price = caruna_cfg.get("kwh_price_eur")
    if kwh_price and kwh is not None:
        data["cost_estimate_eur"] = round(kwh * float(kwh_price), 2)

    _save_cache(data)
    return data
