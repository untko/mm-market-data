"""Myanmar pump prices from Max Energy's daily station-price page."""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta, timezone

import requests

from . import common

FUEL_PRICES_URL = "https://www.maxenergy.com.mm/fuel-prices-list/"
FUEL_API_TIMEOUT = 90
FUEL_API_ATTEMPTS = 5
YANGON_TZ = timezone(timedelta(hours=6, minutes=30))

# These stations are deliberately omitted by the Max Energy page's JavaScript.
EXCLUDED_STATION_IDS = {"22", "24"}

_API_CONFIG_RE = re.compile(
    r"url:\s*['\"](?P<url>https://app\.maxenergy\.com\.mm/[^'\"]*/Price/GetPriceList/?)['\"]"
    r".{0,800}?['\"]apikey['\"]\s*:\s*['\"](?P<key>[^'\"]+)['\"]",
    re.DOTALL,
)


def _page_api_config(html: str) -> tuple[str, str]:
    match = _API_CONFIG_RE.search(html)
    if not match:
        raise RuntimeError("Max Energy price API configuration not found in page")
    return match.group("url"), match.group("key")


def _grade_prices(rows: list[dict], grade: str) -> list[float]:
    latest_by_station = {}
    for row in rows:
        station_id = str(row.get("stationid"))
        if row.get("gradename") == grade and station_id not in EXCLUDED_STATION_IDS:
            # The API orders intraday changes from oldest to newest, as assumed by
            # the page's own JavaScript when it hides superseded duplicate rows.
            latest_by_station[station_id] = row
    return [
        float(row["price"])
        for row in latest_by_station.values()
        if float(row.get("price") or 0) > 0
    ]


def _as_of(rows: list[dict]) -> str | None:
    dates = []
    for row in rows:
        value = row.get("effectivedate") or row.get("pretransactiondate")
        if not value:
            continue
        try:
            dates.append(datetime.strptime(value, "%m/%d/%y %I:%M:%S %p").date())
        except ValueError:
            continue
    return max(dates).isoformat() if dates else None


def fetch(
    usd_mmk_market: float | None = None,
    *,
    http=requests,
    now: datetime | None = None,
) -> dict:
    errors = []
    fuel = None
    try:
        page = http.get(FUEL_PRICES_URL, headers=common.UA, timeout=common.TIMEOUT)
        page.raise_for_status()
        api_url, api_key = _page_api_config(page.text)

        query_time = now or datetime.now(YANGON_TZ)
        if query_time.tzinfo is not None:
            query_time = query_time.astimezone(YANGON_TZ)
        query_date = query_time.strftime("%Y-%m-%d")
        payload = {
            "apikey": api_key,
            "fromdate": f"{query_date} 00:00:00",
            "todate": f"{query_date} 23:59:59",
        }
        for attempt in range(1, FUEL_API_ATTEMPTS + 1):
            try:
                response = http.post(
                    api_url,
                    json=payload,
                    headers={**common.UA, "Content-Type": "application/json"},
                    timeout=FUEL_API_TIMEOUT,
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == FUEL_API_ATTEMPTS:
                    raise
        body = response.json()
        if body.get("messages") != "success":
            raise RuntimeError(f"Max Energy price API error: {body.get('messages', 'unknown')}")

        rows = body.get("data") or []
        gasoline_prices = _grade_prices(rows, "95 Ron Octane")
        diesel_prices = _grade_prices(rows, "Diesel")
        if not gasoline_prices or not diesel_prices:
            raise RuntimeError("Max Energy returned no usable 95-octane or diesel prices")

        gasoline_mmk = float(statistics.median(gasoline_prices))
        diesel_mmk = float(statistics.median(diesel_prices))
        fuel = {
            "gasoline_95_usd_per_litre": (
                round(gasoline_mmk / usd_mmk_market, 4) if usd_mmk_market else None
            ),
            "diesel_usd_per_litre": (
                round(diesel_mmk / usd_mmk_market, 4) if usd_mmk_market else None
            ),
            "gasoline_95_mmk_per_litre_market": gasoline_mmk,
            "diesel_mmk_per_litre_market": diesel_mmk,
            "as_of": _as_of(rows),
            "stations_sampled": {
                "gasoline_95": len(gasoline_prices),
                "diesel": len(diesel_prices),
            },
            "source": "Max Energy Myanmar daily station prices (median across stations)",
        }
    except Exception as exc:  # noqa: BLE001 - never crash the workflow
        errors.append(f"fuel_max_energy: {exc}")
    return {"data": fuel, "errors": errors}
