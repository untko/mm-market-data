"""Exchange rates: MMK market (P2P) rates + official/interbank reference.

The "market" USD/MMK rate is derived from USDT/MMK peer-to-peer ads, which track
the real street rate rather than the Central Bank of Myanmar's fixed official rate.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

import requests

from . import common

SUPERRICH_P2P_URL = "https://superrich.tech/api/p2p-rates"
SUPERRICH_THAILAND_RATES_URL = "https://www.superrichthailand.com/api/v1/rates"
SUPERRICH_THAILAND_CURRENCIES = ("USD", "GBP", "EUR", "JPY", "CNY")
SUPERRICH_THAILAND_AUTHORIZATION = "Basic c3VwZXJyaWNoVGg6aFRoY2lycmVwdXM="
BINANCE_P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
CBM_URL = "https://forex.cbm.gov.mm/api/latest"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"


def _market_from_superrich() -> dict:
    """Aggregated Binance P2P USDT rates served by superrich.tech (works where
    Binance itself is geo-blocked, e.g. most CI runners)."""
    payload = common.get_json(SUPERRICH_P2P_URL)
    data = payload["data"]
    usd_mmk = float(data["MMK"])
    usd_thb = float(data["THB"])
    return {
        "USD_MMK": usd_mmk,
        "USD_THB": usd_thb,
        "THB_MMK": round(usd_mmk / usd_thb, 4),
        "source": "superrich.tech (aggregated Binance P2P USDT ads)",
    }


def _market_from_binance() -> dict:
    """Direct Binance P2P: median of the 10 best USDT-sell ads in MMK.
    Often geo-blocked from datacenter IPs; kept as a fallback."""
    payload = {"asset": "USDT", "fiat": "MMK", "tradeType": "SELL", "page": 1, "rows": 10}
    resp = requests.post(
        BINANCE_P2P_URL,
        json=payload,
        headers={**common.UA, "Content-Type": "application/json"},
        timeout=common.TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != "000000":
        raise RuntimeError(f"binance p2p error: {body.get('message', 'unknown')}")
    ads = body.get("data") or []
    if not ads:
        raise RuntimeError("binance p2p returned no ads (likely geo-blocked)")
    prices = [float(ad["adv"]["price"]) for ad in ads]
    return {
        "USD_MMK": statistics.median(prices),
        "ads_sampled": len(prices),
        "source": "Binance P2P USDT/MMK (median of top sell ads)",
    }


def _retail_cash_superrich_thailand() -> dict:
    """Primary cash-counter quotes advertised by SuperRich Thailand.

    The first rate is the site's primary quote for a currency and normally
    represents its largest banknote denomination. Buying and selling are from
    SuperRich's perspective; values are Thai baht per unit of foreign currency.
    """
    body = common.get_json(
        SUPERRICH_THAILAND_RATES_URL,
        headers={"Authorization": SUPERRICH_THAILAND_AUTHORIZATION},
    )
    if body.get("code") != 20000:
        raise RuntimeError(
            f"SuperRich Thailand API error: {body.get('descriptionEn', 'unknown')}"
        )

    data = body.get("data") or {}
    rates_by_currency = {
        item.get("cUnit"): item for item in data.get("exchangeRate") or []
    }
    missing = [
        currency for currency in SUPERRICH_THAILAND_CURRENCIES if currency not in rates_by_currency
    ]
    if missing:
        raise RuntimeError(f"SuperRich Thailand missing currencies: {', '.join(missing)}")

    quotes = {}
    for currency in SUPERRICH_THAILAND_CURRENCIES:
        rate_options = rates_by_currency[currency].get("rate") or []
        if not rate_options:
            raise RuntimeError(f"SuperRich Thailand returned no {currency} rates")
        primary = rate_options[0]
        buying = float(primary["cBuying"])
        selling = float(primary["cSelling"])
        if buying <= 0 or selling <= 0:
            raise RuntimeError(f"SuperRich Thailand returned invalid {currency} rates")
        quotes[currency] = {
            "pair": f"{currency}/THB",
            "denomination": str(primary.get("denom") or "").strip() or None,
            "buy_thb_per_unit": buying,
            "sell_thb_per_unit": selling,
            "midpoint_thb_per_unit": round((buying + selling) / 2, 6),
        }

    return {
        "quote_currency": "THB",
        "quotes": quotes,
        # The API currently suffixes a Thailand wall-clock value with "Z".
        # Preserve it verbatim instead of presenting it as a trustworthy UTC instant.
        "source_updated_at_raw": data.get("dateTime"),
        "source": "SuperRich Thailand retail cash exchange",
    }


def _official_cbm() -> dict:
    body = common.get_json(CBM_URL)
    as_of = None
    try:
        as_of = datetime.fromtimestamp(int(body["timestamp"]), tz=timezone.utc).isoformat()
    except Exception:
        pass
    return {
        "USD_MMK": float(str(body["rates"]["USD"]).replace(",", "")),
        "THB_MMK": float(str(body["rates"].get("THB", "0")).replace(",", "")) or None,
        "as_of": as_of,
        "source": "Central Bank of Myanmar (official fixed rate)",
    }


def _interbank() -> dict:
    body = common.get_json(FRANKFURTER_URL, params={"base": "USD", "symbols": "THB,EUR"})
    return {
        "USD_THB": body["rates"]["THB"],
        "USD_EUR": body["rates"]["EUR"],
        "as_of": body["date"],
        "source": "Frankfurter / ECB reference",
    }


def fetch() -> dict:
    errors = []

    market = None
    for fn in (_market_from_superrich, _market_from_binance):
        try:
            market = fn()
            break
        except Exception as exc:  # noqa: BLE001 - never crash the workflow
            errors.append(f"{fn.__name__}: {exc}")

    official = None
    try:
        official = _official_cbm()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"official_cbm: {exc}")

    retail_cash = None
    try:
        retail_cash = _retail_cash_superrich_thailand()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"retail_cash_superrich_thailand: {exc}")

    interbank = None
    try:
        interbank = _interbank()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"interbank: {exc}")

    result = {
        "market": market,
        "official_reference": official,
        "interbank": interbank,
        "retail_cash": retail_cash,
    }
    if market and official and official.get("USD_MMK"):
        result["market_vs_official_spread_pct"] = round(
            (market["USD_MMK"] / official["USD_MMK"] - 1) * 100, 2
        )
    return {"data": result, "errors": errors}
