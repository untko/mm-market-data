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

    interbank = None
    try:
        interbank = _interbank()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"interbank: {exc}")

    result = {"market": market, "official_reference": official, "interbank": interbank}
    if market and official and official.get("USD_MMK"):
        result["market_vs_official_spread_pct"] = round(
            (market["USD_MMK"] / official["USD_MMK"] - 1) * 100, 2
        )
    return {"data": result, "errors": errors}
