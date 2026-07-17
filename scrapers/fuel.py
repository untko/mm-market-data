"""Myanmar pump prices from Max Energy's daily station-price page."""
from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timedelta, timezone

import requests

from fuel_history import MAX_ENERGY_SOURCE

from . import common

FUEL_PRICES_URL = "https://www.maxenergy.com.mm/fuel-prices-list/"
FUEL_API_TIMEOUT = 90
FUEL_HTTP_RETRIES = 5
YANGON_TZ = timezone(timedelta(hours=6, minutes=30))
SOURCE = MAX_ENERGY_SOURCE

# These stations are deliberately omitted by the Max Energy page's JavaScript.
EXCLUDED_STATION_IDS = {"22", "24"}

_API_CONFIG_RE = re.compile(
    r"url:\s*['\"](?P<url>https://app\.maxenergy\.com\.mm/[^'\"]*/Price/GetPriceList/?)['\"]"
    r".{0,800}?['\"]apikey['\"]\s*:\s*['\"](?P<key>[^'\"]+)['\"]",
    re.DOTALL,
)
_API_DATETIME_FORMATS = (
    "%m/%d/%y %I:%M:%S %p",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def _page_api_config(html: str) -> tuple[str, str]:
    match = _API_CONFIG_RE.search(html)
    if not match:
        raise RuntimeError("Max Energy price API configuration not found in page")
    return match.group("url"), match.group("key")


def _request_with_retries(operation):
    for attempt in range(FUEL_HTTP_RETRIES + 1):
        try:
            response = operation()
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == FUEL_HTTP_RETRIES:
                raise


def _row_timestamp(row: dict) -> datetime:
    for field in ("transactiondate", "effectivedate", "pretransactiondate"):
        value = row.get(field)
        if not value:
            continue
        for date_format in _API_DATETIME_FORMATS:
            try:
                return datetime.strptime(value, date_format)
            except ValueError:
                continue
    return datetime.min


def _grade_prices(rows: list[dict], grade: str) -> list[float]:
    latest_by_station = {}
    for index, row in enumerate(rows):
        station_id = str(row.get("stationid"))
        if row.get("gradename") == grade and station_id not in EXCLUDED_STATION_IDS:
            candidate = (_row_timestamp(row), index, row)
            if candidate[:2] >= latest_by_station.get(station_id, (datetime.min, -1))[:2]:
                latest_by_station[station_id] = candidate
    return [
        float(row["price"])
        for _, _, row in latest_by_station.values()
        if float(row.get("price") or 0) > 0
    ]


def _as_of(rows: list[dict]) -> str | None:
    dates = []
    for row in rows:
        timestamp = _row_timestamp(row)
        if timestamp != datetime.min:
            dates.append(timestamp.date())
    return max(dates).isoformat() if dates else None


def discover_api_config(*, http=requests) -> tuple[str, str]:
    page = _request_with_retries(
        lambda: http.get(FUEL_PRICES_URL, headers=common.UA, timeout=common.TIMEOUT)
    )
    return _page_api_config(page.text)


def fetch_for_date(
    query_date: date,
    usd_mmk_market: float | None = None,
    *,
    http=requests,
    api_config: tuple[str, str] | None = None,
) -> dict:
    errors = []
    fuel = None
    try:
        api_url, api_key = api_config or discover_api_config(http=http)
        query_date_text = query_date.isoformat()
        payload = {
            "apikey": api_key,
            "fromdate": f"{query_date_text} 00:00:00",
            "todate": f"{query_date_text} 23:59:59",
        }
        response = _request_with_retries(
            lambda: http.post(
                api_url,
                json=payload,
                headers={**common.UA, "Content-Type": "application/json"},
                timeout=FUEL_API_TIMEOUT,
            )
        )
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
            "source": SOURCE,
        }
    except Exception as exc:  # noqa: BLE001 - never crash the workflow
        errors.append(f"fuel_max_energy: {exc}")
    return {"data": fuel, "errors": errors}


def fetch(
    usd_mmk_market: float | None = None,
    *,
    http=requests,
    now: datetime | None = None,
) -> dict:
    query_time = now or datetime.now(YANGON_TZ)
    if query_time.tzinfo is not None:
        query_time = query_time.astimezone(YANGON_TZ)
    return fetch_for_date(query_time.date(), usd_mmk_market, http=http)
