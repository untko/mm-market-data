import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import update
from scrapers import common


class SelectiveUpdateTests(unittest.TestCase):
    def _seed_snapshots(self, data_dir: Path, exchange_rates: dict) -> None:
        (data_dir / "exchange_rates.json").write_text(json.dumps(exchange_rates))
        (data_dir / "gold.json").write_text(
            json.dumps({"updated_at_utc": "old", "usd_per_oz": 3900})
        )
        (data_dir / "fuel.json").write_text(
            json.dumps(
                {
                    "updated_at_utc": "old",
                    "gasoline_95_mmk_per_litre_market": 3300,
                    "diesel_mmk_per_litre_market": 3200,
                }
            )
        )

    def test_fx_refresh_preserves_cash_fuel_and_legacy_gold_snapshots(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            self._seed_snapshots(
                data_dir,
                {
                    "updated_at_utc": "old",
                    "market": {"USD_MMK": 4200, "collected_at_utc": "market-old"},
                    "retail_cash": {
                        "collected_at_utc": "cash-old",
                        "quotes": {"GBP": {"sell_thb_per_unit": 44.0}},
                    },
                },
            )
            fx_result = {
                "data": {
                    "market": {"USD_MMK": 4250, "USD_THB": 36.5, "THB_MMK": 116.4384},
                    "official_reference": {"USD_MMK": 2100},
                    "interbank": {"USD_THB": 33.6},
                    "market_vs_official_spread_pct": 102.38,
                },
                "errors": [],
            }

            with (
                patch.object(common, "DATA_DIR", str(data_dir)),
                patch("update.exchange_rates.fetch", return_value=fx_result),
                patch("update.exchange_rates.fetch_retail_cash") as cash_fx_fetch,
                patch("update.gold.fetch") as gold_fetch,
                patch("update.fuel.fetch") as fuel_fetch,
            ):
                result = update.run({"fx"})

            latest = json.loads((data_dir / "latest.json").read_text())

        self.assertEqual(result, 0)
        self.assertEqual(latest["fx"]["market"]["USD_MMK"], 4250)
        self.assertNotEqual(latest["fx"]["market"]["collected_at_utc"], "market-old")
        self.assertEqual(latest["fx"]["retail_cash"]["quotes"]["GBP"]["sell_thb_per_unit"], 44.0)
        self.assertEqual(latest["fx"]["retail_cash"]["collected_at_utc"], "cash-old")
        self.assertEqual(latest["fuel"]["gasoline_95_mmk_per_litre_market"], 3300)
        self.assertEqual(latest["gold"]["usd_per_oz"], 3900)
        cash_fx_fetch.assert_not_called()
        gold_fetch.assert_not_called()
        fuel_fetch.assert_not_called()

    def test_cash_fx_refresh_is_independent_and_deduplicates_unchanged_history(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            self._seed_snapshots(
                data_dir,
                {
                    "updated_at_utc": "2026-07-19T04:00:00+00:00",
                    "market": {
                        "USD_MMK": 4200,
                        "collected_at_utc": "2026-07-19T04:00:00+00:00",
                    },
                },
            )
            retail_cash = {
                "quote_currency": "THB",
                "quotes": {
                    currency: {
                        "pair": f"{currency}/THB",
                        "denomination": denomination,
                        "buy_thb_per_unit": buying,
                        "sell_thb_per_unit": selling,
                        "midpoint_thb_per_unit": midpoint,
                    }
                    for currency, denomination, buying, selling, midpoint in (
                        ("USD", "100", 33.5, 33.58, 33.54),
                        ("GBP", "50", 45.0, 45.15, 45.075),
                        ("EUR", "500-100", 38.3, 38.45, 38.375),
                        ("JPY", "10000 - 5000", 0.206, 0.2075, 0.20675),
                        ("CNY", "100", 4.93, 4.95, 4.94),
                    )
                },
                "source_updated_at_raw": "2026-07-19T08:53:17.866Z",
                "source": "SuperRich Thailand retail cash exchange",
            }

            with (
                patch.object(common, "DATA_DIR", str(data_dir)),
                patch("update.common.utcnow", return_value="2026-07-20T01:30:00+00:00"),
                patch("update.exchange_rates.fetch") as fx_fetch,
                patch(
                    "update.exchange_rates.fetch_retail_cash",
                    return_value={"data": retail_cash, "errors": []},
                ),
                patch("update.gold.fetch") as gold_fetch,
                patch("update.fuel.fetch") as fuel_fetch,
            ):
                result = update.run({"cash-fx"})
                second_result = update.run({"cash-fx"})

            latest = json.loads((data_dir / "latest.json").read_text())
            retail_history = (data_dir / "history" / "superrich_thailand.csv").read_text()
            successful_exchange_rates = json.loads(
                (data_dir / "exchange_rates.json").read_text()
            )

            with (
                patch.object(common, "DATA_DIR", str(data_dir)),
                patch("update.common.utcnow", return_value="2026-07-21T01:30:00+00:00"),
                patch("update.exchange_rates.fetch") as failed_fx_fetch,
                patch(
                    "update.exchange_rates.fetch_retail_cash",
                    return_value={"data": None, "errors": ["SuperRich unavailable"]},
                ),
                patch("update.gold.fetch"),
                patch("update.fuel.fetch"),
            ):
                failure_result = update.run({"cash-fx"})

            failed_exchange_rates = json.loads(
                (data_dir / "exchange_rates.json").read_text()
            )

        self.assertEqual(result, 0)
        self.assertEqual(second_result, 0)
        self.assertEqual(failure_result, 0)
        self.assertEqual(latest["fx"]["market"]["USD_MMK"], 4200)
        self.assertEqual(
            latest["fx"]["market"]["collected_at_utc"],
            "2026-07-19T04:00:00+00:00",
        )
        self.assertEqual(latest["fx"]["retail_cash"]["quotes"]["GBP"]["sell_thb_per_unit"], 45.15)
        self.assertEqual(
            successful_exchange_rates["retail_cash"]["collected_at_utc"],
            "2026-07-20T01:30:00+00:00",
        )
        self.assertEqual(
            failed_exchange_rates["updated_at_utc"],
            successful_exchange_rates["updated_at_utc"],
        )
        self.assertEqual(
            failed_exchange_rates["market"]["collected_at_utc"],
            "2026-07-19T04:00:00+00:00",
        )
        self.assertEqual(
            failed_exchange_rates["retail_cash"],
            successful_exchange_rates["retail_cash"],
        )
        self.assertEqual(failed_exchange_rates["errors"], ["SuperRich unavailable"])
        self.assertIn("usd_buy_thb_per_unit", retail_history)
        self.assertIn("33.5", retail_history)
        self.assertEqual(len(retail_history.splitlines()), 2)
        fx_fetch.assert_not_called()
        failed_fx_fetch.assert_not_called()
        gold_fetch.assert_not_called()
        fuel_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
