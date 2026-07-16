#!/usr/bin/env python3
"""Run all scrapers and write data/latest.json + per-topic JSON + history CSVs.

Designed to never fail the GitHub Action: every source degrades gracefully and
errors are recorded in the output instead of raising.
"""
from __future__ import annotations

import sys

from scrapers import common, exchange_rates, fuel, gold


def main() -> int:
    errors: list[str] = []

    fx = exchange_rates.fetch()
    errors += fx["errors"]
    market = fx["data"].get("market") or {}
    usd_mmk_market = market.get("USD_MMK")

    gold_res = gold.fetch(usd_mmk_market)
    errors += gold_res["errors"]

    fuel_res = fuel.fetch(usd_mmk_market)
    errors += fuel_res["errors"]

    now = common.utcnow()
    latest = {
        "updated_at_utc": now,
        "updated_at_yangon": common.yangon_now(),
        "fx": fx["data"],
        "gold": gold_res["data"],
        "fuel": fuel_res["data"],
        "errors": errors,
    }

    common.write_json("latest.json", latest)
    common.write_json("exchange_rates.json", {"updated_at_utc": now, **fx["data"], "errors": fx["errors"]})
    if gold_res["data"]:
        common.write_json("gold.json", {"updated_at_utc": now, **gold_res["data"]})
    if fuel_res["data"]:
        common.write_json("fuel.json", {"updated_at_utc": now, **fuel_res["data"]})

    # history (append-only, deduped)
    if market:
        common.append_csv(
            "history/exchange_rates.csv",
            {
                "ts_utc": now,
                "usd_mmk_market": market.get("USD_MMK"),
                "thb_mmk_market": market.get("THB_MMK"),
                "usd_thb_market": market.get("USD_THB"),
                "usd_mmk_official": (fx["data"].get("official_reference") or {}).get("USD_MMK"),
                "spread_pct": fx["data"].get("market_vs_official_spread_pct"),
                "source": market.get("source"),
            },
            dedupe_keys=["usd_mmk_market", "thb_mmk_market", "usd_mmk_official"],
        )
    if gold_res["data"]:
        g = gold_res["data"]
        common.append_csv(
            "history/gold.csv",
            {
                "ts_utc": now,
                "usd_per_oz": g.get("usd_per_oz"),
                "mmk_per_oz_market": g.get("mmk_per_oz_market"),
                "mmk_per_tical_market": g.get("mmk_per_tical_market"),
            },
            dedupe_keys=["usd_per_oz", "mmk_per_oz_market"],
        )
    if fuel_res["data"]:
        f = fuel_res["data"]
        common.append_csv(
            "history/fuel.csv",
            {
                "ts_utc": now,
                "as_of": f.get("as_of"),
                "gasoline_95_usd_per_litre": f.get("gasoline_95_usd_per_litre"),
                "diesel_usd_per_litre": f.get("diesel_usd_per_litre"),
                "gasoline_95_mmk_per_litre_market": f.get("gasoline_95_mmk_per_litre_market"),
                "diesel_mmk_per_litre_market": f.get("diesel_mmk_per_litre_market"),
            },
            dedupe_keys=["as_of", "gasoline_95_usd_per_litre", "diesel_usd_per_litre"],
        )

    print("== update summary ==")
    print(f"fx market: {market or 'FAILED'}")
    print(f"gold: {gold_res['data'] or 'FAILED'}")
    print(f"fuel: {fuel_res['data'] or 'FAILED'}")
    if errors:
        print("non-fatal errors:")
        for e in errors:
            print(f"  - {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
