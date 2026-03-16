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
    ttl = config.get("cache", {}).get("ttl_minutes", 55)

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

        # energy on lista diktejä (yksi per päivä kuukaudelta).
        # Data voi tulla 1–2 päivän viiveellä – otetaan viimeisin päivä jolla on dataa.
        # kentät: timestamp (ISO, esim. "2026-03-14T00:00:00+02:00"), totalConsumption, invoicedConsumption
        kwh = None
        actual_date = None
        for entry in reversed(energy):
            val = entry.get("invoicedConsumption") or entry.get("totalConsumption")
            if val is not None:
                kwh = float(val)
                actual_date = entry.get("timestamp", "")[:10]  # YYYY-MM-DD
                break

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
    }

    kwh_price = caruna_cfg.get("kwh_price_eur")
    if kwh_price and kwh is not None:
        data["cost_estimate_eur"] = round(kwh * float(kwh_price), 2)

    _save_cache(data)
    return data
