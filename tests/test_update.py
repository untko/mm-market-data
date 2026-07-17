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

            latest = json.loads((data_dir / "latest.json").read_text())

        self.assertEqual(result, 0)
        self.assertEqual(latest["fx"]["market"]["USD_MMK"], 4250)
        self.assertEqual(latest["fuel"]["gasoline_95_mmk_per_litre_market"], 3300)
        self.assertEqual(latest["gold"]["usd_per_oz"], 3900)
        gold_fetch.assert_not_called()
        fuel_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
