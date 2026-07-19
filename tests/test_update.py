import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import update
from scrapers import common


class SelectiveUpdateTests(unittest.TestCase):
    def test_fx_refresh_preserves_skipped_fuel_and_legacy_gold_snapshots(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            (data_dir / "exchange_rates.json").write_text(
                json.dumps({"updated_at_utc": "old", "market": {"USD_MMK": 4200}})
            )
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
            fx_result = {
                "data": {
                    "market": {"USD_MMK": 4250, "USD_THB": 36.5, "THB_MMK": 116.4384},
                    "official_reference": {"USD_MMK": 2100},
                    "interbank": {"USD_THB": 33.6},
                    "retail_cash": {
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
                    },
                    "market_vs_official_spread_pct": 102.38,
                },
                "errors": [],
            }

            with (
                patch.object(common, "DATA_DIR", str(data_dir)),
                patch("update.exchange_rates.fetch", return_value=fx_result),
                patch("update.gold.fetch") as gold_fetch,
                patch("update.fuel.fetch") as fuel_fetch,
            ):
                result = update.run({"fx"})
                second_result = update.run({"fx"})

            latest = json.loads((data_dir / "latest.json").read_text())
            retail_history = (data_dir / "history" / "superrich_thailand.csv").read_text()

        self.assertEqual(result, 0)
        self.assertEqual(second_result, 0)
        self.assertEqual(latest["fx"]["market"]["USD_MMK"], 4250)
        self.assertEqual(latest["fx"]["retail_cash"]["quotes"]["GBP"]["sell_thb_per_unit"], 45.15)
        self.assertEqual(latest["fuel"]["gasoline_95_mmk_per_litre_market"], 3300)
        self.assertEqual(latest["gold"]["usd_per_oz"], 3900)
        self.assertIn("usd_buy_thb_per_unit", retail_history)
        self.assertIn("33.5", retail_history)
        self.assertEqual(len(retail_history.splitlines()), 2)
        gold_fetch.assert_not_called()
        fuel_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
