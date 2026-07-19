import unittest
from unittest.mock import patch

from scrapers import exchange_rates


class ExchangeRateTests(unittest.TestCase):
    def test_fetch_retail_cash_includes_requested_superrich_thailand_pairs(self):
        superrich_payload = {
            "code": 20000,
            "data": {
                "dateTime": "2026-07-19T08:53:17.866Z",
                "exchangeRate": [
                    {
                        "cUnit": currency,
                        "rate": [
                            {
                                "cBuying": buying,
                                "cSelling": selling,
                                "denom": denomination,
                            }
                        ],
                    }
                    for currency, buying, selling, denomination in (
                        ("USD", 33.5, 33.58, "100"),
                        ("GBP", 45.0, 45.15, "50"),
                        ("EUR", 38.3, 38.45, "500-100"),
                        ("JPY", 0.206, 0.2075, "10000 - 5000"),
                        ("CNY", 4.93, 4.95, "100"),
                    )
                ],
            },
        }

        def fake_get_json(url, **kwargs):
            if url == exchange_rates.SUPERRICH_THAILAND_RATES_URL:
                self.assertIn("Authorization", kwargs["headers"])
                return superrich_payload
            self.fail(f"unexpected URL: {url}")

        with patch("scrapers.exchange_rates.common.get_json", side_effect=fake_get_json):
            result = exchange_rates.fetch_retail_cash()

        self.assertEqual(result["errors"], [])
        retail = result["data"]
        self.assertEqual(retail["quote_currency"], "THB")
        self.assertNotIn("as_of", retail)
        self.assertEqual(retail["source_updated_at_raw"], "2026-07-19T08:53:17.866Z")
        self.assertEqual(set(retail["quotes"]), {"USD", "GBP", "EUR", "JPY", "CNY"})
        self.assertEqual(
            retail["quotes"]["USD"],
            {
                "pair": "USD/THB",
                "denomination": "100",
                "buy_thb_per_unit": 33.5,
                "sell_thb_per_unit": 33.58,
                "midpoint_thb_per_unit": 33.54,
            },
        )
        self.assertEqual(retail["quotes"]["JPY"]["pair"], "JPY/THB")


if __name__ == "__main__":
    unittest.main()
