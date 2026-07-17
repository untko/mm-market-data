import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import dashboard


class DashboardTests(unittest.TestCase):
    def test_generates_readme_dashboard_from_committed_snapshots(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            history_dir = data_dir / "history"
            history_dir.mkdir(parents=True)
            (data_dir / "latest.json").write_text(
                json.dumps(
                    {
                        "updated_at_utc": "2026-07-17T14:09:03+00:00",
                        "fx": {"market": {"USD_MMK": 4250, "THB_MMK": 116.4384}},
                        "fuel": {
                            "gasoline_95_mmk_per_litre_market": 3330,
                            "diesel_mmk_per_litre_market": 3220,
                        },
                        "errors": [],
                    }
                )
            )
            for filename, fieldnames, row in (
                (
                    "exchange_rates.csv",
                    ["ts_utc", "usd_mmk_market"],
                    ["2026-07-17T14:09:03+00:00", "4250"],
                ),
                (
                    "fuel.csv",
                    [
                        "ts_utc",
                        "as_of",
                        "gasoline_95_mmk_per_litre_market",
                        "diesel_mmk_per_litre_market",
                        "source",
                        "provenance",
                    ],
                    [
                        "2026-07-17T04:49:16+00:00",
                        "2026-07-17",
                        "3330",
                        "3220",
                        "Max Energy Myanmar daily station prices (median across stations)",
                        "scheduled",
                    ],
                ),
            ):
                with (history_dir / filename).open("w", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(fieldnames)
                    writer.writerow(row)

            output = Path(tmp) / "dashboard.svg"
            dashboard.generate_dashboard(data_dir=data_dir, output_path=output)
            svg = output.read_text()

        self.assertIn("<svg", svg)
        self.assertIn("Myanmar market dashboard", svg)
        self.assertIn("USD / MMK", svg)
        self.assertIn("4,250", svg)
        self.assertNotIn("Gold / tical", svg)
        self.assertIn("95 octane / L", svg)
        self.assertIn("3,330", svg)
        self.assertIn("Collecting history · 1/8 points", svg)
        self.assertIn("1 scheduled", svg)

    def test_fuel_trend_excludes_iso_dated_rows_from_other_sources(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            history_dir = data_dir / "history"
            history_dir.mkdir(parents=True)
            (data_dir / "latest.json").write_text(
                json.dumps(
                    {
                        "updated_at_utc": "2026-07-17T14:09:03+00:00",
                        "fx": {"market": {}},
                        "fuel": {},
                        "errors": [],
                    }
                )
            )
            with (history_dir / "fuel.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "ts_utc",
                        "as_of",
                        "gasoline_95_mmk_per_litre_market",
                        "diesel_mmk_per_litre_market",
                        "source",
                        "provenance",
                    ],
                )
                writer.writeheader()
                for day in range(9, 17):
                    writer.writerow(
                        {
                            "ts_utc": f"2026-07-{day:02d}T00:00:00+00:00",
                            "as_of": f"2026-07-{day:02d}",
                            "gasoline_95_mmk_per_litre_market": 9000 + day,
                            "diesel_mmk_per_litre_market": 8000 + day,
                            "source": "Unrelated ISO-dated source",
                            "provenance": "backfill",
                        }
                    )
                writer.writerow(
                    {
                        "ts_utc": "2026-07-17T00:00:00+00:00",
                        "as_of": "2026-07-17",
                        "gasoline_95_mmk_per_litre_market": 3330,
                        "diesel_mmk_per_litre_market": 3220,
                        "source": "Max Energy Myanmar daily station prices (median across stations)",
                        "provenance": "scheduled",
                    }
                )

            output = Path(tmp) / "dashboard.svg"
            dashboard.generate_dashboard(data_dir=data_dir, output_path=output)
            svg = output.read_text()

        self.assertIn("Collecting history · 1/8 points", svg)
        self.assertNotIn("9,016", svg)


if __name__ == "__main__":
    unittest.main()
