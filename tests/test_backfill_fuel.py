from datetime import date
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import backfill_fuel


class FuelBackfillTests(unittest.TestCase):
    def test_records_retrieval_time_separately_from_source_date(self):
        result = {
            "data": {
                "as_of": "2026-07-17",
                "gasoline_95_mmk_per_litre_market": 3330,
                "diesel_mmk_per_litre_market": 3220,
                "source": "Max Energy Myanmar daily station prices (median across stations)",
            },
            "errors": [],
        }
        with TemporaryDirectory() as tmp, patch(
            "backfill_fuel._retrieval_timestamp",
            return_value="2026-07-18T01:02:03+00:00",
        ), patch(
            "backfill_fuel.fuel.discover_api_config", return_value=("url", "key")
        ), patch("backfill_fuel.fuel.fetch_for_date", return_value=result), patch(
            "backfill_fuel.generate_dashboard"
        ):
            output = Path(tmp) / "fuel.csv"
            exit_code = backfill_fuel.backfill(
                days=1,
                end=date(2026, 7, 17),
                workers=1,
                output=output,
            )
            with output.open(newline="") as fh:
                row = next(csv.DictReader(fh))

        self.assertEqual(exit_code, 0)
        self.assertEqual(row["as_of"], "2026-07-17")
        self.assertEqual(row["ts_utc"], "2026-07-18T01:02:03+00:00")
        self.assertEqual(row["provenance"], "backfill")

    def test_rejects_api_rows_for_a_different_source_date(self):
        result = {
            "data": {
                "as_of": "2026-07-16",
                "gasoline_95_mmk_per_litre_market": 3330,
                "diesel_mmk_per_litre_market": 3220,
                "source": "Max Energy Myanmar daily station prices (median across stations)",
            },
            "errors": [],
        }
        with TemporaryDirectory() as tmp, patch(
            "backfill_fuel.fuel.discover_api_config", return_value=("url", "key")
        ), patch("backfill_fuel.fuel.fetch_for_date", return_value=result), patch(
            "backfill_fuel.generate_dashboard"
        ):
            exit_code = backfill_fuel.backfill(
                days=1,
                end=date(2026, 7, 17),
                workers=1,
                output=Path(tmp) / "fuel.csv",
            )
            rows = backfill_fuel._read_existing(Path(tmp) / "fuel.csv")

        self.assertEqual(exit_code, 1)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
