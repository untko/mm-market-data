# mm-market-data

Automated collector for **real market** prices in Myanmar — updated by GitHub Actions and
committed back to this repo, so the `data/` folder doubles as a free JSON API via
`raw.githubusercontent.com`.

| Dataset | What you get | Update cadence |
| --- | --- | --- |
| **MMK market FX** | USD/MMK, THB/MMK from **P2P (USDT) market rates** — *not* the official CBM rate | every 6 h |
| **Official vs market spread** | CBM fixed rate next to the market rate, with spread % | every 6 h |
| **Gold** | International spot XAU/USD + MMK equivalents (per oz / gram / tical) at the **market** rate | every 6 h |
| **Fuel** | Myanmar gasoline (octane-95) & diesel, USD/litre, + MMK/litre at the market rate | weekly (source updates Mondays) |

## Why not the official rate?

The Central Bank of Myanmar fixes USD/MMK (e.g. 2100), which does not reflect the price
people actually pay. This repo uses **USDT/MMK peer-to-peer ads** as the market benchmark
(~4200+ in mid-2026), and also records the official rate so you can see the spread.
Note P2P USDT rates track the cash/street rate closely but are not identical to it.

## Data sources

| Source | Used for | Notes |
| --- | --- | --- |
| `superrich.tech/api/p2p-rates` | USD/MMK, USD/THB market rates | Aggregated Binance P2P ads; works from CI IPs where Binance is geo-blocked |
| Binance P2P API (direct) | USD/MMK fallback | Median of top 10 USDT-sell ads; skipped automatically when geo-blocked |
| Central Bank of Myanmar API | official reference rate | For the spread calculation only |
| Frankfurter (ECB reference) | interbank USD/THB, USD/EUR | Context for the P2P THB rate |
| gold-api.com | XAU/USD spot | Free, keyless |
| GlobalPetrolPrices.com | gasoline & diesel prices | Scraped with headless Chromium (page is JS-rendered); weekly updates |

## Using the data

Once this repo is on GitHub, the latest snapshot is available at:

```
https://raw.githubusercontent.com/<you>/<repo>/main/data/latest.json
```

Per-topic files: `data/exchange_rates.json`, `data/gold.json`, `data/fuel.json`.
Append-only history (great for charts): `data/history/*.csv`.

`latest.json` shape:

```jsonc
{
  "updated_at_utc": "…",
  "fx": {
    "market":            { "USD_MMK": 4250.0, "USD_THB": 36.5, "THB_MMK": 116.44, "source": "…" },
    "official_reference":{ "USD_MMK": 2100.0, "source": "Central Bank of Myanmar …" },
    "interbank":         { "USD_THB": 33.565, "USD_EUR": 0.872, "…": "…" },
    "market_vs_official_spread_pct": 102.38
  },
  "gold": { "usd_per_oz": 3977.3, "mmk_per_tical_market": 8874336.97, "…": "…" },
  "fuel": { "gasoline_95_usd_per_litre": 1.059, "diesel_mmk_per_litre_market": 4250.0, "as_of": "13-Jul-2026" },
  "errors": []   // non-fatal source failures are listed here, never crash the workflow
}
```

## Setup

1. Create a new GitHub repo and push this code:

   ```bash
   git remote add origin git@github.com:<you>/<repo>.git
   git push -u origin main
   ```

2. That's it. The workflow (`.github/workflows/update-data.yml`) runs every 6 hours
   (`cron: "23 */6 * * *"`) and commits any changes. You can also trigger it manually
   from **Actions → Update market data → Run workflow**.

> Scheduled workflows can be delayed under GitHub load, and GitHub disables schedules
> after 60 days of repo inactivity — the bot commits usually keep it alive, but a manual
> run now and then doesn't hurt.

## Running locally

```bash
pip install -r requirements.txt
playwright install chromium   # or use system chromium — auto-detected
python update.py
```

## Caveats

- **P2P ≠ exact street rate.** USDT/MMK ads are the best programmatically accessible
  proxy for the real market; cash rates in Yangon/Mandalay will differ slightly.
- **Fuel** figures are national averages collected by GlobalPetrolPrices (weekly), and
  their MMK equivalents here are computed at the market FX rate — actual station prices
  vary by city and day.
- **Gold** MMK values are international spot × market FX. Local gold (per tical) trades
  at its own premium/discount.
- Third-party endpoints can change or go down; failures are logged in `errors` and the
  previous committed data stays in place until a source recovers.

## License

MIT — data belongs to the respective sources; check their terms before commercial use.
