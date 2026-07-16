"""Gold: international spot (XAU/USD) with MMK market-rate conversions.

Local Myanmar gold trades per tical (kyattha, ~16.33 g) and usually at a
premium/discount to the international price; the MMK figures here are the
international spot converted at the MMK *market* rate, for reference.
"""
from __future__ import annotations

from . import common

GOLD_API_URL = "https://api.gold-api.com/price/XAU"

TROY_OZ_GRAMS = 31.1034768
TICAL_GRAMS = 16.3293  # 1 kyattha / tical


def fetch(usd_mmk_market: float | None = None) -> dict:
    errors = []
    gold = None
    try:
        body = common.get_json(GOLD_API_URL)
        usd_per_oz = float(body["price"])
        gold = {
            "usd_per_oz": usd_per_oz,
            "usd_per_gram": round(usd_per_oz / TROY_OZ_GRAMS, 4),
            "as_of": body.get("updatedAt"),
            "source": "gold-api.com (international spot XAU/USD)",
        }
        if usd_mmk_market:
            gold["mmk_per_oz_market"] = round(usd_per_oz * usd_mmk_market, 2)
            gold["mmk_per_gram_market"] = round(usd_per_oz * usd_mmk_market / TROY_OZ_GRAMS, 2)
            gold["mmk_per_tical_market"] = round(
                usd_per_oz * usd_mmk_market * TICAL_GRAMS / TROY_OZ_GRAMS, 2
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"gold_api: {exc}")
    return {"data": gold, "errors": errors}
