#!/usr/bin/env python3
"""Update selected market datasets, histories, and the README dashboard."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fuel_history
from dashboard import generate_dashboard
from scrapers import common, exchange_rates, fuel, gold

ALL_TOPICS = {"fx", "gold", "fuel"}
DEFAULT_TOPICS = {"fx", "fuel"}


def _snapshot(relpath: str) -> dict | None:
    payload = common.read_json(relpath)
    if not payload:
        return None
    payload = dict(payload)
    payload.pop("updated_at_utc", None)
    payload.pop("errors", None)
    return payload or None


def _merged_fx(existing: dict | None, fetched: dict) -> dict:
    merged = dict(existing or {})
    for key in ("market", "official_reference", "interbank", "retail_cash"):
        if fetched.get(key) is not None:
            merged[key] = fetched[key]
    market = merged.get("market") or {}
    official = merged.get("official_reference") or {}
    if market.get("USD_MMK") and official.get("USD_MMK"):
        merged["market_vs_official_spread_pct"] = round(
            (market["USD_MMK"] / official["USD_MMK"] - 1) * 100, 2
        )
    return merged


def _retail_cash_history_row(retail_cash: dict, *, ts_utc: str) -> dict:
    row = {
        "ts_utc": ts_utc,
        "source_updated_at_raw": retail_cash.get("source_updated_at_raw"),
    }
    quotes = retail_cash.get("quotes") or {}
    for currency in exchange_rates.SUPERRICH_THAILAND_CURRENCIES:
        quote = quotes.get(currency) or {}
        prefix = currency.lower()
        row[f"{prefix}_denomination"] = quote.get("denomination")
        row[f"{prefix}_buy_thb_per_unit"] = quote.get("buy_thb_per_unit")
        row[f"{prefix}_sell_thb_per_unit"] = quote.get("sell_thb_per_unit")
    row["source"] = retail_cash.get("source")
    return row


def run(topics: set[str]) -> int:
    unknown = topics - ALL_TOPICS
    if unknown:
        raise ValueError(f"unknown topics: {', '.join(sorted(unknown))}")

    errors: list[str] = []
    now = common.utcnow()
    existing_fx = _snapshot("exchange_rates.json")
    existing_gold = _snapshot("gold.json")
    existing_fuel = _snapshot("fuel.json")

    fx_observation = None
    if "fx" in topics:
        fx_result = exchange_rates.fetch()
        errors += fx_result["errors"]
        fx_observation = fx_result["data"]
        fx_data = _merged_fx(existing_fx, fx_observation)
        common.write_json(
            "exchange_rates.json",
            {"updated_at_utc": now, **fx_data, "errors": fx_result["errors"]},
        )
    else:
        fx_data = existing_fx or {}

    market = fx_data.get("market") or {}
    usd_mmk_market = market.get("USD_MMK")

    gold_observation = None
    if "gold" in topics:
        gold_result = gold.fetch(usd_mmk_market)
        errors += gold_result["errors"]
        gold_observation = gold_result["data"]
        gold_data = gold_observation or existing_gold
        if gold_observation:
            common.write_json("gold.json", {"updated_at_utc": now, **gold_observation})
    else:
        gold_data = existing_gold

    fuel_observation = None
    if "fuel" in topics:
        fuel_result = fuel.fetch(usd_mmk_market)
        errors += fuel_result["errors"]
        fuel_observation = fuel_result["data"]
        fuel_data = fuel_observation or existing_fuel
        if fuel_observation:
            common.write_json("fuel.json", {"updated_at_utc": now, **fuel_observation})
    else:
        fuel_data = existing_fuel

    latest = {
        "updated_at_utc": now,
        "updated_at_yangon": common.yangon_now(),
        "fx": fx_data,
        "gold": gold_data,
        "fuel": fuel_data,
        "errors": errors,
    }
    common.write_json("latest.json", latest)

    if fx_observation and fx_observation.get("market"):
        observed_market = fx_observation["market"]
        common.append_csv(
            "history/exchange_rates.csv",
            {
                "ts_utc": now,
                "usd_mmk_market": observed_market.get("USD_MMK"),
                "thb_mmk_market": observed_market.get("THB_MMK"),
                "usd_thb_market": observed_market.get("USD_THB"),
                "usd_mmk_official": (fx_data.get("official_reference") or {}).get("USD_MMK"),
                "spread_pct": fx_data.get("market_vs_official_spread_pct"),
                "source": observed_market.get("source"),
            },
            dedupe_keys=["usd_mmk_market", "thb_mmk_market", "usd_mmk_official"],
        )
    if fx_observation and fx_observation.get("retail_cash"):
        retail_cash = fx_observation["retail_cash"]
        retail_row = _retail_cash_history_row(retail_cash, ts_utc=now)
        retail_dedupe_keys = [
            f"{currency.lower()}_{field}"
            for currency in exchange_rates.SUPERRICH_THAILAND_CURRENCIES
            for field in ("denomination", "buy_thb_per_unit", "sell_thb_per_unit")
        ]
        common.append_csv(
            "history/superrich_thailand.csv",
            retail_row,
            dedupe_keys=retail_dedupe_keys,
        )
    if gold_observation:
        common.append_csv(
            "history/gold.csv",
            {
                "ts_utc": now,
                "usd_per_oz": gold_observation.get("usd_per_oz"),
                "mmk_per_oz_market": gold_observation.get("mmk_per_oz_market"),
                "mmk_per_tical_market": gold_observation.get("mmk_per_tical_market"),
            },
            dedupe_keys=["usd_per_oz", "mmk_per_oz_market"],
        )
    if fuel_observation:
        common.append_csv(
            "history/fuel.csv",
            fuel_history.serialize(
                fuel_observation,
                ts_utc=now,
                provenance=fuel_history.PROVENANCE_SCHEDULED,
                include_usd=True,
            ),
            dedupe_keys=["as_of", "gasoline_95_usd_per_litre", "diesel_usd_per_litre"],
        )

    dashboard_path = generate_dashboard(
        data_dir=Path(common.DATA_DIR),
        output_path=Path(common.DATA_DIR).parent / "dashboard" / "market-trends.svg",
    )
    print("== update summary ==")
    print(f"topics: {', '.join(sorted(topics))}")
    print(f"fx market: {market or 'UNAVAILABLE'}")
    print(f"gold: {gold_data or 'UNAVAILABLE'}")
    print(f"fuel: {fuel_data or 'UNAVAILABLE'}")
    print(f"dashboard: {dashboard_path}")
    if errors:
        print("non-fatal errors:")
        for error in errors:
            print(f"  - {error}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--topics",
        nargs="+",
        choices=sorted(ALL_TOPICS),
        default=sorted(DEFAULT_TOPICS),
        help="datasets to refresh (default: fx and fuel; gold is legacy/manual only)",
    )
    args = parser.parse_args(argv)
    return run(set(args.topics))


if __name__ == "__main__":
    sys.exit(main())
