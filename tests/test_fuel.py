from datetime import datetime, timezone
import unittest

import requests

from scrapers import fuel


class _Response:
    def __init__(self, *, text="", payload=None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _MaxEnergyHttp:
    def get(self, *args, **kwargs):
        return _Response(
            text="""
                url: 'https://app.maxenergy.com.mm/maxapi/webapi/Price/GetPriceList',
                data: JSON.stringify({'apikey':'public-page-key'})
            """
        )

    def post(self, *args, **kwargs):
        if kwargs["json"]["fromdate"] != "2026-07-17 00:00:00":
            raise AssertionError("expected a whole-day start time")
        if kwargs["json"]["todate"] != "2026-07-17 23:59:59":
            raise AssertionError("expected a whole-day end time")
        rows = []
        for grade, prices in {
            "95 Ron Octane": [
                ("01", 3300, "7/17/26 10:00:00 AM"),
                ("01", 1000, "7/17/26 5:00:00 AM"),
                ("02", 3350, "7/17/26 10:00:00 AM"),
                ("02", 1000, "7/17/26 5:00:00 AM"),
                ("03", 3400, "7/17/26 10:00:00 AM"),
                ("04", 0, "7/17/26 10:00:00 AM"),
                ("22", 9999, "7/17/26 10:00:00 AM"),
            ],
            "Diesel": [
                ("01", 3000, "7/17/26 10:00:00 AM"),
                ("01", 1000, "7/17/26 5:00:00 AM"),
                ("02", 3100, "7/17/26 10:00:00 AM"),
                ("02", 1000, "7/17/26 5:00:00 AM"),
                ("03", 3200, "7/17/26 10:00:00 AM"),
                ("04", 0, "7/17/26 10:00:00 AM"),
                ("24", 9999, "7/17/26 10:00:00 AM"),
            ],
        }.items():
            rows.extend(
                {
                    "gradename": grade,
                    "stationid": station_id,
                    "price": price,
                    "effectivedate": "7/17/26 12:00:00 AM",
                    "transactiondate": transaction_date,
                }
                for station_id, price, transaction_date in prices
            )
        return _Response(payload={"messages": "success", "data": rows})


class _FlakyMaxEnergyHttp(_MaxEnergyHttp):
    def __init__(self):
        self.attempts = 0

    def post(self, *args, **kwargs):
        self.attempts += 1
        if self.attempts <= 5:
            raise requests.Timeout("temporary timeout")
        return super().post(*args, **kwargs)


class _FlakyPageHttp(_MaxEnergyHttp):
    def __init__(self):
        self.attempts = 0

    def get(self, *args, **kwargs):
        self.attempts += 1
        if self.attempts <= 5:
            raise requests.Timeout("temporary page timeout")
        return super().get(*args, **kwargs)


class FuelFetchTests(unittest.TestCase):
    def test_returns_median_max_energy_station_prices(self):
        result = fuel.fetch(
            4250,
            http=_MaxEnergyHttp(),
            now=datetime(2026, 7, 17, 2, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(result["errors"], [])
        self.assertEqual(
            result["data"],
            {
                "gasoline_95_usd_per_litre": 0.7882,
                "diesel_usd_per_litre": 0.7294,
                "gasoline_95_mmk_per_litre_market": 3350.0,
                "diesel_mmk_per_litre_market": 3100.0,
                "as_of": "2026-07-17",
                "stations_sampled": {"gasoline_95": 3, "diesel": 3},
                "source": "Max Energy Myanmar daily station prices (median across stations)",
            },
        )

    def test_retries_a_temporary_price_api_timeout(self):
        http = _FlakyMaxEnergyHttp()

        result = fuel.fetch(
            4250,
            http=http,
            now=datetime(2026, 7, 17, 2, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(result["errors"], [])
        self.assertIsNotNone(result["data"])

    def test_retries_a_temporary_page_timeout(self):
        result = fuel.fetch(
            4250,
            http=_FlakyPageHttp(),
            now=datetime(2026, 7, 17, 2, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(result["errors"], [])
        self.assertIsNotNone(result["data"])


if __name__ == "__main__":
    unittest.main()
